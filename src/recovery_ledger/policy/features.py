"""Case -> numeric feature vector, for both the uplift learner and the EV
policy. Deliberately only OBSERVABLE fields — nothing from
`sim.environment.LatentTraits` belongs here; that would let the "learner"
cheat by reading the answer key.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from recovery_ledger.events.schemas import Channel, Language, LossType, RecoveryCase

_LOSS_TYPES = list(LossType)
_LANGUAGES = list(Language)
_CHANNELS = list(Channel)

FEATURE_NAMES = (
    ["amount_at_risk", "is_b2b"]
    + [f"loss_type_{lt.value}" for lt in _LOSS_TYPES]
    + [f"language_{lang.value}" for lang in _LANGUAGES]
    + [f"channel_pref_{c.value}" for c in _CHANNELS]
    + ["channel_pref_unset"]
)


def case_to_features(case: RecoveryCase) -> NDArray[np.float64]:
    values: list[float] = [case.amount_at_risk, float(case.customer.is_b2b)]
    values.extend(float(case.loss_type == lt) for lt in _LOSS_TYPES)
    values.extend(float(case.customer.language_pref == lang) for lang in _LANGUAGES)
    values.extend(float(case.customer.channel_pref == c) for c in _CHANNELS)
    values.append(float(case.customer.channel_pref is None))
    return np.array(values, dtype=np.float64)


def cases_to_feature_matrix(cases: list[RecoveryCase]) -> NDArray[np.float64]:
    return np.vstack([case_to_features(c) for c in cases])
