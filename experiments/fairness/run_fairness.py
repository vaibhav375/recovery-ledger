"""Who does this agent decide not to help?

The compliance kernel checks whether an *action* is permitted. Nothing in this
project so far checks whether the *policy* distributes its attention fairly.
Those are different questions, and the second one is not answered by passing
the first: an agent can refuse every illegal action and still systematically
decline to work Hindi-speaking customers' cases.

WHY THIS IS NOT SIMPLY "CONTACT EVERYONE EQUALLY"
-------------------------------------------------
In collections the harm runs both ways, and this experiment reports both
rather than picking whichever framing flatters the system.

  * Under-contact is **denied access to resolution**. A case the agent never
    works loses whatever chance the contact would have created. If two groups
    have the same predicted benefit from contact and one is contacted far
    less, the system is offering a service to one and withholding it from the
    other.
  * Over-contact is **a larger share of the pressure**. The RBI recovery norms
    exist because collection contact is a burden. A group contacted twice as
    often is carrying twice the burden.

Neither is automatically the violation. What would be a violation is a gap
with no basis — so the analysis below is built around one question:

    Is the difference in how groups are treated explained by a real
    difference in how much contact actually helps them?

CONDITIONING, AND WHY IT IS THE WHOLE ANALYSIS
----------------------------------------------
Raw contact-rate gaps prove nothing. The policy contacts on expected value,
which is predicted uplift times amount at risk, so a group with larger
invoices *should* be contacted more and that is not discrimination.

The informative comparison holds those constant. Within a decile of predicted
uplift — and then within predicted uplift crossed with amount — do groups
still get contacted at different rates? A gap that survives that conditioning
is not explained by anything the objective is entitled to use.

And because this is a simulator, one further question can be asked that no
production audit can ask: within the same conditioning cells, does *true*
persuadability differ across groups? If the treatment gap is large and the
true-benefit gap is zero, the model is inventing a difference. That check is
only available here, and it is the reason to run this in simulation at all.

Significance is by permutation — group labels shuffled within cells — because
the statistic is a max-minus-min over several groups and has no clean
parametric null.

MULTIPLE COMPARISONS, AND WHICH TEST THE CORRECTION BELONGS TO
--------------------------------------------------------------
Four segments times four tests is sixteen hypotheses, and at alpha = 0.05 that
is a coin-flip's chance of one false positive before any real effect exists.
An audit that hunts across segments and reports whichever one crossed 0.05 is
generating findings, not detecting them. The disparity test therefore uses a
Bonferroni-corrected threshold.

The *explanation* test does not, and applying the correction to both would
invert the protection it exists to give. A verdict of "unexplained" needs two
things: a treatment gap that is real, and no real difference in benefit to
account for it. Tightening the threshold on the second makes it harder to find
an explanation, so it makes crying wolf *easier* — the opposite of what a
correction is for. It happened: with the same correction on both, `loss_type`
was flagged as an unexplained disparity on a true-benefit p of 0.004 against a
corrected 0.0031, while the observed benefit gap was a very large +172 rupees.
That is a non-significant p being read as evidence of absence, at a threshold
chosen to make absence easier to conclude.

So: the disparity test must clear the corrected bar; the explanation test only
has to clear an ordinary 0.05. Both p-values are reported either way.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from recovery_ledger.diagnoser.diagnoser import CaseDiagnoser
from recovery_ledger.events.actions import ActionType
from recovery_ledger.listener.listener import ReplyIntent
from recovery_ledger.policy.churn import ChurnRiskModel, estimated_ltv
from recovery_ledger.policy.decision import CHANNEL_COST, EVDecisionPolicy
from recovery_ledger.events.schemas import Channel
from recovery_ledger.policy.features import cases_to_feature_matrix
from recovery_ledger.policy.uplift.learners import TLearnerModel
from recovery_ledger.sim.environment import (
    SimulationEnvironment,
    generate_population,
    persuadability,
)
from recovery_ledger.sim.generator import generate_cases

HERE = Path(__file__).parent
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
SEED = 20260823
EVAL_SEED = SEED + 5000  # disjoint from every other experiment's eval seed
LAMBDA_CHURN = 4.0
# Reaches the customer.
CONTACT_ACTIONS = {ActionType.NUDGE, ActionType.NEGOTIATE}
SCATTER_POINTS = 1200  # enough to show the cloud, small enough for data.json
# The agent did *something* for this case. The distinction matters: a failed
# subscription is worked by a silent RETRY 80% of the time, so measuring only
# customer contact reports those customers as neglected when the agent is in
# fact working them on the free channel. An audit that missed that would
# manufacture a disparity out of correct behaviour.
WORKED_ACTIONS = CONTACT_ACTIONS | {ActionType.RETRY, ActionType.ESCALATE_HUMAN}


# ── setup, shared with the other tier 2 experiments ──────────────────────

def train(n_train: int, seed: int):
    cases = generate_cases(n_train, seed=seed, now=NOW)
    traits = generate_population(cases, seed=seed)
    env = SimulationEnvironment(traits, seed=seed)
    rng = np.random.default_rng(seed)
    treatment = rng.integers(0, 2, size=n_train)
    paid = np.zeros(n_train)
    churned = np.zeros(n_train)
    for i, c in enumerate(cases):
        r = env.step(c, ActionType.NUDGE if treatment[i] else ActionType.WAIT, 0)
        paid[i] = float(r.paid)
        churned[i] = float(r.reply == ReplyIntent.OPT_OUT)
    X = cases_to_feature_matrix(cases)
    uplift = TLearnerModel(random_state=seed)
    uplift.fit(X, treatment, paid)
    churn = ChurnRiskModel().fit(X, treatment, churned, random_state=seed)
    return uplift, churn


def segments(cases) -> dict[str, np.ndarray]:
    """The groups this audit examines, and why each one.

    language  — the listener is measurably worse in Hindi and Hinglish than in
                English (95.2% gold-set accuracy overall, 100% en vs 92% hi).
                If model quality varies by language, so does the quality of
                every decision made for those customers.
    b2b       — business counterparties are a fifth of the book and get
                different treatment paths (negotiation, 43B(h)).
    amount    — the objective multiplies uplift by amount, so small invoices
                are structurally less worth contacting. That is defensible on
                its face and worth measuring anyway: it is how a system ends
                up ignoring the customers with least at stake.
    """
    return {
        "language": np.array([c.customer.language_pref.value for c in cases]),
        "b2b": np.array(["b2b" if c.customer.is_b2b else "b2c" for c in cases]),
        "amount_quartile": _quantile_labels(
            np.array([c.amount_at_risk for c in cases]), 4, "Q"
        ),
        "loss_type": np.array([type(c).__name__.replace("Case", "") for c in cases]),
    }


def _quantile_labels(values: np.ndarray, k: int, prefix: str) -> np.ndarray:
    edges = np.quantile(values, np.linspace(0, 1, k + 1)[1:-1])
    idx = np.searchsorted(edges, values, side="right")
    return np.array([f"{prefix}{i + 1}" for i in idx])


# ── the statistic ────────────────────────────────────────────────────────

def _cell_gap(labels: np.ndarray, outcome: np.ndarray, cells: np.ndarray) -> float:
    """Size-weighted mean, over cells, of the max-minus-min group rate.

    Cells with fewer than two represented groups contribute nothing: a gap
    cannot be measured where only one group is present, and treating that as
    zero would dilute the statistic toward "no disparity" exactly where the
    data is thinnest.
    """
    total, weighted = 0, 0.0
    for cell in np.unique(cells):
        mask = cells == cell
        rates = [
            float(outcome[mask & (labels == g)].mean())
            for g in np.unique(labels[mask])
            if (mask & (labels == g)).sum() >= 5
        ]
        if len(rates) < 2:
            continue
        n = int(mask.sum())
        weighted += n * (max(rates) - min(rates))
        total += n
    return weighted / total if total else 0.0


def permutation_p(labels, outcome, cells, *, n_perm: int, seed: int) -> dict:
    """Observed gap, the null distribution's mean, and the p-value.

    Labels are permuted *within* cells, so the null preserves the cell
    structure — it asks whether group membership carries information about
    treatment beyond what the conditioning variables already explain.

    `excess` is the number to read, not `observed`. A max-minus-min over
    several groups is bounded below by sampling noise and never lands near
    zero: with four language groups and thirty cells, shuffled labels alone
    produce an apparent gap larger than the raw unconditional one. Subtracting
    the null mean is what turns the statistic into something a reader can
    interpret as a size. The p-value was always valid — the null carries the
    same noise — but reporting `observed` as "the gap" would have been
    misleading, and it was, in the first version of this script.
    """
    observed = _cell_gap(labels, outcome, cells)
    rng = np.random.default_rng(seed)
    shuffled = labels.copy()
    null = np.empty(n_perm)
    for i in range(n_perm):
        for cell in np.unique(cells):
            mask = cells == cell
            shuffled[mask] = rng.permutation(labels[mask])
        null[i] = _cell_gap(shuffled, outcome, cells)
    hits = int(np.sum(null >= observed))
    exact = (hits + 1) / (n_perm + 1)
    return {
        "observed": round(float(observed), 4),
        "null_mean": round(float(null.mean()), 4),
        "excess": round(float(observed - null.mean()), 4),
        "p": round(exact, 4),
        # Verdicts are decided on this, not on the rounded `p`. Comparing a
        # 4-decimal p against a 5-decimal Bonferroni threshold can flip a
        # borderline call purely on rounding, which is not a basis for
        # declaring a disparity.
        "p_exact": exact,
    }


# ── the audit ────────────────────────────────────────────────────────────

def audit(n_train: int, n_eval: int, n_perm: int) -> dict:
    uplift, churn = train(n_train, SEED)
    cases = generate_cases(n_eval, seed=EVAL_SEED, now=NOW)
    traits = generate_population(cases, seed=EVAL_SEED)

    X = cases_to_feature_matrix(cases)
    tau_hat = uplift.predict_cate(X)
    tau_true = np.array([persuadability(traits[c.case_id]) for c in cases])

    policy = EVDecisionPolicy(uplift_model=uplift, churn_model=churn)
    diagnoser = CaseDiagnoser()
    proposed = [policy.decide(c, diagnoser.diagnose(c), 0).action_type for c in cases]
    contacted = np.array([int(a in CONTACT_ACTIONS) for a in proposed])
    worked = np.array([int(a in WORKED_ACTIONS) for a in proposed])

    env = SimulationEnvironment(traits, seed=EVAL_SEED)
    paid = np.zeros(n_eval)
    opted = np.zeros(n_eval)
    for i, c in enumerate(cases):
        r = env.step(c, ActionType.NUDGE if contacted[i] else ActionType.WAIT, 0)
        paid[i] = float(r.paid)
        opted[i] = float(r.reply == ReplyIntent.OPT_OUT)

    amounts = np.array([c.amount_at_risk for c in cases])
    value = np.array([
        paid[i] * cases[i].amount_at_risk
        - (CHANNEL_COST[cases[i].customer.channel_pref or Channel.SMS] if contacted[i] else 0.0)
        - LAMBDA_CHURN * opted[i] * estimated_ltv(cases[i])
        for i in range(n_eval)
    ])

    # Conditioning cells. Deciles of predicted uplift alone, and then crossed
    # with amount terciles — the two quantities the objective is entitled to
    # use.
    tau_decile = _quantile_labels(tau_hat, 10, "D")
    # Coarser for the joint conditioning: ten deciles crossed with three
    # amount bands leaves cells too thin to measure a rate in, and the gap
    # statistic then reports mostly noise. Quintiles x halves keeps ten cells
    # with enough cases per group to mean something.
    joint = np.array([
        f"{d}|{a}" for d, a in zip(
            _quantile_labels(tau_hat, 5, "D"), _quantile_labels(amounts, 2, "A")
        )
    ])
    # What contacting a group is actually worth: the objective is uplift TIMES
    # amount, so persuadability alone is the wrong yardstick for whether a
    # group deserves more attention. A B2B book with lower per-unit
    # persuadability and much larger invoices should be contacted more.
    true_benefit = tau_true * amounts

    seg_map = segments(cases)
    n_tests = 4 * len(seg_map)
    alpha = 0.05 / n_tests  # kept unrounded for the comparisons below

    # A downsampled scatter of what the model predicted against what was
    # true, with the decision it drove. This is the only place the project
    # publishes per-case predictions, and it is the frame the spec asks for at
    # 3:45 of the video: the negative-uplift quadrant. Deliberately a sample
    # rather than all 4,000 rows — the shape is the argument, and shipping the
    # full set would add a megabyte to data.json to draw the same cloud.
    rng_s = np.random.default_rng(SEED)
    take = rng_s.permutation(n_eval)[: min(SCATTER_POINTS, n_eval)]
    scatter = [
        {
            "tau_hat": round(float(tau_hat[i]), 4),
            "tau_true": round(float(tau_true[i]), 4),
            "contacted": int(contacted[i]),
        }
        for i in sorted(take.tolist())
    ]

    out = {"n_eval": n_eval, "n_train": n_train, "seed": SEED, "eval_seed": EVAL_SEED,
           "scatter_sample": scatter,
           "scatter_note": (
               "a random sample of the evaluation batch; tau_hat is the model's "
               "predicted uplift, tau_true the simulator's hidden persuadability, "
               "contacted the decision the policy actually took"
           ),
           "overall_contact_rate": round(float(contacted.mean()), 4),
           "uplift_correlation": round(float(np.corrcoef(tau_hat, tau_true)[0, 1]), 4),
           "n_permutations": n_perm,
           "n_hypotheses_tested": n_tests,
           "bonferroni_alpha": round(alpha, 5),
           "segments": {}}

    for seg_name, labels in seg_map.items():
        groups = {}
        for g in sorted(np.unique(labels)):
            m = labels == g
            groups[str(g)] = {
                "n": int(m.sum()),
                "contact_rate": round(float(contacted[m].mean()), 4),
                "worked_rate": round(float(worked[m].mean()), 4),
                "mean_tau_hat": round(float(tau_hat[m].mean()), 4),
                "mean_true_persuadability": round(float(tau_true[m].mean()), 4),
                "true_expected_value_of_contact": round(float(true_benefit[m].mean()), 2),
                "mean_amount": round(float(amounts[m].mean()), 2),
                "payment_rate": round(float(paid[m].mean()), 4),
                "opt_out_rate": round(float(opted[m].mean()), 4),
                "net_value_per_case": round(float(value[m].mean()), 2),
                # Is the model as good for this group as for the others? A
                # decision founded on a worse estimate is a worse decision,
                # even when the contact rate looks even-handed.
                "model_correlation": (
                    round(float(np.corrcoef(tau_hat[m], tau_true[m])[0, 1]), 4)
                    if m.sum() > 2 else None
                ),
            }

        rates = [v["contact_rate"] for v in groups.values()]
        raw_gap = max(rates) - min(rates)
        ratio = (min(rates) / max(rates)) if max(rates) > 0 else None

        by_tau = permutation_p(
            labels, contacted.astype(float), tau_decile, n_perm=n_perm, seed=SEED
        )
        by_joint = permutation_p(
            labels, contacted.astype(float), joint, n_perm=n_perm, seed=SEED + 1
        )
        # The check only a simulator can run: within the same cells, does the
        # benefit actually differ? `contacted` is what the policy did;
        # `true_benefit` is what it should have been responding to.
        by_truth = permutation_p(
            labels, true_benefit, joint, n_perm=n_perm, seed=SEED + 2
        )
        # Same conditioning, but on "was this case worked at all". A group can
        # look under-contacted and be fully served on a silent channel.
        by_worked = permutation_p(
            labels, worked.astype(float), joint, n_perm=n_perm, seed=SEED + 3
        )

        # Does the policy give more attention to the groups it is actually
        # worth contacting? Spearman across groups, so it reads ordering, not
        # magnitudes — with two groups it is +1 or -1 and says only "right way
        # round" or "backwards".
        #
        # DESCRIPTIVE ONLY. This is a rank correlation over two to four points.
        # It has essentially no statistical weight and no test is attached to
        # it; it is reported because a negative value is worth looking at, not
        # because a negative value demonstrates anything.
        contact_by_group = np.array([v["contact_rate"] for v in groups.values()])
        value_by_group = np.array([
            v["true_expected_value_of_contact"] for v in groups.values()
        ])
        alignment = float(np.corrcoef(
            np.argsort(np.argsort(contact_by_group)),
            np.argsort(np.argsort(value_by_group)),
        )[0, 1]) if len(groups) > 1 else None

        out["segments"][seg_name] = {
            "groups": groups,
            "raw_contact_gap": round(raw_gap, 4),
            "contact_rate_ratio_min_over_max": round(ratio, 4) if ratio else None,
            "conditional_on_predicted_uplift": by_tau,
            "conditional_on_uplift_and_amount": by_joint,
            "worked_at_all_conditional_on_uplift_and_amount": by_worked,
            "true_benefit_gap_in_same_cells": by_truth,
            "attention_aligned_with_true_value": (
                round(alignment, 3) if alignment is not None else None
            ),
            "attention_alignment_is_descriptive_only": True,
            # A treatment gap that survives conditioning while the true-benefit
            # gap does not is a difference the model invented. Stated as a rule
            # rather than left for a reader to assemble — and judged at the
            # corrected threshold, because twelve tests were run.
            # Disparity test at the corrected threshold; explanation test at
            # an ordinary 0.05. See the module docstring for why they differ.
            "unexplained": bool(
                by_joint["p_exact"] < alpha and by_truth["p_exact"] >= 0.05
            ),
            "unexplained_at_uncorrected_alpha": bool(
                by_joint["p_exact"] < 0.05 and by_truth["p_exact"] >= 0.05
            ),
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-train", type=int, default=5000)
    ap.add_argument("--n-eval", type=int, default=4000)
    ap.add_argument("--n-perm", type=int, default=2000)
    args = ap.parse_args()

    print(f"Auditing the deployed policy over {args.n_eval} cases "
          f"({args.n_perm} permutations)...\n")
    result = audit(args.n_train, args.n_eval, args.n_perm)
    print(f"{result['n_hypotheses_tested']} hypotheses tested; "
          f"Bonferroni threshold alpha = {result['bonferroni_alpha']}\n")

    for seg, data in result["segments"].items():
        print(f"── {seg} " + "─" * (58 - len(seg)))
        print(f"  {'group':20}{'n':>6}{'contact':>9}{'worked':>8}{'tau_hat':>9}"
              f"{'true EV':>10}{'corr':>7}{'net Rs':>9}")
        for g, v in data["groups"].items():
            corr = v["model_correlation"]
            print(f"  {g:20}{v['n']:>6}{v['contact_rate']:>9.3f}{v['worked_rate']:>8.3f}"
                  f"{v['mean_tau_hat']:>9.4f}{v['true_expected_value_of_contact']:>10.0f}"
                  f"{(f'{corr:.2f}' if corr is not None else '-'):>7}"
                  f"{v['net_value_per_case']:>9.0f}")
        j = data["conditional_on_uplift_and_amount"]
        t = data["true_benefit_gap_in_same_cells"]
        w = data["worked_at_all_conditional_on_uplift_and_amount"]
        print(f"  raw gap {data['raw_contact_gap']:.3f} | contact excess "
              f"{j['excess']:+.3f} (p={j['p']:.3f}) | worked excess "
              f"{w['excess']:+.3f} (p={w['p']:.3f}) | true-benefit excess "
              f"{t['excess']:+.1f} (p={t['p']:.3f}) | alignment "
              f"{data['attention_aligned_with_true_value']}")
        verdict = (
            "UNEXPLAINED DISPARITY" if data["unexplained"]
            else "unexplained only before correcting for 12 tests"
            if data["unexplained_at_uncorrected_alpha"]
            else "explained by the data"
        )
        print(f"  → {verdict}\n")

    (HERE / "results_fairness.json").write_text(json.dumps(result, indent=2))
    print(f"Wrote {HERE / 'results_fairness.json'}")


if __name__ == "__main__":
    main()
