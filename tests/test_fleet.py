"""Fleet-level degradation detection (spec 8.4, novelty claim N6)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from recovery_ledger.detector.fleet import (
    DegradedIssuerRegistry,
    FleetDegradationDetector,
    PaymentAttempt,
)
from recovery_ledger.sim.fleet_health import generate_fleet_health, synth_history
from recovery_ledger.sim.generator import ISSUERS

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


def _stream(rates: dict[str, tuple[float, float]], *, seed=0, per_hour=25):
    """rates: issuer -> (baseline_rate, recent_rate)."""
    rng = np.random.default_rng(seed)
    out = []
    for h in range(24 * 7, 0, -1):
        at = NOW - timedelta(hours=h)
        recent = h <= 6
        for issuer, (base, rec) in rates.items():
            p = rec if recent else base
            for _ in range(per_hour):
                out.append(PaymentAttempt(at, issuer, "card", "metro", bool(rng.random() < p)))
    return out


def test_detects_a_collapsed_issuer():
    d = FleetDegradationDetector()
    d.observe_many(_stream({"HDFC": (0.92, 0.10), "ICICI": (0.90, 0.90)}))
    flagged = {x.slice_key for x in d.detect(NOW) if x.dimension == "issuer"}
    assert flagged == {"HDFC"}


def test_does_not_flag_a_stable_issuer():
    d = FleetDegradationDetector()
    d.observe_many(_stream({"HDFC": (0.90, 0.90), "ICICI": (0.90, 0.89)}))
    assert not [x for x in d.detect(NOW) if x.dimension == "issuer"]


def test_a_structurally_low_issuer_is_not_flagged_merely_for_being_low():
    """Each slice is compared against ITSELF. An issuer that always authorises
    at 55% is not degraded — it is just worse."""
    d = FleetDegradationDetector()
    d.observe_many(_stream({"WEAK": (0.55, 0.55), "STRONG": (0.95, 0.95)}))
    assert not [x for x in d.detect(NOW) if x.dimension == "issuer"]


def test_attribution_names_the_issuer_not_the_dimensions_it_drags_down():
    """An issuer outage also depresses the aggregate for the method and region
    it serves. The operator needs the root cause, not all three."""
    d = FleetDegradationDetector()
    d.observe_many(_stream({"HDFC": (0.92, 0.08), "ICICI": (0.91, 0.91)}))
    top = d.attribute(NOW)
    assert top is not None
    assert top.dimension == "issuer" and top.slice_key == "HDFC"


def test_thinly_observed_slices_are_not_judged():
    """Below the minimum observation floor the detector must decline rather
    than guess — a false positive suppresses retries into a working issuer."""
    d = FleetDegradationDetector()
    d.observe_many(_stream({"TINY": (0.92, 0.05)}, per_hour=2))
    assert not d.detect(NOW)


def test_narration_is_specific_enough_to_act_on():
    d = FleetDegradationDetector()
    d.observe_many(_stream({"HDFC": (0.92, 0.10), "ICICI": (0.9, 0.9)}))
    text = d.detect(NOW)[0].narrate()
    assert "HDFC" in text and "%" in text


def test_registry_only_tracks_issuers():
    d = FleetDegradationDetector()
    d.observe_many(_stream({"HDFC": (0.92, 0.08), "ICICI": (0.9, 0.9)}))
    reg = DegradedIssuerRegistry().update_from(d.detect(NOW))
    assert reg.is_degraded("HDFC")
    assert not reg.is_degraded("ICICI")
    assert not reg.is_degraded(None)


def test_end_to_end_detection_recovers_the_true_outage():
    """Against the simulator's ground truth, which the detector never sees."""
    for seed in range(8):
        health = generate_fleet_health(ISSUERS, now=NOW, seed=seed)
        d = FleetDegradationDetector()
        d.observe_many(synth_history(ISSUERS, health, now=NOW, seed=seed, attempts_per_hour=25))
        flagged = {x.slice_key for x in d.detect(NOW) if x.dimension == "issuer"}
        assert flagged == {o.issuer for o in health.outages}, f"seed {seed}"


def test_retry_into_a_degraded_issuer_is_valued_at_zero():
    from recovery_ledger.events.schemas import Channel, CustomerProfile, FailedPaymentCase
    from recovery_ledger.policy.decision import _retry_incremental_prob

    def case(issuer):
        return FailedPaymentCase(
            case_id="c", customer=CustomerProfile(customer_id="u", channel_pref=Channel.SMS),
            amount_at_risk=5000.0, detected_at=NOW, failure_code="gateway_timeout",
            is_hard_decline=False, payment_method="card", issuer=issuer)

    reg = DegradedIssuerRegistry(degraded={"KOTAK"})
    assert _retry_incremental_prob(case("KOTAK"), reg) == 0.0
    assert _retry_incremental_prob(case("HDFC"), reg) > 0.0
    # with no registry at all, nothing is suppressed
    assert _retry_incremental_prob(case("KOTAK"), None) > 0.0
