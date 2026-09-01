"""Uplift by decile: does the CATE model's ranking survive contact with reality?

The correlation between predicted uplift and true persuadability (0.347, the
weakest number in this repo) is a diagnostic the simulator can hand you because
it knows the hidden trait. Nothing in production can. This module computes the
version a real deployment could compute: rank cases by predicted uplift, cut
into equal-sized bins, and inside each bin take the *randomised* contrast
between the contacted rows and the not-contacted rows.

Three properties make that the honest form of the chart:

- The contrast is always within a bin. Comparing a bin's treated mean against
  the whole population's control mean produces a monotone picture out of a
  worthless predictor, because the bins differ in baseline payment rate as well
  as in uplift.
- A bin missing either arm reports `None`, not zero. An undefined estimate that
  renders as a bar at zero is a lie the chart tells silently.
- Monotonicity is scored with a statistic that can come out negative, and the
  calibration slope with one that can come out flat. Both failure directions
  are reachable, and `tests/test_uplift_decile_calibration.py` reaches them.

`calibration_slope` regresses realised uplift on mean predicted uplift across
the bins. 1.0 means predictions are on the right scale; below 1.0 means the
model spreads its predictions wider than the effects it is predicting, which is
the failure that matters here — the policy contacts when `tau_hat * amount`
clears the message cost, so an over-confident tau_hat mis-sets that threshold
even when the ranking is fine.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class DecileBin:
    """One equal-sized bin of the predicted-uplift ranking, lowest first."""

    index: int
    n: int
    row_indices: NDArray[np.int64]
    n_treated: int
    n_control: int
    mean_predicted_uplift: float
    realised_uplift: float | None
    ci_low: float | None
    ci_high: float | None
    treated_outcome_rate: float | None
    control_outcome_rate: float | None


@dataclass(frozen=True)
class DecileCalibration:
    bins: list[DecileBin]
    spearman: float
    top_minus_bottom: float | None
    calibration_slope: float
    calibration_intercept: float
    overall_predicted: float
    overall_realised: float
    n_bins_undefined: int


def _spearman(x: NDArray, y: NDArray) -> float:
    """Rank correlation, computed here rather than pulled from scipy.stats so
    the tie handling is visible: bins are ranked by their own ordering, so ties
    only ever appear in the realised values."""
    def ranks(v: NDArray) -> NDArray:
        order = np.argsort(v, kind="stable")
        r = np.empty(len(v), dtype=float)
        r[order] = np.arange(len(v), dtype=float)
        # average ranks within tied groups
        for value in np.unique(v):
            tied = np.flatnonzero(v == value)
            if len(tied) > 1:
                r[tied] = r[tied].mean()
        return r

    rx, ry = ranks(x), ranks(y)
    if rx.std() == 0 or ry.std() == 0:
        return 0.0
    return float(np.corrcoef(rx, ry)[0, 1])


def uplift_by_decile(
    tau_hat: NDArray,
    treatment: NDArray,
    outcome: NDArray,
    *,
    n_bins: int = 10,
    n_boot: int = 1000,
    seed: int = 0,
) -> DecileCalibration:
    """Bin `tau_hat` into `n_bins` equal-sized bins and measure realised uplift.

    `treatment` must be a randomised 0/1 assignment over the same rows — the
    within-bin contrast is only a treatment effect if assignment is independent
    of the outcome. Bins are ordered lowest predicted uplift first.
    """
    tau_hat = np.asarray(tau_hat, dtype=float)
    treatment = np.asarray(treatment).astype(int)
    outcome = np.asarray(outcome, dtype=float)
    if not (len(tau_hat) == len(treatment) == len(outcome)):
        raise ValueError("tau_hat, treatment and outcome must be the same length")
    if len(tau_hat) < n_bins:
        raise ValueError(f"need at least {n_bins} rows for {n_bins} bins")

    rng = np.random.default_rng(seed)
    order = np.argsort(tau_hat, kind="stable")
    bins: list[DecileBin] = []

    for i, idx in enumerate(np.array_split(order, n_bins)):
        t_vals = outcome[idx][treatment[idx] == 1]
        c_vals = outcome[idx][treatment[idx] == 0]
        defined = len(t_vals) > 0 and len(c_vals) > 0
        point = float(t_vals.mean() - c_vals.mean()) if defined else None

        lo = hi = None
        if defined and n_boot > 0:
            boot = np.empty(n_boot)
            for b in range(n_boot):
                boot[b] = (
                    rng.choice(t_vals, size=len(t_vals), replace=True).mean()
                    - rng.choice(c_vals, size=len(c_vals), replace=True).mean()
                )
            lo, hi = (float(v) for v in np.quantile(boot, [0.025, 0.975]))

        bins.append(DecileBin(
            index=i,
            n=len(idx),
            row_indices=idx,
            n_treated=len(t_vals),
            n_control=len(c_vals),
            mean_predicted_uplift=float(tau_hat[idx].mean()),
            realised_uplift=point,
            ci_low=lo,
            ci_high=hi,
            treated_outcome_rate=float(t_vals.mean()) if len(t_vals) else None,
            control_outcome_rate=float(c_vals.mean()) if len(c_vals) else None,
        ))

    usable = [b for b in bins if b.realised_uplift is not None]
    predicted = np.array([b.mean_predicted_uplift for b in usable])
    realised = np.array([b.realised_uplift for b in usable])

    # A predictor with no spread has no slope to report. np.polyfit goes
    # singular on zero-variance input and raises LinAlgError, which would take
    # down the whole chart for a degenerate model — while _spearman right above
    # already returns 0.0 for the same input. Same input, same answer.
    if len(usable) >= 2 and float(np.std(predicted)) > 0:
        slope, intercept = (float(v) for v in np.polyfit(predicted, realised, 1))
        spearman = _spearman(predicted, realised)
    else:
        slope = intercept = spearman = 0.0

    top = bins[-1].realised_uplift
    bottom = bins[0].realised_uplift
    gap = float(top - bottom) if (top is not None and bottom is not None) else None

    treated_all, control_all = outcome[treatment == 1], outcome[treatment == 0]
    return DecileCalibration(
        bins=bins,
        spearman=spearman,
        top_minus_bottom=gap,
        calibration_slope=slope,
        calibration_intercept=intercept,
        overall_predicted=float(tau_hat.mean()),
        overall_realised=float(treated_all.mean() - control_all.mean()),
        n_bins_undefined=len(bins) - len(usable),
    )
