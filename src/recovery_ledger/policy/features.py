"""Case -> numeric feature vector, for both the uplift learner and the EV
policy. Deliberately only OBSERVABLE fields — nothing from
`sim.environment.LatentTraits` belongs here; that would let the "learner"
cheat by reading the answer key.

Two encoding decisions here are deliberate and were arrived at by measuring,
not by assumption (2026-08-24, see ENGINEERING_LOG.md):

1. **Amount is log-transformed.** Raw amounts run ~66 to ~31,000 (mean
   ~3,300) while every other feature is a 0/1 indicator — a ~4,000x scale
   gap that upsets the linear/logistic models used internally by
   CausalForestDML's residualisation step. Semantically it's also the
   better encoding: response plausibly scales with an amount's order of
   magnitude, not its absolute rupee value (₹100 vs ₹200 matters more than
   ₹20,000 vs ₹20,100). NOTE this is the CATE model's input only — the EV
   calculation in `policy/decision.py` monetises against the raw
   `case.amount_at_risk`, which is the correct quantity there.

2. **Categoricals drop their first level.** Encoding all levels of a
   categorical makes each group's columns sum to exactly 1; with three such
   groups the design matrix picks up linear dependencies *between* groups
   and goes rank-deficient (measured: rank 11 of 16 columns before this
   fix). Dropping one level per group is the standard remedy, and is what
   the Tier 1 experiment already did via `pd.get_dummies(drop_first=True)` —
   this brings the domain feature encoding in line with the encoding the
   validated Tier 1 pipeline used.

`Channel.RETRY` is excluded from the channel-preference encoding: it's an
action mechanism ("retry the payment silently"), not something a customer
can prefer to be contacted on.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from recovery_ledger.events.schemas import Channel, Language, LossType, RecoveryCase

# First level of each group is the reference level and is NOT emitted.
_LOSS_TYPES = list(LossType)
_LANGUAGES = list(Language)
_CONTACT_CHANNELS = [Channel.SMS, Channel.WHATSAPP, Channel.EMAIL, Channel.VOICE]

FEATURE_NAMES = (
    ["log_amount_at_risk", "is_b2b"]
    + [f"loss_type_{lt.value}" for lt in _LOSS_TYPES[1:]]
    + [f"language_{lang.value}" for lang in _LANGUAGES[1:]]
    + [f"channel_pref_{c.value}" for c in _CONTACT_CHANNELS[1:]]
    + ["channel_pref_unset"]
)


def case_to_features(case: RecoveryCase) -> NDArray[np.float64]:
    values: list[float] = [float(np.log1p(case.amount_at_risk)), float(case.customer.is_b2b)]
    values.extend(float(case.loss_type == lt) for lt in _LOSS_TYPES[1:])
    values.extend(float(case.customer.language_pref == lang) for lang in _LANGUAGES[1:])
    values.extend(float(case.customer.channel_pref == c) for c in _CONTACT_CHANNELS[1:])
    values.append(float(case.customer.channel_pref is None))
    return np.array(values, dtype=np.float64)


def cases_to_feature_matrix(cases: list[RecoveryCase]) -> NDArray[np.float64]:
    return np.vstack([case_to_features(c) for c in cases])
