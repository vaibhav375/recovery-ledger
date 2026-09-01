"""The claims registry: pre-registration as a mechanism, not a habit.

This project's discipline is to fix a rule before a run and report the outcome
whichever way it falls. That discipline is currently kept by hand, in eight
separate experiment scripts, and the only thing stopping a future run from
quietly reporting the flattering half is somebody remembering. A habit nobody
can check is a claim about the author rather than about the work.

Every pre-registered claim is declared here once: what is asserted, the rule
that was fixed before the run, the artifact its verdict is read from, and the
phrases that may not appear in the published documents if the evidence did not
support it.

`tests/test_claims_registry.py` then holds three lines that good intentions
cannot:

  - a registered claim must resolve against a real artifact field;
  - an artifact carrying a pre-registered rule must be registered, so a new
    experiment cannot slip a rule past by not mentioning it;
  - a claim the evidence REFUTED or left UNRESOLVED may not be asserted as
    established anywhere in RESULTS.md, README.md or PROJECT_STATE.md.

The third is the one worth having. This repo's worst near-miss was publishing
"strictly dominates" from a run that no longer reproduced — prose that had
drifted from its own evidence with an artifact sitting right there. That is
exactly the shape this catches, and it catches it mechanically.

Status is derived from the artifact, never written here. The registry says
where to look and what would count; the run says what happened.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Sequence


class Status(str, Enum):
    HELD = "HELD"
    REFUTED = "REFUTED"
    UNRESOLVED = "UNRESOLVED"
    MISSING = "MISSING"          # the artifact field named here does not exist


@dataclass(frozen=True)
class Claim:
    id: str
    statement: str
    artifact: str
    verdict_path: str
    #: values at `verdict_path` that mean the claim held. Everything else is
    #: read through `unresolved_values` and then treated as refuted.
    held_values: tuple[Any, ...] = (True,)
    unresolved_values: tuple[Any, ...] = ()
    #: phrases that must NOT appear in the published documents unless this
    #: claim held. Empty means the claim carries no prose commitment.
    forbidden_when_not_held: tuple[str, ...] = ()
    note: str = ""
    status: Status = Status.MISSING
    observed: Any = None

    def resolved(self, observed: Any, missing: bool) -> "Claim":
        if missing:
            status = Status.MISSING
        elif observed in self.held_values:
            status = Status.HELD
        elif observed in self.unresolved_values:
            status = Status.UNRESOLVED
        elif isinstance(observed, str) and observed.upper().startswith("UNRESOLVED"):
            status = Status.UNRESOLVED
        elif isinstance(observed, str) and observed.upper().startswith("INCONCLUSIVE"):
            status = Status.UNRESOLVED
        else:
            status = Status.REFUTED
        return Claim(**{**self.__dict__, "status": status, "observed": observed})


_MISSING = object()


def _dig(blob: Any, path: str) -> Any:
    cur = blob
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return _MISSING
    return cur


# ── The registry ─────────────────────────────────────────────────────────
#
# Order is the order these were established, which is also roughly the order a
# reader meets them. Nothing here records an outcome; every status comes from
# the artifact at read time.

REGISTRY: tuple[Claim, ...] = (
    Claim(
        id="N2.dnd-signal",
        statement="Do-not-disturbs opt out more than everyone else when contacted, "
                  "so churn risk is a signal independent of predicted uplift.",
        artifact="experiments/dnd_signal/results_dnd_signal.json",
        verdict_path="effect_excludes_one",
        forbidden_when_not_held=("independent of predicted uplift",),
        note="The supporting signal for N2. Published at 1.29x after the "
             "original 1.93x was found to be a single small-sample draw.",
    ),
    Claim(
        id="calibration.ranking",
        statement="The uplift model's top decile realises more uplift than its "
                  "bottom decile, in every draw.",
        artifact="experiments/uplift_calibration/results_uplift_calibration.json",
        verdict_path="verdict.ranking_holds",
        forbidden_when_not_held=("The ranking is real",),
    ),
    Claim(
        id="calibration.monotone",
        statement="Decile uplift is monotone: Spearman >= 0.9 in every draw.",
        artifact="experiments/uplift_calibration/results_uplift_calibration.json",
        verdict_path="verdict.monotone_all_draws",
        forbidden_when_not_held=("the deciles are monotone",),
        note="Fails at 0.879 on one draw. Reported as failed rather than "
             "rounded up; near-monotone is tracked as the weaker claim.",
    ),
    Claim(
        id="regret.model-errors",
        statement="The model-judgement bucket contains a non-trivial count of "
                  "refusals of customers who would have paid, as the calibration "
                  "result requires.",
        artifact="experiments/regret/results_regret.json",
        verdict_path="prediction.holds",
        forbidden_when_not_held=("corroborate",),
    ),
    Claim(
        id="regret.cost-disagreement",
        statement="The counterfactual's cost-side disagreement with the model-based "
                  "estimate is a replicated finding.",
        artifact="experiments/regret/results_regret.json",
        # The verdict string, not the boolean: `replicates: false` collapses
        # "did not replicate" and "came out mixed" into one value, and this one
        # came out mixed. Reading the string keeps UNRESOLVED distinct from
        # REFUTED, which is the whole distinction the rule was written to draw.
        verdict_path="disagreement_replication.verdict",
        held_values=("REPLICATES",),
        forbidden_when_not_held=("disagree by more than sampling variance",),
        note="Outside the interval in 3 of 6 draws. Unresolved, and published "
             "as unresolved — the limitation itself did not replicate.",
    ),
    Claim(
        id="dr.cross-fitting",
        statement="DR's low reading on Criteo is caused by cross-fitting starving "
                  "the 15% minority arm, so more folds should shrink the gap.",
        artifact="experiments/tier1_criteo/results_dr_foldsweep.json",
        verdict_path="verdict",
        held_values=("CONFIRMED",),
        unresolved_values=("UNRESOLVED",),
        forbidden_when_not_held=("cross-fitting is the cause",),
        note="Refuted: coverage and mean gap are flat across a 10x fold range.",
    ),
    Claim(
        id="N6.detection-latency",
        statement="Detection latency is claimable: the detector fires in every draw "
                  "at the largest effect size, reported with its false-alarm rate.",
        artifact="experiments/fleet/results_fleet_latency.json",
        verdict_path="claimable",
        forbidden_when_not_held=("median latency",),
    ),
    Claim(
        id="tier1b.real-money-effect",
        statement="Contact produces incremental revenue, measured on a real "
                  "randomised experiment with real dollars rather than in the "
                  "simulator.",
        artifact="experiments/tier1_revenue/results_revenue.json",
        verdict_path="effect.excludes_zero",
        forbidden_when_not_held=("grounded outside its own simulator",),
        note="The only money figure in this repo not produced by its own "
             "generator: $424 per 1,000 customers, interval excluding zero.",
    ),
    Claim(
        id="tier1b.targeting-on-real-money",
        statement="Targeting beats matched-volume random targeting on real "
                  "money, not only in simulation.",
        artifact="experiments/tier1_revenue/results_revenue.json",
        verdict_path="targeting.paired_interval_excludes_zero",
        forbidden_when_not_held=("targeting beats random on real money",),
        note="Not established. Three estimators agree on the sign - all the "
             "registered rule asked for - but the paired interval on the "
             "difference covers zero. The rule was weaker than the question "
             "and is left as registered, with the interval reported beside it.",
    ),
    Claim(
        id="lambda.dominance",
        statement="lambda_churn = 4.0 strictly dominates 2.0.",
        artifact="experiments/churn_lambda/results_lambda_sweep.json",
        verdict_path="dominance_4_over_2.holds",
        forbidden_when_not_held=("strictly dominates",),
        note="The project's worst near-miss. Published as dominance from a run "
             "that no longer reproduced; it trades, it does not dominate.",
    ),
)


def load_claims(root: str | Path = ".") -> list[Claim]:
    """Resolve every registered claim against its artifact, now."""
    root = Path(root)
    out: list[Claim] = []
    cache: dict[str, Any] = {}
    for claim in REGISTRY:
        path = root / claim.artifact
        if claim.artifact not in cache:
            try:
                cache[claim.artifact] = json.loads(path.read_text())
            except Exception:
                cache[claim.artifact] = _MISSING
        blob = cache[claim.artifact]
        observed = _MISSING if blob is _MISSING else _dig(blob, claim.verdict_path)
        out.append(claim.resolved(
            None if observed is _MISSING else observed, observed is _MISSING))
    return out


def render(claims: Sequence[Claim]) -> str:
    """The registry as a table, for CLAIMS.md."""
    by = {s: [c for c in claims if c.status is s] for s in Status}
    lines = [
        "# Claims registry",
        "",
        "Every claim this project pre-registered, the rule fixed before the run,",
        "and what the evidence said. Generated by `make claims` from the",
        "artifacts themselves — nothing here is written by hand, so a claim",
        "cannot be recorded as holding by anyone's decision.",
        "",
        f"**{len(by[Status.HELD])} held · {len(by[Status.REFUTED])} refuted · "
        f"{len(by[Status.UNRESOLVED])} unresolved**",
        "",
        "| claim | status | read from |",
        "|---|---|---|",
    ]
    for c in claims:
        lines.append(
            f"| **{c.id}** — {c.statement} | `{c.status.value}` "
            f"| `{c.artifact}` → `{c.verdict_path}` |"
        )
    lines.append("")
    for c in claims:
        if c.note:
            lines.append(f"- **{c.id}**: {c.note}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    claims = load_claims(Path(__file__).resolve().parents[2])
    root = Path(__file__).resolve().parents[2]
    (root / "CLAIMS.md").write_text(render(claims))
    (root / "claims.json").write_text(json.dumps(
        [{"id": c.id, "statement": c.statement, "artifact": c.artifact,
          "verdict_path": c.verdict_path, "status": c.status.value,
          "observed": c.observed, "note": c.note} for c in claims], indent=2))
    for c in claims:
        print(f"{c.status.value:<11} {c.id}")
    print(f"\nWrote {root / 'CLAIMS.md'} and {root / 'claims.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
