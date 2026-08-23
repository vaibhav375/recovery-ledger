"""The response model — "the recovery gym" (spec section 7.3).

This is where every number is an ASSUMPTION, stated as one. Tier 1 already
proved the causal machinery (uplift learners, OPE estimators) recovers known
treatment effects on real randomised data — that's what makes it valid to
*transfer* the method here. This module does not re-prove that; it only
needs to be plausible enough that a policy trained against it produces a
defensible relative ranking of candidate policies (spec section 7.3: "the
simulator only needs to be plausible, not probative, because the method is
already proven separately"). Every constant below is invented for this
purpose and loosely anchored to the aggregate benchmarks in spec section
3.2 — anchoring an aggregate rate does not validate a causal response, see
`ENGINEERING_LOG.md` for why that distinction matters and was the whole
reason Tier 1 exists.

Hidden latent traits (liquidity, annoyance_threshold, dispute_propensity)
are generated here and used to determine outcomes, but are NEVER exposed to
the policy or the uplift learner — only observable case/customer fields are.
If the policy could see these directly there would be nothing to learn.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import (
    Channel,
    FailedPaymentCase,
    FailedSubscriptionCase,
    LossType,
    RecoveryCase,
)
from recovery_ledger.listener.listener import ReplyIntent

# --- calibration constants (all invented; see module docstring) -----------

BASE_ORGANIC_RESOLUTION_PROB = 0.05  # customer pays with zero intervention at all
RETRY_SUCCESS_PROB_GENERIC = 0.17    # anchored to "automated retries recover 15-20%" (spec 3.2)
RETRY_SUCCESS_PROB_SUBSCRIPTION = 0.35  # anchored to "subscription smart-retry recovers up to 57%"
                                          # cumulatively across attempts (spec 3.2) — per-step, not cumulative
HARD_DECLINE_RETRY_SUCCESS_PROB = 0.01  # retrying a hard decline (e.g. expired card) essentially never works

BASE_OPT_OUT_PROB_PER_CONTACT = 0.015
BASE_DISPUTE_PROB_PER_CONTACT = 0.01
BASE_PROMISE_TO_PAY_PROB_PER_CONTACT = 0.10


@dataclass(frozen=True)
class LatentTraits:
    """Hidden — never observed by the policy or the uplift learner."""

    liquidity: float           # 0..1, higher = more able to pay regardless of contact
    annoyance_threshold: float # 0..1, lower = annoyed by contact faster
    dispute_propensity: float  # 0..1, higher = more likely to dispute when contacted


def generate_population(cases: list[RecoveryCase], *, seed: int) -> dict[str, LatentTraits]:
    """Hidden traits, generated with a DECLARED, modest dependence on each
    case's observable fields — not pure noise independent of everything the
    policy can see.

    This dependence is what makes the whole uplift-transfer exercise
    non-vacuous. An earlier version of this function drew every trait
    independently of the case entirely, which meant the true treatment
    effect (persuadability(), driven only by these traits) was
    STATISTICALLY INDEPENDENT of every feature the uplift model was given —
    there was nothing for it to learn, by construction, no matter how good
    the learner was. Caught by checking corr(tau_hat, tau_true) on eval
    data and finding it was ~0 (not by assuming a plausible-looking result
    was actually right) — see ENGINEERING_LOG.md, 2026-08-24.

    First attempt at this fix (2026-08-24) used shifts of 0.10-0.15 against
    traits with a natural standard deviation of ~0.2 — checked
    corr(tau_hat, tau_true) afterwards instead of assuming a "declared
    correlation exists" fix was sufficient, and found it was still ~0 at
    the project's default training size (a T-learner on 1000 noisy
    Bernoulli outcomes couldn't reliably detect a signal that small; it
    inched up to a weak +0.16 at 5000 training cases and was NOT stable at
    20000 — evidence the signal was still marginal, not that more data
    would obviously fix it). Shifts below are roughly 2x stronger for
    exactly that reason: this needs to be a *learnable* signal, not merely
    a technically-nonzero one. Bulk of the variance is still unexplained
    per-customer noise — this is a genuine prediction problem, not a
    lookup table — but the explained part is now large enough for a
    T-learner to actually find at a training size this project can afford
    to run repeatedly (~1000-5000 cases, seconds not minutes)."""
    rng = np.random.default_rng(seed)
    traits: dict[str, LatentTraits] = {}
    for case in cases:
        liquidity_shift = (
            (0.35 if case.customer.is_b2b else 0.0)
            - 0.25 * min(case.amount_at_risk / 5000.0, 1.0)
        )
        liquidity = float(np.clip(rng.beta(2, 2) + liquidity_shift, 0.0, 1.0))

        dispute_shift = 0.35 if (case.customer.is_b2b or case.loss_type == LossType.OVERDUE_RECEIVABLE) else 0.0
        if case.loss_type == LossType.CHECKOUT_ABANDONMENT:
            dispute_shift -= 0.05  # nothing was ever charged; little to dispute
        dispute_propensity = float(np.clip(rng.beta(1.5, 8) + dispute_shift, 0.0, 1.0))

        if case.customer.channel_pref == Channel.WHATSAPP:
            annoyance_shift = 0.30
        elif case.customer.channel_pref == Channel.SMS:
            annoyance_shift = -0.30
        else:
            annoyance_shift = 0.0
        annoyance_threshold = float(np.clip(rng.beta(2, 2) + annoyance_shift, 0.0, 1.0))

        traits[case.case_id] = LatentTraits(
            liquidity=liquidity,
            annoyance_threshold=annoyance_threshold,
            dispute_propensity=dispute_propensity,
        )
    return traits


def persuadability(traits: LatentTraits) -> float:
    """The heterogeneous treatment effect driver — this is what an uplift
    model has to recover from observable correlates. Deliberately allows
    negative values: customers with high dispute propensity and low
    annoyance tolerance are "do-not-disturbs" (spec's N2) — contacting them
    makes things worse, not better."""
    return float(np.clip(
        0.12 + 0.30 * traits.liquidity - 0.45 * traits.dispute_propensity
        + 0.20 * (traits.annoyance_threshold - 0.5),
        -0.20, 0.55,
    ))


def _retry_success_prob(case: RecoveryCase) -> float:
    if isinstance(case, FailedSubscriptionCase):
        return RETRY_SUCCESS_PROB_SUBSCRIPTION
    if isinstance(case, FailedPaymentCase) and case.is_hard_decline:
        return HARD_DECLINE_RETRY_SUCCESS_PROB
    return RETRY_SUCCESS_PROB_GENERIC


@dataclass
class StepResult:
    reply: ReplyIntent
    paid: bool


class SimulationEnvironment:
    """Stateful per-run environment: tracks accumulated contact/annoyance
    per case and samples one outcome per `step()` call. Deterministic given
    the seed the environment was built with — draws are made from a single
    `np.random.Generator` advanced in call order, so re-running the same
    sequence of steps reproduces the same outcomes."""

    def __init__(self, traits_by_case: dict[str, LatentTraits], *, seed: int):
        self._traits = traits_by_case
        self._rng = np.random.default_rng(seed)
        self._contacts: dict[str, int] = {}

    def step(self, case: RecoveryCase, action_type: ActionType, attempt_index: int) -> StepResult:
        traits = self._traits[case.case_id]

        if action_type == ActionType.WAIT:
            paid = bool(self._rng.random() < BASE_ORGANIC_RESOLUTION_PROB)
            return StepResult(reply=ReplyIntent.PAID if paid else ReplyIntent.NO_REPLY, paid=paid)

        if action_type == ActionType.RETRY:
            paid = bool(self._rng.random() < _retry_success_prob(case))
            return StepResult(reply=ReplyIntent.PAID if paid else ReplyIntent.NO_REPLY, paid=paid)

        # customer-contact actions (NUDGE / NEGOTIATE / ESCALATE_HUMAN)
        n_contacts = self._contacts.get(case.case_id, 0)
        self._contacts[case.case_id] = n_contacts + 1

        tau = persuadability(traits)
        pay_prob = np.clip(BASE_ORGANIC_RESOLUTION_PROB + tau, 0.0, 0.9)

        # annoyance accumulates faster for low-annoyance-threshold customers;
        # past that point, opt-out/dispute risk rises and pay probability decays
        annoyance_capacity = 1 + 3 * traits.annoyance_threshold
        overcontacted = max(0, n_contacts - annoyance_capacity)
        pay_prob = float(np.clip(pay_prob - 0.05 * overcontacted, 0.0, 0.9))
        opt_out_prob = BASE_OPT_OUT_PROB_PER_CONTACT * (1 + overcontacted) * (1.5 - traits.annoyance_threshold)
        dispute_prob = BASE_DISPUTE_PROB_PER_CONTACT * (1 + 4 * traits.dispute_propensity)
        promise_prob = BASE_PROMISE_TO_PAY_PROB_PER_CONTACT

        draw = float(self._rng.random())
        cumulative = 0.0
        for prob, reply in (
            (pay_prob, ReplyIntent.PAID),
            (opt_out_prob, ReplyIntent.OPT_OUT),
            (dispute_prob, ReplyIntent.DISPUTE),
            (promise_prob, ReplyIntent.PROMISE_TO_PAY),
        ):
            cumulative += prob
            if draw < cumulative:
                return StepResult(reply=reply, paid=(reply == ReplyIntent.PAID))
        return StepResult(reply=ReplyIntent.NO_REPLY, paid=False)


class EnvironmentListener:
    """Adapts a SimulationEnvironment to the Listener interface, so the
    unmodified agent loop can run against simulated outcomes. Also records
    which action actually resulted in payment, for batch ₹-recovery
    accounting (spec section 11) — the loop itself only cares about
    ReplyIntent, not rupees, so this is tracked here rather than forcing
    ledger/loop changes."""

    def __init__(self, environment: SimulationEnvironment):
        self.environment = environment
        self.paid_cases: set[str] = set()

    def listen(self, case: RecoveryCase, action_type: ActionType, attempt_index: int) -> ReplyIntent:
        result = self.environment.step(case, action_type, attempt_index)
        if result.paid:
            self.paid_cases.add(case.case_id)
        return result.reply
