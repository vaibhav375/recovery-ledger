# Compliance kernel — rules, sources, and how each is tested

The kernel (`src/recovery_ledger/kernel/`) is deterministic and denies by
default: an action is `ALLOW` only if every registered rule passes, and zero
registered rules means every action is denied (see
`src/recovery_ledger/kernel/engine.py`). Nothing under `kernel/` may import
an LLM client — mechanically enforced by
`tests/test_kernel_no_llm_imports.py`, which was mutation-tested (a
temporary `import anthropic` inside `kernel/` was confirmed to fail the
test, then removed — see `ENGINEERING_LOG.md`, 2026-08-23).

13 rules are implemented so far, all with passing unit tests in
`tests/test_kernel_engine.py`, `tests/test_kernel_rules_new.py`, and
`tests/test_runner.py` (the promise-to-pay window).

## Provenance is machine-readable, and its limits are stated

`src/recovery_ledger/kernel/provenance.py` carries a `Citation` for every rule
in the default kernel: the instrument, its reference where we could name one,
the section number **only where it was checked against the instrument itself**,
one sentence on what the source requires, and one sentence on what this project
actually encoded — which is not always the same thing.

Two rules are enforced by `tests/test_kernel_provenance.py` rather than left to
good intentions:

- **No invented clause numbers.** Where the rule was encoded from the spec's
  summary of a requirement rather than from the instrument, `clause` is `None`
  and `confidence` is `"spec"`. A missing section number is information; a
  plausible-looking wrong one is a liability. The tests fail the build if a
  clause is pinned without a primary source.
- **Policy is labelled as policy.** The three `POLICY.*` rules are this
  project's own operating limits, not law. They declare `kind="policy"` and
  carry no instrument, and a test fails if one ever claims otherwise.

Two further tests keep the registry from drifting: every rule in the default
kernel must have an entry, and every entry must correspond to a rule that still
exists.

The registry is embedded in `dashboard/dist/data.json`, so the static dashboard
can answer "says who?" with no server running, and is also served at
`/api/provenance` by the live console.

## RBI recovery-agent norms

| Rule | File | What it checks | Source |
|---|---|---|---|
| `RBI.RECOVERY.HOURS` | `rules/timing.py` | No customer contact before 08:00 or after 19:00 IST. Silent retries are exempt (not customer contact). | Spec section 9.2, citing the RBI draft loan-recovery norms (8am–7pm cap) |
| `RBI.RECOVERY.TONE_CEILING` | `rules/escalation.py` | Maximum permitted message "tone intensity" (0=neutral..3=firm) rises only with genuine attempt history (attempt 0 → ≤1, attempt 1 → ≤2, attempt 2+ → ≤3) — an escalation ladder can't jump straight to its firmest tone on first contact. | Spec section 9.2: "No harassment/intimidation. Encode intensity ceilings on tone escalation." This is also the machine-checked half of bar requirement B2. |

## TRAI TCCCPR (incl. 2025 amendments)

| Rule | File | What it checks | Source |
|---|---|---|---|
| `TCCCPR.DLT.REGISTERED` | `rules/tcccpr.py` | Commercial comms must be DLT-registered before transmission. | Spec section 9.2 |
| `TCCCPR.HEADER.CLASS_MATCH` | `rules/tcccpr.py` | The DLT template's registered class (-P/-S/-T/-G) must match the message's actual declared class. | Spec section 9.2 |
| `TCCCPR.CONSENT.VALIDITY` | `rules/tcccpr.py` | Inferred consent lapses when the underlying contract/relationship is no longer active; explicit consent for service-class messages expires after 7 days. | Spec section 9.2 — **see ambiguity note below** |
| `TCCCPR.OPT_OUT.OPTION_PRESENT` | `rules/tcccpr.py` | Promotional messages must carry an opt-out option. Service/transactional messages are exempt from this specific check. | Spec section 9.2 |
| `TCCCPR.OPT_OUT.COOLING` | `rules/opt_out.py` | After opt-out, no further consent requests for 90 days unless the customer opts back in. | Spec section 9.2 |
| `TCCCPR.NUMBER_SERIES` | `rules/tcccpr.py` | 140-series exclusively for promotional voice; 160-series for service/transactional SMS and voice. | Spec section 9.2 |

## RBI Digital Payments E-Mandate Framework, 2026

| Rule | File | What it checks | Source |
|---|---|---|---|
| `EMANDATE2026.PRE_DEBIT_NOTICE` | `rules/emandate_2026.py` | A mandate debit attempt (modelled as `RETRY` against a `FailedSubscriptionCase`) requires a pre-debit notice sent at least 24 hours earlier. | Spec section 9.2 |

**Not yet encoded:** AFA (Additional Factor Authentication) requirements for
mandate registration, modification, or withdrawal. There is no `ActionType`
in this project that represents registering or modifying a mandate — the
agent loop only acts against an *existing* mandate (retry, nudge, escalate).
Encoding a rule against an action the system can never actually propose
would test nothing; noted here rather than faked with a rule that's
vacuously always exempt.

## DPDPA (Digital Personal Data Protection Act, 2023)

| Rule | File | What it checks | Source |
|---|---|---|---|
| `DPDPA.CONSENT_RECORD` | `rules/dpdp.py` | Customer contact requires an on-record consent capture timestamp — not necessarily current, just that one exists. | Spec section 9.2: "purpose limitation, consent record, retention" |

**Purpose limitation and retention are not encoded as per-action rules.**
They're structural properties of what the system stores, not predicates
about one candidate action: purpose limitation is addressed by the event
schemas (`events/schemas.py`) only carrying fields each loss type actually
needs, and retention is currently an honest gap — the ledger has no
automatic purge/expiry policy yet. Recording that gap here rather than
writing a rule that doesn't check anything real.

## Promise-to-pay silence window (internal policy, harassment-adjacent)

| Rule | File | What it checks | Source |
|---|---|---|---|
| `POLICY.PROMISE_TO_PAY_WINDOW` | `rules/promise.py` | No customer contact while a promised-payment date (plus grace) is still in the future. Silent retries and waiting are exempt. | Spec section 10, rule 6 ("pause until the promised date + grace, then re-evaluate") |

Placed in the kernel rather than the agent loop deliberately. Contacting
someone on the 3rd who said they would pay on the 5th is not merely
suboptimal targeting — it is the pestering pattern the RBI recovery-agent
norms exist to prevent. Encoding it as an admissibility rule means the
silence is *justified in the audit trail* with a certificate naming the
promised date, rather than being an invisible branch in control flow.

## Contact budget (internal policy, not a specific regulation)

| Rule | File | What it checks | Source |
|---|---|---|---|
| `POLICY.CONTACT_BUDGET` | `rules/budget.py` | Contact attempts per customer per rolling window stay under a cap. | Spec sections 8.3 / 9.1 (also backs stopping rule 3, "budget exhausted", section 10) |

## Negotiation envelope (internal policy, not a specific regulation)

| Rule | File | What it checks | Source |
|---|---|---|---|
| `POLICY.NEGOTIATION_ENVELOPE` | `rules/negotiation.py` | A settlement offer must stay inside the discount ceiling the merchant authorised, and the case must sit below the agent's per-case autonomy limit in rupees. Above it the kernel returns `DENY` and no message is drafted at all. | Spec section 9.4 (bounded authority) and section 10, rule 8 ("amount or sensitivity exceeds autonomy limit") |

Not law. The envelope is *sized* against Section 43B(h) of the Income-tax
Act, 1961 (inserted by the Finance Act, 2023) read with s. 15 of the MSMED
Act, 2006 — a buyer who does not pay a micro or small enterprise inside the
statutory window has the deduction deferred to the year of actual payment,
which is what makes early settlement the buyer's own interest and means the
agent rarely needs to concede margin at all. That statute shapes the
negotiation; it does not impose this rule.

Verified in `experiments/negotiation/`: the ₹900,000 scenario returns `DENY`
on this rule, with no draft produced.

## Ambiguities flagged rather than silently resolved

**`TCCCPR.CONSENT.VALIDITY`'s 7-day explicit-consent window.** The spec's
source material states "explicit consent for service comms expires after 7
days," cited from the 2025 TCCCPR amendments. It is not fully clear from
that source whether *all* explicit consent for service-class messages
lapses in 7 days regardless of origin, or only consent that was captured for
a different original purpose and is now being reused for service
communications. This project encodes the **strict, literal reading** —
re-validate every 7 days — because a deny-by-default kernel should fail
toward more restrictive when a rule's scope is ambiguous, not less. If this
reading is wrong, it's wrong in the safe direction (over-blocking, not
under-blocking).

**Default consent basis in the agent loop.** `agent/loop.py` populates every
`RuleContext.consent` as `basis="inferred"`, on the reasoning that every
case this project acts on arises from an existing transaction, subscription,
or invoice relationship — the customer already has a relationship with the
merchant, this isn't cold outreach. If a future loss type or scenario
involves contacting someone with no prior relationship at all, that
assumption needs revisiting; it hasn't come up yet because all four current
loss types are inherently relationship-based.
