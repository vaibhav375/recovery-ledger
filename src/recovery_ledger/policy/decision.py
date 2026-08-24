"""Decision policy (spec section 5.3 / 8.3). STUB: proposes a fixed, small
action sequence per case rather than real EV = Δp_pay × ₹amount − cost −
annoyance decisioning. The real version lands once the Tier 1 uplift
learners are transferred to the domain simulator (spec section 7.3) — this
stub exists so the end-to-end loop is real and runnable before that
transfer happens, per the project's rule 2 (the agent loop must work at
every commit, even with stub components inside it).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from pydantic import BaseModel

from recovery_ledger.diagnoser.diagnoser import Diagnosis
from recovery_ledger.events.actions import ActionType, StopReason
from recovery_ledger.events.schemas import (
    Channel,
    FailedPaymentCase,
    FailedSubscriptionCase,
    RecoveryCase,
)
from recovery_ledger.policy.churn import ChurnRiskModel, estimated_ltv
from recovery_ledger.policy.features import case_to_features
from recovery_ledger.policy.uplift.learners import UpliftModel


class ActionDecision(BaseModel):
    action_type: ActionType
    channel: Channel | None
    rationale: str
    # Why the policy chose to stop, when action_type is STOP. Without this the
    # agent loop has to guess, and it guessed wrong: every policy STOP was
    # attributed to NEGATIVE_EV, including the STOP returned on reaching
    # max_attempts. Budget exhaustion and "nothing has positive expected
    # value" are different terminations that the ledger must distinguish
    # (spec section 10, rules 3 and 4). Found 2026-08-24 — the last full run
    # reported 1,335 negative_ev stops and 0 budget_exhausted, which was an
    # artifact of that conflation, not a property of the policy.
    stop_reason: StopReason | None = None


class DecisionPolicy:
    """Fixed sequence: nudge once on the customer's preferred channel (SMS if
    unset), then a silent retry, then stop. Every real EV/budget/stopping
    constraint still runs downstream (the kernel and the loop's own stopping
    rules) — this only decides which action gets *proposed*."""

    max_attempts: int = 2

    def decide(self, case: RecoveryCase, diagnosis: Diagnosis, attempts_so_far: int) -> ActionDecision:
        if attempts_so_far >= self.max_attempts:
            return ActionDecision(
                action_type=ActionType.STOP, channel=None,
                stop_reason=StopReason.BUDGET_EXHAUSTED,
                rationale=f"stub policy: reached max_attempts={self.max_attempts}",
            )
        if attempts_so_far == 0:
            channel = case.customer.channel_pref or Channel.SMS
            return ActionDecision(
                action_type=ActionType.NUDGE, channel=channel,
                rationale=f"stub policy: first contact via {channel.value} ({diagnosis.taxonomy})",
            )
        return ActionDecision(
            action_type=ActionType.RETRY, channel=None,
            rationale="stub policy: second attempt, silent retry",
        )


CHANNEL_COST = {
    Channel.EMAIL: 0.1,
    Channel.WHATSAPP: 0.3,
    Channel.SMS: 0.5,
    Channel.VOICE: 5.0,
    Channel.RETRY: 0.0,
}

# Retry economics are treated as known operational statistics (spec section
# 3.2 cites these as published industry figures — "automated retries recover
# 15-20% of failed transactions", "subscription smart-retry recovers up to
# 57%") — unlike customer-level response to CONTACT, which is exactly the
# heterogeneous, unobservable-without-inference quantity the uplift model
# exists to learn (spec's N1/N2 novelty claims). These numbers are the same
# ones sim/environment.py uses internally, by design: this represents "what
# a real system would plausibly know" about retry success rates from
# historical data, not a leak of the simulator's hidden state.
RETRY_SUCCESS_PROB_SUBSCRIPTION = 0.35
RETRY_SUCCESS_PROB_HARD_DECLINE = 0.01
RETRY_SUCCESS_PROB_GENERIC = 0.17

# The rate at which a case resolves on its own with no action at all. Needed
# to convert RETRY's ABSOLUTE success probability into an INCREMENTAL one, so
# it can be compared like-for-like against the uplift model's tau_hat.
#
# This mattered: until 2026-08-24 the EV formula compared `tau_hat * amount`
# (incremental — CATE is P(pay|contact) - P(pay|no contact)) directly against
# `p_retry * amount` (absolute). Apples to oranges, in the same max(). It
# overvalued RETRY by base_resolution_prob * amount on every case — roughly a
# 40% overstatement of retry's relative worth at the mean case size — and the
# spec's formula is explicitly "Delta p_pay(action) x amount" (section 8.3),
# a delta for every action, not just for contact.
BASE_RESOLUTION_PROB = 0.05


def _retry_success_prob(case: RecoveryCase) -> float:
    """ABSOLUTE probability that a retry resolves the case."""
    if isinstance(case, FailedSubscriptionCase):
        return RETRY_SUCCESS_PROB_SUBSCRIPTION
    if isinstance(case, FailedPaymentCase) and case.is_hard_decline:
        return RETRY_SUCCESS_PROB_HARD_DECLINE
    return RETRY_SUCCESS_PROB_GENERIC


def _retry_incremental_prob(case: RecoveryCase) -> float:
    """INCREMENTAL lift from retrying, versus letting the case sit. This is
    the quantity comparable to the uplift model's tau_hat, and the one the
    EV formula must use."""
    return max(_retry_success_prob(case) - BASE_RESOLUTION_PROB, 0.0)


def _check_autonomy_limit(case: RecoveryCase, limit: float) -> ActionDecision | None:
    """Stopping rule 8 — amount exceeds the agent's autonomy limit, so the
    case goes to a human instead of being worked automatically."""
    if case.amount_at_risk > limit:
        return ActionDecision(
            action_type=ActionType.ESCALATE_HUMAN, channel=None,
            stop_reason=StopReason.HUMAN_ESCALATION_THRESHOLD,
            rationale=(
                f"amount at risk Rs {case.amount_at_risk:,.0f} exceeds the agent's "
                f"autonomy limit of Rs {limit:,.0f}; handing to a human"
            ),
        )
    return None


def _terminal_reason(
    case: RecoveryCase, tau_hat: float, retry_applicable: bool, *, ever_worthwhile: bool = True
) -> StopReason:
    """WHY this case is finished, once its attempt budget is spent.

    Design note, because this is subtle and a naive version of it caused a
    real regression. Do-not-disturb (rule 5) and hard decline (rule 9) are
    *classifications of why the agent never acted*, not licences to abandon
    the case the moment they are detected. Terminating early on them looks
    reasonable and is actively harmful: it forfeits the organic
    self-resolution the customer might reach anyway, which is precisely the
    bug that had the EV policy recovering 8.1% of overdue receivables
    against the do-nothing baseline's 13.9% (see ENGINEERING_LOG.md,
    2026-08-24).

    So the agent still waits out the window costlessly — contacting nobody,
    spending nothing — and only when the budget is spent does it record
    which of these three actually describes the case. The customer is never
    disturbed either way; the difference is purely whether the case keeps
    its free shot at resolving, and whether the ledger records a meaningful
    reason or a catch-all.
    """
    is_hard_decline = isinstance(case, FailedPaymentCase) and case.is_hard_decline

    # Rule 5 — negative predicted uplift: contact destroys value, so the
    # agent deliberately never contacted. Silent retry may still have been
    # admissible (spec: "never contact — may still allow silent retry"), so
    # this only describes the case when retry was not on the table.
    if tau_hat < 0 and not retry_applicable:
        return StopReason.DO_NOT_DISTURB

    # Rule 9 — non-retryable failure code, and no contact was worth making.
    if is_hard_decline and tau_hat <= 0:
        return StopReason.HARD_DECLINE

    # Rule 4 — nothing was ever worth doing. Distinct from rule 3: the agent
    # did not spend a budget, it declined to act at all because no admissible
    # action had positive expected value even on the first attempt. Expected
    # value is monotonically non-increasing in attempts (annoyance cost only
    # grows), so "not worthwhile at attempt 0" implies "never worthwhile".
    if not ever_worthwhile:
        return StopReason.NEGATIVE_EV

    # Rule 3 — the agent worked the case and ran out of attempts.
    return StopReason.BUDGET_EXHAUSTED


@dataclass
class EVDecisionPolicy:
    """EV(action | state) = delta_p_pay(action) x amount_at_risk
                            - channel_cost(action)
                            - lambda_annoyance x annoyance_cost(action, history)
       (spec section 8.3). Simplified from the full spec formula: no
       explicit lambda_churn x P(churn) x LTV term — modelling per-customer
       LTV would need assumptions this project has no basis to validate, so
       it's left out rather than invented. annoyance_cost is approximated
       as proportional to attempt count, since the policy cannot observe
       the simulator's true hidden annoyance state (nor could a real
       system observe a customer's true annoyance) — only that repeated
       contact carries rising expected cost.

    `uplift_model` must already be fitted (see
    experiments/tier2_simulation/run_batch.py for how it's trained: a
    T-learner from policy/uplift/learners.py — the same class validated in
    Tier 1 — fit on randomised-contact data generated by
    sim/environment.py)."""

    uplift_model: UpliftModel
    lambda_annoyance: float = 30.0
    max_attempts: int = 3
    # Above this amount the agent must hand off rather than act autonomously
    # (spec section 10, rule 8: "amount or sensitivity exceeds autonomy
    # limit"). Set deliberately high so it fires on genuinely large cases
    # rather than routinely.
    autonomy_limit_rupees: float = 25_000.0
    # The spec's lambda_churn term (section 8.3), previously omitted. The
    # model estimates the INCREMENTAL opt-out probability caused by
    # contacting; multiplied by the relationship value at stake, it prices
    # the downside of contact that a payment-only objective cannot see.
    #
    # This is defence in depth for novelty claim N2: avoiding
    # do-not-disturbs previously rested entirely on tau_hat being right, and
    # tau_hat correlates only ~0.35-0.42 with truth. Churn risk is an
    # independent signal (measured: true do-not-disturbs opt out 1.93x more
    # often when contacted), so two models must now both be wrong before a
    # do-not-disturb is contacted.
    #
    # Defaults to None, so behaviour is unchanged unless a caller opts in.
    churn_model: ChurnRiskModel | None = None
    # Chosen from a measured sweep, not picked by feel. Against lambda_churn=0
    # this cuts do-not-disturb contacts 20.1% -> 13.6% and raises incremental
    # rupees per contact 302 -> 450, for a 12% reduction in total incremental
    # recovery. It also strictly dominates lambda_churn=2.0, which reached the
    # same total recovery using 21% MORE contacts. Full curve in
    # experiments/tier2_simulation/REPORT.md.
    #
    # This is a stated policy choice, not an optimum: a merchant who prices
    # customer goodwill differently should set it differently, which is why it
    # is a parameter and the whole curve is published rather than one number.
    lambda_churn: float = 4.0

    def _churn_cost(self, case: RecoveryCase, features) -> float:
        """Expected value destroyed by contacting this customer."""
        if self.churn_model is None:
            return 0.0
        p_churn = float(self.churn_model.predict_incremental_churn(features)[0])
        return self.lambda_churn * p_churn * estimated_ltv(case)

    def _best_ev(self, case: RecoveryCase, tau_hat: float, *, attempt_index: int) -> float:
        """Best expected value available at a given attempt index. Used both
        to choose an action and, at the horizon, to tell "never worth acting"
        (rule 4) apart from "acted until the budget ran out" (rule 3)."""
        channel = case.customer.channel_pref or Channel.SMS
        ev_nudge = (
            tau_hat * case.amount_at_risk
            - CHANNEL_COST[channel]
            - self.lambda_annoyance * attempt_index
            - self._churn_cost(case, case_to_features(case).reshape(1, -1))
        )
        ev_retry = (
            _retry_incremental_prob(case) * case.amount_at_risk
            if isinstance(case, (FailedPaymentCase, FailedSubscriptionCase))
            else float("-inf")
        )
        return max(ev_nudge, ev_retry, 0.0 if attempt_index < 0 else float("-inf"))

    def decide(self, case: RecoveryCase, diagnosis: Diagnosis, attempts_so_far: int) -> ActionDecision:
        escalation = _check_autonomy_limit(case, self.autonomy_limit_rupees)
        if escalation is not None:
            return escalation

        features = case_to_features(case).reshape(1, -1)
        tau_hat = float(self.uplift_model.predict_cate(features)[0])
        retry_available = isinstance(case, (FailedPaymentCase, FailedSubscriptionCase))

        if attempts_so_far >= self.max_attempts:
            reason = _terminal_reason(
                case, tau_hat, retry_available,
                ever_worthwhile=self._best_ev(case, tau_hat, attempt_index=0) > 0,
            )
            return ActionDecision(
                action_type=ActionType.STOP, channel=None, stop_reason=reason,
                rationale=f"EV policy: terminal reason {reason.value} (max_attempts={self.max_attempts})",
            )

        channel = case.customer.channel_pref or Channel.SMS
        ev_nudge = (
            tau_hat * case.amount_at_risk
            - CHANNEL_COST[channel]
            - self.lambda_annoyance * attempts_so_far
            - self._churn_cost(case, features)
        )

        retry_applicable = isinstance(case, (FailedPaymentCase, FailedSubscriptionCase))
        ev_retry = _retry_incremental_prob(case) * case.amount_at_risk if retry_applicable else float("-inf")

        ev_wait = 0.0  # the reference point every other action must beat

        best_action, best_ev = max(
            [(ActionType.NUDGE, ev_nudge), (ActionType.RETRY, ev_retry), (ActionType.WAIT, ev_wait)],
            key=lambda pair: pair[1],
        )

        if best_ev <= 0:
            # WAIT, not STOP. These are NOT equivalent, and conflating them
            # was a real bug (found 2026-08-24): STOP abandons the case and
            # forfeits the organic self-resolution the customer might have
            # reached anyway, while WAIT costs nothing, contacts nobody, and
            # keeps the case eligible for that free recovery. Before this
            # fix the EV policy recovered only 8.1% of overdue receivables
            # against the do-nothing baseline's 13.9% — i.e. it was doing
            # actively WORSE than not having an agent at all on that segment,
            # purely by giving up on cases too eagerly.
            #
            # Terminating on genuinely exhausted budget is still correct and
            # still happens, via max_attempts above.
            return ActionDecision(
                action_type=ActionType.WAIT, channel=None,
                rationale=(
                    f"EV policy: no action beats waiting "
                    f"(best was {best_action.value} at EV={best_ev:.2f}); "
                    f"waiting is free and preserves organic recovery"
                ),
            )
        if best_action == ActionType.NUDGE:
            return ActionDecision(
                action_type=ActionType.NUDGE, channel=channel,
                rationale=f"EV policy: tau_hat={tau_hat:.4f}, EV={best_ev:.2f}",
            )
        return ActionDecision(
            action_type=ActionType.RETRY, channel=None,
            rationale=f"EV policy: retry EV={best_ev:.2f} (p_success={_retry_success_prob(case):.2f})",
        )


@dataclass
class DoNothingPolicy:
    """The randomised no-contact holdout arm (spec section 11.1) — always
    proposes WAIT, for the same number of attempt-windows a contact policy
    would have used, then stops. This is what makes an "incremental"
    recovery number meaningful rather than an artifact of comparing
    different-length observation periods: it's the counterfactual every
    other policy is measured against, over the same horizon."""

    max_attempts: int = 3

    def decide(self, case: RecoveryCase, diagnosis: Diagnosis, attempts_so_far: int) -> ActionDecision:
        if attempts_so_far >= self.max_attempts:
            return ActionDecision(
                action_type=ActionType.STOP, channel=None,
                stop_reason=StopReason.BUDGET_EXHAUSTED,
                rationale=f"holdout: reached max_attempts={self.max_attempts}",
            )
        return ActionDecision(
            action_type=ActionType.WAIT, channel=None,
            rationale="holdout: no-contact baseline",
        )


@dataclass
class LookaheadEVDecisionPolicy:
    """EV policy that values the WHOLE REMAINING ATTEMPT SEQUENCE rather
    than one greedy step.

    Why this exists: the 5-baseline comparison (2026-08-24) found the
    greedy `EVDecisionPolicy` recovering *less* than blindly contacting
    everyone. Investigation ruled out annoyance-cost miscalibration
    (sweeping `lambda_annoyance` to 0 barely moved recovery) and pointed at
    the greedy formulation itself: `sim/environment.py` treats each contact
    as close to an independent trial, so persistence compounds. A policy
    that asks only "is one more nudge worth it *right now*" gives up on
    cases where the sequence of remaining attempts is collectively
    worthwhile — and does so more often when `tau_hat` is noisy, which it
    is (~0.4 correlation with truth, not 1.0).

    The fix is a small finite-horizon dynamic program over the remaining
    attempt budget, solved by backward induction:

        V(k) = max over admissible actions a of
                   [ immediate_value(a, k) + (1 - p_resolve(a)) * V(k+1) ]
        V(max_attempts) = 0        # horizon: no attempts left

    `immediate_value` is the same incremental-EV expression the greedy
    policy uses (Δp × ₹amount − channel cost − annoyance cost). The
    `(1 - p_resolve)` factor is what the greedy version was missing: an
    action's value includes the option to keep working the case if it
    doesn't resolve now.

    STATED ASSUMPTION: `p_resolve` for a contact is approximated as
    `base_resolution_prob + tau_hat`, since the uplift model estimates the
    *incremental* effect (CATE) and not an absolute payment probability.
    That approximation is the weakest link in this policy and is why
    `base_resolution_prob` is an explicit parameter rather than a hidden
    constant — a real deployment would estimate absolute payment
    probability directly, alongside the CATE.
    """

    uplift_model: UpliftModel
    lambda_annoyance: float = 30.0
    max_attempts: int = 3
    base_resolution_prob: float = 0.05
    autonomy_limit_rupees: float = 25_000.0
    churn_model: ChurnRiskModel | None = None
    lambda_churn: float = 4.0

    def _churn_cost(self, case: RecoveryCase, features) -> float:
        if self.churn_model is None:
            return 0.0
        p_churn = float(self.churn_model.predict_incremental_churn(features)[0])
        return self.lambda_churn * p_churn * estimated_ltv(case)

    def _immediate_and_resolve(
        self, case: RecoveryCase, tau_hat: float, attempt_index: int
    ) -> dict[ActionType, tuple[float, float, Channel | None]]:
        """(immediate incremental value, P(resolve), channel) per action."""
        channel = case.customer.channel_pref or Channel.SMS
        nudge_value = (
            tau_hat * case.amount_at_risk
            - CHANNEL_COST[channel]
            - self.lambda_annoyance * attempt_index
            - self._churn_cost(case, case_to_features(case).reshape(1, -1))
        )
        nudge_resolve = float(min(max(self.base_resolution_prob + tau_hat, 0.0), 0.95))

        options: dict[ActionType, tuple[float, float, Channel | None]] = {
            ActionType.NUDGE: (nudge_value, nudge_resolve, channel),
            ActionType.WAIT: (0.0, self.base_resolution_prob, None),
        }
        if isinstance(case, (FailedPaymentCase, FailedSubscriptionCase)):
            p_retry = _retry_success_prob(case)
            # value uses the INCREMENTAL lift; p_resolve (the continuation
            # discount) correctly uses the ABSOLUTE probability, since what
            # ends the case is the case actually resolving.
            options[ActionType.RETRY] = (
                _retry_incremental_prob(case) * case.amount_at_risk, p_retry, None,
            )
        return options

    def _solve(self, case: RecoveryCase, tau_hat: float, attempts_so_far: int):
        """Backward induction from the horizon back to the current attempt.
        Returns (best_action, channel, value_of_acting_now)."""
        future_value = 0.0
        best_at_current: tuple[ActionType, Channel | None, float] | None = None

        for k in range(self.max_attempts - 1, attempts_so_far - 1, -1):
            options = self._immediate_and_resolve(case, tau_hat, k)
            best_action, best_channel, best_value = ActionType.STOP, None, 0.0
            for action, (immediate, p_resolve, channel) in options.items():
                total = immediate + (1.0 - p_resolve) * future_value
                if total > best_value:
                    best_action, best_channel, best_value = action, channel, total
            future_value = best_value
            if k == attempts_so_far:
                best_at_current = (best_action, best_channel, best_value)

        assert best_at_current is not None
        return best_at_current

    def decide(self, case: RecoveryCase, diagnosis: Diagnosis, attempts_so_far: int) -> ActionDecision:
        escalation = _check_autonomy_limit(case, self.autonomy_limit_rupees)
        if escalation is not None:
            return escalation
        features = case_to_features(case).reshape(1, -1)
        tau_hat = float(self.uplift_model.predict_cate(features)[0])
        retry_available = isinstance(case, (FailedPaymentCase, FailedSubscriptionCase))

        if attempts_so_far >= self.max_attempts:
            _, _, value_from_start = self._solve(case, tau_hat, 0)
            reason = _terminal_reason(
                case, tau_hat, retry_available, ever_worthwhile=value_from_start > 0,
            )
            return ActionDecision(
                action_type=ActionType.STOP, channel=None, stop_reason=reason,
                rationale=f"lookahead EV: terminal reason {reason.value} (max_attempts={self.max_attempts})",
            )

        action, channel, value = self._solve(case, tau_hat, attempts_so_far)

        if action == ActionType.STOP or value <= 0:
            # WAIT rather than STOP, for the same reason as EVDecisionPolicy —
            # waiting is free and preserves organic recovery, abandoning the
            # case throws it away.
            return ActionDecision(
                action_type=ActionType.WAIT, channel=None,
                rationale=(
                    f"lookahead EV: no remaining action sequence beats waiting "
                    f"(tau_hat={tau_hat:.4f}); waiting is free"
                ),
            )
        return ActionDecision(
            action_type=action, channel=channel,
            rationale=f"lookahead EV: tau_hat={tau_hat:.4f}, sequence value={value:.2f}",
        )


@dataclass
class RandomTargetingPolicy:
    """Contacts a RANDOM subset of cases, at a chosen rate, ignoring every
    signal. This is the control that makes the efficiency claim falsifiable.

    "Our policy gets the same recovery as mass-contact with 61% fewer
    contacts" is only evidence of good *targeting* if a policy that contacts
    the same reduced number of cases AT RANDOM does measurably worse. If
    random targeting at matched volume performs just as well, then the
    result says something about diminishing returns to contact volume and
    nothing whatsoever about the uplift model — a distinction worth being
    able to prove rather than assert (added 2026-08-24).

    Seeded per case id so the choice is deterministic and reproducible.
    """

    contact_rate: float = 0.5
    max_attempts: int = 3
    seed: int = 0
    default_channel: Channel = Channel.SMS

    def _contacts_this_case(self, case: RecoveryCase) -> bool:
        digest = hashlib.sha256(f"{self.seed}:{case.case_id}".encode()).digest()
        draw = int.from_bytes(digest[:8], "big") / 2**64
        return draw < self.contact_rate

    def decide(self, case: RecoveryCase, diagnosis: Diagnosis, attempts_so_far: int) -> ActionDecision:
        if attempts_so_far >= self.max_attempts:
            return ActionDecision(
                action_type=ActionType.STOP, channel=None,
                stop_reason=StopReason.BUDGET_EXHAUSTED,
                rationale=f"random targeting: reached max_attempts={self.max_attempts}",
            )
        if not self._contacts_this_case(case):
            return ActionDecision(
                action_type=ActionType.WAIT, channel=None,
                rationale=f"random targeting: case not selected (rate={self.contact_rate})",
            )
        channel = case.customer.channel_pref or self.default_channel
        return ActionDecision(
            action_type=ActionType.NUDGE, channel=channel,
            rationale=f"random targeting: case selected at random (rate={self.contact_rate})",
        )


@dataclass
class BlastEveryonePolicy:
    """Contact every case, every attempt, no discrimination between
    persuadables and do-not-disturbs — the naive "when in doubt, reach out"
    policy this project's whole thesis is that you can beat (spec section
    11.3, baseline 2)."""

    max_attempts: int = 3
    default_channel: Channel = Channel.SMS

    def decide(self, case: RecoveryCase, diagnosis: Diagnosis, attempts_so_far: int) -> ActionDecision:
        if attempts_so_far >= self.max_attempts:
            return ActionDecision(
                action_type=ActionType.STOP, channel=None,
                stop_reason=StopReason.BUDGET_EXHAUSTED,
                rationale=f"blast-everyone: reached max_attempts={self.max_attempts}",
            )
        channel = case.customer.channel_pref or self.default_channel
        return ActionDecision(
            action_type=ActionType.NUDGE, channel=channel,
            rationale="blast-everyone: always contact, no targeting",
        )


class RazorpayCurrentPolicy:
    """A single automated retry, then hand the case back to the merchant
    (spec section 3.3): "Razorpay Subscriptions currently retries a failed
    recurring charge once... then moves the subscription to halted."
    Modelled as: one silent RETRY, then STOP — everything after that first
    retry is, by design, unowned by this policy (spec section 11.3,
    baseline 3)."""

    def decide(self, case: RecoveryCase, diagnosis: Diagnosis, attempts_so_far: int) -> ActionDecision:
        if attempts_so_far == 0:
            return ActionDecision(
                action_type=ActionType.RETRY, channel=None,
                rationale="razorpay-current: single automated retry",
            )
        return ActionDecision(
            action_type=ActionType.STOP, channel=None,
            rationale="razorpay-current: halted after first retry, handed back to merchant",
        )


@dataclass
class RulesBasedDunningPolicy:
    """The industry-standard fixed cadence — a 3-contact ladder regardless
    of any signal about who's actually persuadable (spec section 11.3,
    baseline 4: "fixed 3-email ladder — the industry standard")."""

    max_attempts: int = 3
    default_channel: Channel = Channel.EMAIL

    def decide(self, case: RecoveryCase, diagnosis: Diagnosis, attempts_so_far: int) -> ActionDecision:
        if attempts_so_far >= self.max_attempts:
            return ActionDecision(
                action_type=ActionType.STOP, channel=None,
                rationale="rules-based dunning: fixed 3-contact ladder complete",
            )
        channel = case.customer.channel_pref or self.default_channel
        return ActionDecision(
            action_type=ActionType.NUDGE, channel=channel,
            rationale=f"rules-based dunning: fixed contact {attempts_so_far + 1}/{self.max_attempts}",
        )
