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

from dataclasses import dataclass
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
