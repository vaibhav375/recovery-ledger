"""Typed wrappers around econml's CATE meta-learners.

Every learner here answers one question: for a case with features X, how much
does contacting it (T=1) change the probability of payment/response, relative
to not contacting it (T=0)? That's the conditional average treatment effect
(CATE), estimated four different ways so they can be compared against each
other and against a doubly-robust off-policy estimate of the same quantity
(see policy/ope/estimators.py and experiments/tier1_criteo/).

Binary outcomes are modelled as regression targets in {0, 1} for the
meta-learners (S/T/X), which is the standard econml convention for CATE
estimation on binary outcomes — the fitted "predictions" are calibrated
probabilities, not hard classes. CausalForestDML instead uses
`discrete_outcome=True`, which handles this natively.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
from econml.dml import CausalForestDML
from econml.metalearners import SLearner, TLearner, XLearner
from numpy.typing import NDArray
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import LogisticRegression


class UpliftModel(Protocol):
    """Common interface every uplift learner below satisfies."""

    def fit(self, X: NDArray, T: NDArray, Y: NDArray) -> "UpliftModel": ...

    def predict_cate(self, X: NDArray) -> NDArray[np.float64]:
        """Estimated E[Y|T=1,X] - E[Y|T=0,X] per row of X."""
        ...


@dataclass
class SLearnerModel:
    """Single model, treatment as a feature. Fastest, weakest at capturing
    heterogeneous effects (treatment can get regularised away)."""

    random_state: int = 0
    _est: SLearner | None = None

    def fit(self, X: NDArray, T: NDArray, Y: NDArray) -> "SLearnerModel":
        base = GradientBoostingRegressor(random_state=self.random_state, n_estimators=100)
        self._est = SLearner(overall_model=base)
        self._est.fit(Y, T, X=X)
        return self

    def predict_cate(self, X: NDArray) -> NDArray[np.float64]:
        assert self._est is not None, "call fit() first"
        return np.asarray(self._est.effect(X), dtype=np.float64)


@dataclass
class TLearnerModel:
    """Two independent models, one per arm. Simple, no shared statistical
    strength across arms, can overfit the minority arm."""

    random_state: int = 0
    _est: TLearner | None = None

    def fit(self, X: NDArray, T: NDArray, Y: NDArray) -> "TLearnerModel":
        base = GradientBoostingRegressor(random_state=self.random_state, n_estimators=100)
        self._est = TLearner(models=base)
        self._est.fit(Y, T, X=X)
        return self

    def predict_cate(self, X: NDArray) -> NDArray[np.float64]:
        assert self._est is not None, "call fit() first"
        return np.asarray(self._est.effect(X), dtype=np.float64)


@dataclass
class XLearnerModel:
    """T-learner plus a cross-arm imputation step; designed for exactly the
    imbalanced-treatment-ratio setting this project's data has (Criteo is
    0.85 treated; recovery contact policies are typically contact-minority
    too, once budget constraints bind)."""

    random_state: int = 0
    _est: XLearner | None = None

    def fit(self, X: NDArray, T: NDArray, Y: NDArray) -> "XLearnerModel":
        base = GradientBoostingRegressor(random_state=self.random_state, n_estimators=100)
        propensity = LogisticRegression(max_iter=1000)
        self._est = XLearner(models=base, propensity_model=propensity)
        self._est.fit(Y, T, X=X)
        return self

    def predict_cate(self, X: NDArray) -> NDArray[np.float64]:
        assert self._est is not None, "call fit() first"
        return np.asarray(self._est.effect(X), dtype=np.float64)


@dataclass
class CausalForestModel:
    """Honest random forest of local treatment-effect estimates (Wager &
    Athey). The only learner here with built-in confidence intervals per
    prediction, at higher computational cost."""

    random_state: int = 0
    n_estimators: int = 200
    _est: CausalForestDML | None = None

    def fit(self, X: NDArray, T: NDArray, Y: NDArray) -> "CausalForestModel":
        self._est = CausalForestDML(
            discrete_treatment=True,
            discrete_outcome=True,
            n_estimators=self.n_estimators,
            random_state=self.random_state,
            cv=3,
        )
        self._est.fit(Y, T, X=X)
        return self

    def predict_cate(self, X: NDArray) -> NDArray[np.float64]:
        assert self._est is not None, "call fit() first"
        return np.asarray(self._est.effect(X), dtype=np.float64).ravel()


ALL_LEARNERS: dict[str, type] = {
    "s_learner": SLearnerModel,
    "t_learner": TLearnerModel,
    "x_learner": XLearnerModel,
    "causal_forest": CausalForestModel,
}

@dataclass
class BootstrapEnsembleModel:
    """A CATE model that also reports how much it trusts itself.

    Every uplift model in this project returns a point estimate, and the EV
    policy has been treating those points as if they were facts. The disparity
    audit showed what that costs: on overdue receivables the model predicts a
    small *positive* uplift (tau_hat 0.023) where contact truly destroys value
    (-Rs 69 per case), and its correlation with truth there is 0.25. On the
    smallest invoices it predicts the *highest* uplift in the book with a
    correlation of 0.09 — confident precisely where it has no signal.

    A point estimate cannot express that. This fits `n_models` replicates of
    the same learner on bootstrap resamples of the training data and reports
    the spread across them as a per-case standard error, which is what lets a
    policy decline to act on a number it should not trust.

    Deliberately a wrapper rather than a new learner: it composes with
    whichever CATE model is already validated, and `predict_cate` returns the
    ensemble mean, so an existing caller that ignores the uncertainty gets
    sensible behaviour rather than a surprise.
    """

    base: type = TLearnerModel
    n_models: int = 20
    random_state: int = 0
    _members: list = field(default_factory=list)

    def fit(self, X: NDArray, T: NDArray, Y: NDArray) -> "BootstrapEnsembleModel":
        rng = np.random.default_rng(self.random_state)
        n = len(Y)
        self._members = []
        for k in range(self.n_models):
            idx = rng.integers(0, n, size=n)
            # A resample can land with one arm empty or a constant outcome,
            # which the base learner cannot fit. Skipping is correct — the
            # ensemble is smaller, not wrong — and silently returning a
            # half-fitted member would not be.
            if len(np.unique(T[idx])) < 2:
                continue
            try:
                self._members.append(
                    self.base(random_state=self.random_state + k).fit(X[idx], T[idx], Y[idx])
                )
            except Exception:  # noqa: BLE001 - a degenerate resample, not a bug
                continue
        if not self._members:
            raise RuntimeError("every bootstrap replicate failed to fit")
        return self

    def _all(self, X: NDArray) -> NDArray[np.float64]:
        return np.vstack([m.predict_cate(X) for m in self._members])

    def predict_cate(self, X: NDArray) -> NDArray[np.float64]:
        return np.asarray(self._all(X).mean(axis=0), dtype=np.float64)

    def predict_cate_std(self, X: NDArray) -> NDArray[np.float64]:
        """Per-case standard error of the CATE estimate across replicates."""
        return np.asarray(self._all(X).std(axis=0, ddof=1), dtype=np.float64)

    def predict_cate_with_std(self, X: NDArray) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """Mean and standard error from a single pass over the members.

        A policy needs both for the same row, and calling `predict_cate` then
        `predict_cate_std` runs every member twice. That is invisible in a
        batch call and expensive in the loop the EV policy actually runs:
        measured at 70.7 ms per case one row at a time against 0.235 ms per
        case batched — a 301x per-row overhead, doubled for no reason.
        """
        preds = self._all(X)
        return (
            np.asarray(preds.mean(axis=0), dtype=np.float64),
            np.asarray(preds.std(axis=0, ddof=1), dtype=np.float64),
        )

    def predict_cate_lcb(self, X: NDArray, k: float) -> NDArray[np.float64]:
        """tau_hat - k * se. The quantity a cautious policy should act on.

        k = 0 reproduces the point estimate exactly, so a sweep over k has the
        current behaviour as its origin rather than as a separate branch.
        """
        return self.predict_cate(X) - k * self.predict_cate_std(X)

