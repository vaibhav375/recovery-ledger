"""Acting on a lower bound, and the ways that could quietly not happen.

`uncertainty_k` is the kind of knob that is easy to add and easy to have no
effect. If the model does not report a standard error, if the default is not
exactly the old behaviour, or if the bound is applied to the wrong side, the
sweep still produces a curve and the curve still looks plausible. These pin
each of those.
"""

from __future__ import annotations

import numpy as np
import pytest

from recovery_ledger.policy.decision import _acted_on_tau
from recovery_ledger.policy.uplift.learners import (
    BootstrapEnsembleModel,
    TLearnerModel,
)


@pytest.fixture(scope="module")
def fitted():
    rng = np.random.default_rng(0)
    n = 600
    X = rng.normal(size=(n, 4))
    T = rng.integers(0, 2, size=n)
    # A real effect on the first feature, nothing on the rest.
    Y = (rng.random(n) < np.clip(0.2 + 0.25 * T * (X[:, 0] > 0), 0, 1)).astype(float)
    return BootstrapEnsembleModel(base=TLearnerModel, n_models=6, random_state=0).fit(X, T, Y), X


# ── the ensemble reports uncertainty at all ──────────────────────────────

def test_ensemble_reports_a_positive_standard_error(fitted):
    model, X = fitted
    se = model.predict_cate_std(X)
    assert se.shape == (len(X),)
    assert np.all(se >= 0)
    assert se.max() > 0, "a bootstrap ensemble with zero spread everywhere is not an ensemble"


def test_ensemble_mean_is_a_usable_point_estimate(fitted):
    """`predict_cate` must stay the ensemble mean, so a caller that ignores
    uncertainty gets sensible behaviour rather than a surprise."""
    model, X = fitted
    members = np.vstack([m.predict_cate(X) for m in model._members])
    assert np.allclose(model.predict_cate(X), members.mean(axis=0))


def test_lower_bound_is_below_the_point_estimate_wherever_there_is_spread(fitted):
    model, X = fitted
    tau = model.predict_cate(X)
    lcb = model.predict_cate_lcb(X, k=1.0)
    se = model.predict_cate_std(X)
    assert np.all(lcb <= tau + 1e-12)
    assert np.allclose(tau - lcb, se)


@pytest.mark.parametrize("k", [0.5, 1.0, 2.0])
def test_more_caution_never_raises_the_acted_on_estimate(fitted, k):
    model, X = fitted
    assert np.all(model.predict_cate_lcb(X, k) <= model.predict_cate_lcb(X, 0.0) + 1e-12)


# ── the knob is wired, and its default is the old behaviour ──────────────

def test_k_zero_is_exactly_the_point_estimate(fitted):
    """The sweep's origin must be today's policy, not something near it —
    otherwise every reported improvement is measured against a baseline that
    was never deployed."""
    model, X = fitted
    row = X[:1]
    assert _acted_on_tau(model, row, 0.0) == pytest.approx(
        float(model.predict_cate(row)[0])
    )


def test_positive_k_actually_lowers_the_number_the_policy_acts_on(fitted):
    model, X = fitted
    row = X[:1]
    assert _acted_on_tau(model, row, 1.0) < _acted_on_tau(model, row, 0.0)


def test_a_model_without_a_standard_error_raises_rather_than_silently_ignoring_k():
    """The failure this prevents: a plain T-learner passed with k=1.5 would
    quietly behave exactly like k=0, and the whole sweep would be a flat line
    that looks like a finding."""
    rng = np.random.default_rng(1)
    X = rng.normal(size=(200, 3))
    T = rng.integers(0, 2, size=200)
    Y = (rng.random(200) < 0.3).astype(float)
    plain = TLearnerModel(random_state=0).fit(X, T, Y)

    assert _acted_on_tau(plain, X[:1], 0.0) == pytest.approx(
        float(plain.predict_cate(X[:1])[0])
    )
    with pytest.raises(TypeError, match="standard error"):
        _acted_on_tau(plain, X[:1], 1.0)


def test_ev_policies_default_to_the_point_estimate():
    """Adding the knob must not change any existing result."""
    from recovery_ledger.policy.decision import (
        EVDecisionPolicy,
        LookaheadEVDecisionPolicy,
    )

    for cls in (EVDecisionPolicy, LookaheadEVDecisionPolicy):
        assert cls.__dataclass_fields__["uncertainty_k"].default == 0.0


def test_uncertainty_rises_where_the_training_data_is_sparse():
    """The premise of the whole idea, tested on the mechanism that actually
    produces it. If the standard error carried no information about where the
    model is guessing, a lower bound would be a uniform shrink and the k-sweep
    would be measuring nothing but a threshold change.

    An earlier version of this test probed proximity to the effect's decision
    boundary and failed — correctly. Boundary proximity is not where a model
    is uncertain; on this data it is the *densest* region and has the lowest
    standard error of anywhere. Sparsity is the mechanism.
    """
    rng = np.random.default_rng(0)
    n = 1500
    # A dense bulk around 0 and a small far-off cluster near 6, leaving a
    # genuine data desert between them.
    x = np.concatenate([rng.normal(0, 1, size=n - 150), rng.normal(6, 0.3, size=150)])
    X = np.column_stack([x, rng.normal(size=n)])
    T = rng.integers(0, 2, size=n)
    Y = (rng.random(n) < np.clip(0.2 + 0.3 * T * (x > 0), 0, 1)).astype(float)
    model = BootstrapEnsembleModel(base=TLearnerModel, n_models=12, random_state=0).fit(X, T, Y)

    grid = np.column_stack([np.linspace(-3, 9, 13), np.zeros(13)])
    se = model.predict_cate_std(grid)
    density = np.array([np.mean(np.abs(x - g) < 0.75) for g in grid[:, 0]])

    assert np.corrcoef(density, se)[0, 1] < -0.3, (
        "the standard error does not rise where training data thins out, so it "
        "is not tracking what the policy is being asked to trust it for"
    )
    dense, sparse = density > 0.2, density < 0.05
    assert se[sparse].mean() > se[dense].mean()


def test_ensemble_survives_a_degenerate_resample():
    """A bootstrap resample can land with one arm empty. Skipping it leaves a
    smaller ensemble, which is correct; a half-fitted member would not be."""
    rng = np.random.default_rng(2)
    n = 120
    X = rng.normal(size=(n, 2))
    T = np.zeros(n, dtype=int)
    T[:4] = 1  # resamples will frequently miss the treated arm entirely
    Y = (rng.random(n) < 0.3).astype(float)
    model = BootstrapEnsembleModel(base=TLearnerModel, n_models=8, random_state=3).fit(X, T, Y)
    assert 0 < len(model._members) <= 8
    assert np.all(np.isfinite(model.predict_cate(X)))
