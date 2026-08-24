"""Issuer health over time — the ground truth the fleet detector has to find.

Models what actually happens on a payment rail: most of the time an issuer
authorises at its normal rate, and occasionally it has an outage window
where that rate collapses. The detector never sees this object; it only sees
observed attempts, exactly as a real system would.

This is what makes novelty claim N6 measurable rather than rhetorical. If
retries into a degraded issuer are simply *less likely* to work, suppressing
them is a marginal optimisation. If they are near-certain to fail, then
retrying is a strictly value-destroying act — it consumes the case's attempt
budget and produces nothing — and detecting the outage recovers real money
without contacting a single customer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

HEALTHY_AUTH_RATE = 0.90
OUTAGE_AUTH_RATE = 0.12


@dataclass(frozen=True)
class Outage:
    issuer: str
    start: datetime
    end: datetime

    def covers(self, at: datetime) -> bool:
        return self.start <= at < self.end


@dataclass
class FleetHealth:
    outages: list[Outage]

    def auth_rate(self, issuer: str | None, at: datetime) -> float:
        if issuer is None:
            return HEALTHY_AUTH_RATE
        for o in self.outages:
            if o.issuer == issuer and o.covers(at):
                return OUTAGE_AUTH_RATE
        return HEALTHY_AUTH_RATE

    def is_out(self, issuer: str | None, at: datetime) -> bool:
        return issuer is not None and any(o.issuer == issuer and o.covers(at) for o in self.outages)


def generate_fleet_health(
    issuers: list[str], *, now: datetime, seed: int, n_outages: int = 1,
    duration_hours: float = 10.0,
) -> FleetHealth:
    """One or more issuers having an outage that is live *now* — so a batch
    run at `now` actually encounters it rather than reading about it in
    history."""
    rng = np.random.default_rng(seed)
    chosen = rng.choice(issuers, size=min(n_outages, len(issuers)), replace=False)
    outages = [
        Outage(issuer=str(i),
               start=now - timedelta(hours=duration_hours * 0.6),
               end=now + timedelta(hours=duration_hours * 0.4))
        for i in chosen
    ]
    return FleetHealth(outages=outages)


def synth_history(
    issuers: list[str], health: FleetHealth, *, now: datetime, seed: int,
    hours: int = 24 * 7, attempts_per_hour: int = 4,
):
    """Observed attempt history for the detector to work from — the only
    thing it is allowed to see."""
    from recovery_ledger.detector.fleet import PaymentAttempt

    rng = np.random.default_rng(seed)
    out = []
    for h in range(hours, 0, -1):
        at = now - timedelta(hours=h)
        for issuer in issuers:
            for _ in range(attempts_per_hour):
                rate = health.auth_rate(issuer, at)
                out.append(PaymentAttempt(
                    at=at, issuer=issuer, method="card", region="metro",
                    succeeded=bool(rng.random() < rate),
                ))
    return out
