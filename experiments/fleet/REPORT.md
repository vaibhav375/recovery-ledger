# Detection latency — how fast is contact-free recovery?

`make fleet-latency` → `results_fleet_latency.json`

## Why this was run

Novelty claim N6 is contact-free recovery: the agent notices a payment rail has
degraded and stops retrying into it, recovering money without messaging anyone.
`make fleet` *demonstrates* that — it plants an outage, the detector fires, and
351 futile retries are avoided.

A demonstration is not a measurement. It shows the detector works on one
outage; it does not say how fast, how that speed varies with how bad the outage
is, or how often the detector cries wolf on a healthy rail. Latency without a
false-alarm rate is meaningless — a detector that fires instantly on noise has
zero latency and no value.

## Design

A change-point is injected at a known attempt index and the detector is polled
until it flags that issuer; the gap is the latency. Repeated over
**8 independent draws** per effect size, because a latency from one draw is a
claim about that draw. The effect size is swept: the issuer's success rate
falls from 90% to each of four post-change rates, so the
relationship between how bad the outage is and how fast it is caught is
visible rather than assumed.

The false-alarm rate is measured separately on **30 control draws with no
change-point injected at all**, under the same polling procedure.

The detector is measured as it ships. Nothing in `detector/fleet.py` was
changed for this experiment.

## The rule, fixed before the run

> Latency is claimable only if it replicates: the median latency must be finite and the detector must fire in every draw at the largest effect size. If the detector misses the change-point in any draw at that size, report the miss rate rather than a latency. A latency figure is only meaningful alongside the false-alarm rate measured on no-change control runs, so both are reported together or neither is claimed.

## Result

| issuer rate falls to | drop | detected | median latency (attempts) | range |
|---:|---:|:--|---:|---|
| 0.70 | 0.20 | 8/8 | 125 | 100–150 |
| 0.55 | 0.35 | 8/8 | 75 | 50–100 |
| 0.40 | 0.50 | 8/8 | 50 | 50–75 |
| 0.12 | 0.78 | 8/8 | 50 | 25–50 |

**False alarms: 0 of 30 control draws (0.0%).**

## What it says

**The detector fires every time, at every effect size swept** — 8/8 draws in all
four conditions. There is no miss rate to report.

**Latency scales with severity, monotonically.** A 20-point drop takes a median
of 125 attempts to catch; a 78% collapse takes 50. That is the shape a
two-proportion z-test should produce — a larger divergence from baseline clears
the threshold on less evidence — and seeing it come out that way is a check on
the detector, not just a description of it.

**It does not cry wolf.** Zero false alarms across 30 healthy draws, so the
latency figures are not bought by a trigger-happy threshold.

At 25 attempts an hour, a median of 50 attempts on a severe outage is about
two hours of futile retries before the rail is ruled out.

## What this does not license

This measures the detector against an injected change-point in the simulator,
where the ground truth is known by construction. It says nothing about latency
on a real payment rail, where degradations are gradual, partial, and mixed with
seasonality the simulator does not model. The claim is that the detector's
speed is now *measured* rather than demonstrated — not that this number
transfers.
