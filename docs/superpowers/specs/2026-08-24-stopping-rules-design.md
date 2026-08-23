# Design — B3: all 11 stopping rules, reachable and provable

**Date:** 2026-08-24
**Status:** approved, implementing
**Bar requirement:** B3 ("stopping rules") — spec section 10, on the
"never cut" list in section 13.

## Problem

The `StopReason` enum has all 11 values, but a real 2,000-case run fires
only 5 of them:

```
resolved 498 · negative_ev 1335 · promise_to_pay 115 · dispute 33 · opt_out 19
budget_exhausted 0 · do_not_disturb 0 · human_escalation 0
hard_decline 0 · regulatory_ceiling 0 · global_kill_switch 0
```

So the honest claim today is "5 of 11 implemented", against a bar
requirement that reads "stopping rules" as a graded deliverable. Worse,
one of the five that *does* fire is mis-attributed (see Defect 1).

## Defects this design fixes

**Defect 1 — `BUDGET_EXHAUSTED` is mis-attributed as `NEGATIVE_EV`.**
`agent/loop.py` maps *every* policy `STOP` decision to
`StopReason.NEGATIVE_EV`, including the `STOP` a policy returns when it
reaches `max_attempts`. Budget exhaustion and "no action has positive
expected value" are different terminations with different meanings, and
the ledger currently cannot distinguish them. A large share of the 1,335
`negative_ev` stops are really budget exhaustion.

**Defect 2 — promise-to-pay is treated as terminal.** Spec rule 6 is
"pause until the promised date + grace, then re-evaluate". The loop
treats it as an ending. A promise is not an ending, and terminating on it
understates recovery: those 115 cases were abandoned at exactly the
moment the customer signalled intent to pay.

## Non-goals

- No real scheduler, daemon, or persistent datastore. Simulated time only.
- No change to the compliance kernel's deny-by-default semantics.
- Not building the promise-honouring measurement if the schedule slips
  (see Cut line).

## Design

### 1. `CaseOutcome` replaces the bare `StopReason` return

```python
@dataclass(frozen=True)
class CaseOutcome:
    case_id: str
    status: Literal["terminated", "paused"]
    stop_reason: StopReason | None    # set iff terminated
    resume_at: datetime | None        # set iff paused
```

This is the interface change that makes the work architectural rather
than bounded: `run_batch.py` and `run_baselines.py` both consume
`run_case`'s return value for ₹ accounting.

### 2. `ActionDecision` carries its own `stop_reason`

Fixes Defect 1. A policy that stops because its budget is exhausted says
so; a policy that stops because nothing has positive EV says that. The
loop attributes rather than guesses.

### 3. `agent/runner.py` — a work queue with scheduled resumption

Owns the clock. Runs every case; collects the paused ones; advances
simulated time to the earliest `resume_at`; re-runs those; repeats until
nothing is paused or a horizon is reached.

Cases still paused at the horizon are **reported as exceptions, not
silently dropped** — which also produces the "honest exception list" that
spec section 11.2 and the Definition of Done both require.

This is the integration of the two options considered (in-loop time
advance vs. real suspend/resume): pauses are first-class inspectable
state, but a batch driver advances the clock rather than a scheduler.
It generalises to every other temporal constraint already in the
system — the 90-day opt-out cooling period and the 24-hour pre-debit
notice window are the same shape of problem.

### 4. `PromiseToPayWindowRule` in the compliance kernel

Contact actions are DENIED inside an active promise window, with a
certificate stating the promised date. This is the design decision that
makes promise-to-pay serve the project's actual differentiator (N3, the
deterministic compliance kernel) rather than being loop plumbing.

Rationale: contacting a customer on the 3rd who said they would pay on
the 5th is not merely suboptimal, it is the harassment pattern the RBI
recovery-agent norms exist to prevent. It belongs in the kernel, and it
belongs in the audit trail.

### 5. The five remaining dead rules

| Rule | Trigger |
|---|---|
| `HARD_DECLINE` | failure code non-retryable, retry inadmissible, nothing else left |
| `DO_NOT_DISTURB` | predicted uplift < 0 and no silent retry available |
| `HUMAN_ESCALATION_THRESHOLD` | amount at risk exceeds the agent's autonomy limit |
| `GLOBAL_KILL_SWITCH` | operator halt flag, checked at the top of every iteration |
| `BUDGET_EXHAUSTED` | attempt cap reached (correctly attributed per Defect 1) |

### 6. Testing — making B3 provable rather than claimed

- A unit test per rule that forces it in isolation.
- **One integration test that runs a crafted scenario suite and asserts
  every one of the 11 reasons fires at least once.** This converts "all
  11 stopping rules implemented" from a claim in a README into something
  a judge can execute.

### 7. Measurement (the cut line)

`respect_promise_windows: bool` on the agent; both variants run in
`make baselines`; report whether honouring promises actually recovers
more money. Interesting because it tests whether compliance and revenue
align or conflict — and because no dunning vendor reports it.

**This is the first thing cut if the schedule slips.** Everything above
stands without it.

## Risks

- **Scope creep via the runner.** The queue driver is the piece most
  likely to grow. Horizon and max-resume-rounds are hard-capped.
- **Non-termination.** A resumption loop can in principle cycle forever.
  Mitigated by a hard cap on resume rounds plus the existing per-case
  step cap, and asserted by test.
- **Experiment churn.** Both experiment scripts change; every headline
  number must be re-run and re-verified deterministic afterwards.
