# Project Spec — Razorpay AI Buildathon, Track 03 (AI Revenue Recovery)

**Codename:** RECOVERY LEDGER
**Owner:** Vaibhav
**Deadline:** 5 September 2026 (applications close). Spec written 20 August 2026 — **16 calendar days**.
**Audience for this doc:** an implementing agent/engineer picking this up cold. Read it end to end before writing code.

---

## 0. TL;DR for the implementer

Build an autonomous **revenue-recovery agent** for Indian payments that decides *whether, when, how, and in what language* to intervene on at-risk revenue — and that reports **incremental** rupees recovered against a randomised no-contact holdout, with every outbound action gated by a deterministic, machine-checkable Indian-regulatory compliance kernel that emits a signed certificate per action.

Three non-negotiable framings:

1. **The agent is the product. The measurement is the proof.** The repo must read as a working system, not a research notebook. If a judge clones it and runs one command, an agent must visibly run, make decisions, and produce an audit trail.
2. **Report incremental, never gross.** Gross recovery is the industry's standard lie. Incremental-with-confidence-intervals is the differentiator.
3. **The compliance kernel is deliberately not an LLM.** This is a headline design decision, not an implementation detail. An agent that is 99% compliant is 100% undeployable in a regulated business.

---

## 1. The competition brief (source of truth)

From `https://razorpay.com/buildathon/`. Do not drift from this.

### 1.1 What the program is

- Student-only program to hire **AI Builder Interns**.
- 6 or 12 month internship, candidate's choice.
- **In-person, Bangalore, from September.**
- ₹75,000/month stipend.
- No resume screening, no aptitude test, no group discussion. Shortlisted builders go straight to a panel.
- Four steps: pick a track → build something real → show your work (public repo, 5-min pitch video, architecture) → if it has signal, they call you in.

### 1.2 Track 03 — AI Revenue Recovery (verbatim)

> **Find revenue that's slipping away and win it back.**
>
> Build an agent that detects revenue at risk, determines the right intervention, and executes a bounded recovery workflow: from payment failures and checkout abandonment to overdue receivables.
>
> **Why now:** Revenue loss rarely happens in one clean step. A payment degrades, a checkout gets abandoned, a subscription fails, or an invoice goes overdue. AI can now close the loop from detecting the problem to diagnosing it, choosing the right intervention, and recovering the money.
>
> **Example directions:** Payment degradation → root cause → recovery action · Checkout drop-off recovery · Failed-subscription recovery · B2B receivables chaser · Mandate retry sequencer · Hinglish voice recovery · Promise-to-pay tracker.
>
> **The bar:** Don't just identify the problem. Show measured money recovered across a batch, with compliant escalation, stopping rules, and an audit trail.

### 1.3 Decoding "the bar" into four gradeable deliverables

The bar is one sentence containing four independent requirements. Each must be demonstrably satisfied:

| # | Requirement | What must exist in the repo |
|---|---|---|
| B1 | **Measured money recovered across a batch** | A batch run over ≥ hundreds of cases producing a headline ₹ figure with a stated methodology. Not a cherry-picked single case. |
| B2 | **Compliant escalation** | An escalation ladder (channel/tone/intensity) where every rung is legally justified and the justification is machine-checked. |
| B3 | **Stopping rules** | Explicit, enumerable termination conditions. The agent must provably stop. |
| B4 | **Audit trail** | Per-decision provenance: what was observed, what was decided, why, under what authority, and what happened. |

### 1.4 Judging criteria (verbatim, from "We read the work, not the resume")

| Criterion | Their words | How this project answers it |
|---|---|---|
| **Problem taste** | "did you pick something that actually matters" | Involuntary churn + MSME receivables are real, funded, unsolved-at-the-edges problems. Cite market evidence (§3). |
| **Build quality** | "does it run, is it structured, would you trust it" | One-command reproducible run, typed interfaces, tests, deterministic seeds, clean module boundaries. |
| **AI judgment** | "the right tool in the right place, **and where you chose not to use one**" | LLM for language/persona/parsing; classical ML for treatment effects; **deterministic kernel for compliance**. Document the "no LLM here" decisions loudly. |
| **Failure recovery** | "what broke, and what you did about it" | Keep an engineering log from day 1 (§13). This maps to the form question they read first. |

### 1.5 Submission checklist — the form asks for exactly 12 things

Form URL: `https://forms.gle/d9r2gvxp8cmoZhon9`

**About you (6):**
1. Full name
2. College
3. Graduation year
4. In-person from September: yes / no
5. 6 or 12 months: your pick
6. Resume file

**About the build (6):**
7. Your track → **Track 03, AI Revenue Recovery**
8. Project name
9. What it solves
10. GitHub repo URL — **must be public**
11. 5-min pitch video — unlisted is fine
12. **What broke, and how you got out** ← *they state this is the one they read first*

> **Implementer note:** #12 is a first-class deliverable, not an afterthought. Maintain `ENGINEERING_LOG.md` from commit 1. See §13.

---

## 2. Non-goals (explicitly out of scope)

Guard against scope creep. This project does **not**:

- Move real money or touch live credentials. **Test mode / synthetic only.**
- Build a production-grade WhatsApp/SMS/voice integration. Channels are **simulated adapters** behind an interface (one may be wired to a real sandbox if time permits).
- Attempt fraud detection or chargeback defence — that is Track 02, and straying there dilutes the story.
- Build a merchant-facing SaaS UI. A single operator dashboard/report is sufficient.
- Claim real-world causal effect sizes. We claim **method validity** (proven on real RCT data) + **policy dominance under stated assumptions** (in simulation). Be scrupulous about this distinction; overclaiming is the fastest way to lose a technical panel.

---

## 3. Problem statement and evidence

### 3.1 The loss surface

Revenue leaks in four distinct ways, each with different physics:

| Loss type | Mechanism | Recovery lever |
|---|---|---|
| **Failed payment** (one-off) | Technical decline (gateway/bank timeout) vs business decline (insufficient funds, wrong PIN, expired card) | Retry timing, rerouting, method switch, customer nudge |
| **Checkout abandonment** | Intent existed, conversion didn't | Nudge, link resend, friction removal |
| **Failed subscription / mandate** | Recurring charge fails; involuntary churn | Retry sequencing, mandate repair, customer action request |
| **Overdue B2B receivable** | Counterparty liquidity or process delay | Escalation, negotiation, settlement terms |

### 3.2 Hard numbers to anchor the pitch (all externally sourced — cite them)

- UPI success ≈ **99.2%**; cards **85–90%**; netbanking **90–95%**; international cards **70–80%**; blended D2C **68–74%**.
- Geographic spread is the hidden killer: metros **78–82%** vs Tier-3 **55–62%** — a **27-point** gap masked by blended metrics.
- **~70%** of Indian cart abandonment is attributed to payment failures; **40%** of customers don't return after a decline.
- Automated retries recover **15–20%** of failed transactions (≈ 3–5 pp on overall success rate).
- Subscription smart-retry recovers up to **57%** of initially failed attempts.
- False declines cost more than fraud: for every ₹100 saved preventing fraud, ₹400–600 is lost to falsely declined legitimate orders.

### 3.3 The gap Razorpay itself leaves open

Razorpay Subscriptions currently retries a failed recurring charge **once** ("We automatically retry the payment on the following day"), then moves the subscription to `halted` and hands the problem back to the merchant, who must manually charge the invoice after the customer updates their details. **Everything after that first retry is unowned.** That is precisely the territory this project occupies — which is a strong "why this matters to *you specifically*" line for the pitch.

### 3.4 Why the category being mature is fine

Butter Payments, Churnkey, Churn Buster, Recurly (~$800M recovered for customers in 2021) and Stripe Revenue Recovery all exist. **Do not claim category novelty.** Claim method novelty (§4). Maturity of the category is evidence the problem is real; the novelty must be in *how* the problem is attacked.

---

## 4. Novelty claims — stated precisely and defensibly

State these in the README and video **exactly this carefully**. Overclaiming loses more points than underclaiming.

### 4.1 What is NOT novel (say so out loud — it buys credibility)

- Dunning / recovery agents as a category.
- Uplift modelling as a technique (benchmarked publicly since Criteo's 2018 work).
- LLM-generated recovery messaging.
- Hinglish voice bots — *and this will be the single most crowded idea in the track, since the brief lists it.*

### 4.2 What IS novel (the defensible claims)

| # | Claim | Why it holds |
|---|---|---|
| **N1** | **Incremental-first recovery accounting.** Recovery vendors overwhelmingly report *gross* recovered revenue. This agent reports **incremental** ₹ vs a randomised no-contact holdout, with confidence intervals. | Industry norm is gross reporting; incremental reframing is rare in this application. |
| **N2** | **Negative-uplift targeting ("do-not-disturbs").** Uplift segmentation into persuadables / sure-things / lost-causes / **do-not-disturbs** — customers who would have paid anyway and whose contact *destroys* value via annoyance and churn. | Nobody in dunning models the downside of contact. This is the sharpest single insight in the project. |
| **N3** | **A deterministic, machine-checkable India-regulatory compliance kernel** emitting a per-action certificate. Encodes TCCCPR/DLT, RBI recovery-agent norms, and the RBI Digital Payments E-Mandate Framework **2026** (four months old at time of writing). | No public project found doing this. Also the strongest "regulated fintech could actually deploy this" signal. |
| **N4** | **Contact modelled as a budget-constrained sequential decision problem**, not one-shot classification — with an explicit contact budget per customer per window. | Grounded in constrained-MDP / budgeted-RL literature; rare in student builds. |
| **N5** | **Two-tier validation** — causal machinery validated on real randomised public data *before* transfer to the domain simulator. | Directly defeats the "your synthetic number is circular" objection (§7). |
| **N6** | **Contact-free recovery.** Detecting issuer-level degradation and suppressing retries into a dead issuer recovers revenue without contacting anyone — the cheapest recovery there is. | Inverts the track's implicit assumption that recovery = outreach. |

---

## 5. System overview

```
                      ┌────────────────────────────────────────┐
                      │           EVENT SOURCES                │
                      │  payments · checkouts · subscriptions  │
                      │            · invoices                  │
                      └───────────────┬────────────────────────┘
                                      │
                      ┌───────────────▼────────────────────────┐
                      │  1. DETECTOR                           │
                      │  - case-level: at-risk revenue         │
                      │  - fleet-level: issuer degradation     │
                      │    (change-point + contribution attr.) │
                      └───────────────┬────────────────────────┘
                                      │
                      ┌───────────────▼────────────────────────┐
                      │  2. DIAGNOSER                          │
                      │  - failure taxonomy (hard/soft)        │
                      │  - root cause attribution              │
                      │  - LLM narration of the "why"          │
                      └───────────────┬────────────────────────┘
                                      │
                      ┌───────────────▼────────────────────────┐
                      │  3. POLICY (the brain)                 │
                      │  - uplift model → expected Δ           │
                      │  - EV = Δ·₹ − cost − annoyance         │
                      │  - budget-constrained sequencing       │
                      │  - action ∈ {wait, retry, reroute,     │
                      │    nudge(channel,lang), negotiate,     │
                      │    escalate_human, STOP}               │
                      └───────────────┬────────────────────────┘
                                      │
        ╔═════════════════════════════▼════════════════════════╗
        ║  4. COMPLIANCE KERNEL   ── DETERMINISTIC, NO LLM ──   ║
        ║  every action must produce a signed certificate      ║
        ║  DENY-BY-DEFAULT. No certificate → no action.        ║
        ╚═════════════════════════════┬════════════════════════╝
                                      │
                      ┌───────────────▼────────────────────────┐
                      │  5. EXECUTOR                           │
                      │  channel adapters (simulated)          │
                      │  sms · whatsapp · email · voice · retry│
                      └───────────────┬────────────────────────┘
                                      │
                      ┌───────────────▼────────────────────────┐
                      │  6. LISTENER                           │
                      │  LLM intent parse of replies:          │
                      │  paid · promise_to_pay · dispute ·      │
                      │  opt_out · wrong_person · negotiate     │
                      └───────────────┬────────────────────────┘
                                      │
                      ┌───────────────▼────────────────────────┐
                      │  7. LEDGER (audit trail + accounting)  │
                      │  append-only · hash-chained            │
                      │  incremental ₹ vs holdout + CIs        │
                      └────────────────────────────────────────┘
```

Components 1→7 form the agent loop. It runs until a **stopping rule** fires (§10).

---

## 6. The four loss types — pick your depth

**Recommendation: implement all four in the event schema, but go deep on TWO.**

- **Primary (depth):** Failed subscription / mandate recovery. Best-defined physics, cleanest incrementality story, directly fills the gap Razorpay leaves after its single retry.
- **Secondary (depth):** B2B overdue receivables — because it unlocks the **negotiation** showpiece (§9.4) and the Section 43B(h) insight.
- **Breadth (shallow but wired):** one-off payment failure and checkout abandonment flow through the same pipeline with simpler policies.

Rationale: breadth alone doesn't impress a panel; depth does. But a pipeline that only handles one loss type looks narrow against a brief that names four.

---

## 7. Data strategy — TWO-TIER VALIDATION (critical)

> **This section is the intellectual core of the project. Do not simplify it.**

### 7.1 The circularity problem, stated plainly

If you generate the synthetic data *and* the agent, then your recovery number measures your own data generator's parameters, not your agent. Calibrating the simulator to published aggregates (e.g. 99.2% UPI success) constrains only the **marginal** distribution of outcomes. Uplift measures a **causal response to intervention** — which no aggregate success-rate benchmark constrains. Calibration alone does **not** rescue the claim.

### 7.2 Tier 1 — Validate the METHOD on real randomised data (no simulator)

Use genuinely randomised public datasets to prove the causal machinery recovers known ground truth.

| Dataset | Access | Notes |
|---|---|---|
| **Criteo Uplift** | `sklift.datasets.fetch_criteo`, also on HuggingFace (`criteo/criteo-uplift`) | ~13.98M rows, 297MB compressed / 3.2GB raw. Treatment ratio 0.85. Visit rate ≈4.7%, conversion ≈0.29%. From real incrementality tests. **Primary choice.** |
| **Hillstrom MineThatData** | `sklift.datasets.fetch_hillstrom` | Small, fast, classic email RCT. Good for quick iteration. |
| **Lenta / X5 RetailHero / MegaFon** | `sklift.datasets.fetch_*` | Backups / robustness checks. |

**Tier 1 deliverable:** a notebook + script showing your uplift learners (T/S/X-learner, causal forest) and your **doubly-robust off-policy estimator** reproduce known treatment effects on real RCT data, with calibration plots, Qini/AUUC curves, and estimator variance. Class-imbalance handling matters (Criteo conversion is 0.29%).

### 7.3 Tier 2 — Transfer the validated method to the domain simulator

Now the simulator needs only to be **plausible**, not probative, because the method is already proven.

**Simulator design ("the recovery gym"):**

- Population of payers with **hidden latent traits**: liquidity level, payday cycle (salary date), annoyance threshold, channel preference, language preference (EN/HI/Hinglish/regional), price sensitivity, dispute propensity, B2B vs B2C.
- **Response model:** probability of payment as a function of (state, action, history) — including **negative** responses (annoyance accumulation → opt-out → churn).
- **Calibrate marginals** to published benchmarks (§3.2) and *state explicitly in the README that this calibrates marginals only*.
- **Sensitivity analysis:** sweep the response-function parameters across a defensible range and show the policy ranking is **stable**. Stability of ranking under assumption sweeps is the honest claim, not a point estimate.
- **LLM-driven personas** for free-text replies that genuinely push back: *"I already paid"*, *"stop messaging me"*, *"call me after Diwali"*, *"send me a GST invoice first"*, *"I'll pay on the 5th when my salary comes"*. This forces the Listener (§5.6) to be real, and makes promise-to-pay an **emergent** requirement rather than a hardcoded feature.

### 7.4 Optional Tier 3 — Razorpay test-mode APIs

If time permits, wire the executor to **Razorpay test mode** so Orders/Payments/Subscriptions/Invoices are real API objects and webhooks are real events. Sandbox setup: `https://razorpay.com/docs/api/sandbox-setup/`. This buys significant credibility ("it talks to their actual API") for modest effort. **Stretch goal — do not let it block the core.**

---

## 8. ML specification

### 8.1 Uplift / heterogeneous treatment effects

- Implement **≥2 learners** for comparison: T-learner and X-learner (plus S-learner as a baseline), and a causal-forest variant.
- Output per (case, action) an estimated **conditional average treatment effect** on payment probability.
- **Segment into four quadrants** and name them in the UI:
  - *Persuadables* — pay because contacted (target these)
  - *Sure things* — pay anyway (contact wastes budget)
  - *Lost causes* — never pay (contact wastes budget)
  - *Do-not-disturbs* — **negative uplift**; contact reduces payment and/or triggers churn (**never contact — this is N2**)
- Metrics: **Qini coefficient, AUUC**, uplift-by-decile charts.

### 8.2 Off-policy evaluation

- Implement **IPS, Self-Normalised IPS, and Doubly Robust** estimators.
- Report variance/confidence intervals, not point estimates alone.
- Use OPE to compare candidate policies **without** running them live — this is a genuinely senior move and directly serves B1.

### 8.3 Decision policy

Expected value of an action:

```
EV(action | state) = Δp_pay(action) × ₹amount_at_risk
                   − channel_cost(action)
                   − λ_annoyance × annoyance_cost(action, history)
                   − λ_churn × P(churn | action, history) × ₹LTV
```

Subject to:
- contact budget per customer per rolling window
- compliance kernel admissibility (§9)
- stopping rules (§10)

Frame explicitly as a **budget-constrained sequential decision problem** (cite weakly-coupled constrained MDP / budgeted-RL literature). A well-justified greedy-EV-under-budget baseline is acceptable if a full constrained solver doesn't fit the timeline — but *say which you did and why*.

### 8.4 Fleet-level degradation detection (N6)

- **Change-point detection** on rolling success rate per slice (issuer × method × amount-band × region).
- **Contribution attribution:** which dimension explains the drop.
- Action: **suppress retries into a degraded issuer** (retrying into an outage has negative expected value — it burns both attempt budget and customer patience), reroute, or switch method.
- LLM narrates the diagnosis in plain language for the operator.

### 8.5 Where LLMs are used (and where they are NOT)

| Use | LLM? | Justification |
|---|---|---|
| Persona simulation / synthetic replies | ✅ | Language variety is exactly what LLMs are for |
| Inbound reply intent classification | ✅ | Free-text → structured intent; validate against a labelled set, report accuracy |
| Message drafting (tone/language/Hinglish) | ✅ | Natural-language generation, template-constrained |
| Negotiation dialogue | ✅ | Bounded by a solver + kernel (§9.4) |
| Root-cause narration | ✅ | Explanation, not decision |
| **Treatment effect estimation** | ❌ | Needs calibrated probabilities and CIs — use classical ML |
| **Compliance decisions** | ❌ | **Must be deterministic and auditable. Headline decision.** |
| **Money-affecting final actions** | ❌ | Gated by kernel + explicit policy |

> Write this table into the README verbatim. It *is* the answer to "AI judgment — and where you chose not to use one."

---

## 9. Compliance kernel specification

### 9.1 Design principles

- **Deny by default.** No certificate → no action. Fail closed.
- **Deterministic.** No LLM in the decision path.
- **Machine-checkable.** Each rule is a predicate over structured state.
- **Certificate per action**, hash-chained into the ledger.

### 9.2 Rules to encode (research-verified — cite sources in README)

**TRAI TCCCPR (incl. 2025 amendments):**
- All commercial comms must be **DLT-registered** before transmission.
- Header suffixes: `-P` promotional, `-S` service, `-T` transactional, `-G` government. Message class must match header class.
- Number series: **140-series** exclusively for promotional voice; **160-series** for service/transactional (not subject to scrubbing). Using ordinary 10-digit numbers for commercial calls risks disconnection up to two years and blacklisting.
- **Inferred consent** does not extend beyond the duration/discharge of the contract; explicit consent for service comms expires after **7 days**.
- After opt-out: **no consent requests for 90 days** unless the customer opts back in.
- Every promotional message must carry an opt-out option.
- Complaint threshold: **5 complaints in 10 days** (tightened from 10-in-7). Penalties ₹1,000 per wrongly dismissed complaint, ₹5,000 per improper template registration; repeat violations → suspension/blacklisting.

**RBI recovery-agent norms:**
- **No contact before 08:00 or after 19:00 IST.**
- No harassment / intimidation. Encode intensity ceilings on tone escalation.

**RBI Digital Payments E-Mandate Framework, 2026:**
- Pre-debit notification **at least 24 hours before** debit, with transaction details **and an opt-out option**.
- **No AFA** required for recurring transactions up to **₹15,000** per transaction (higher limits for specified categories: insurance premia, mutual funds, credit-card bills).
- AFA **required** for mandate registration, modification, or withdrawal.
- Customers may modify/withdraw a mandate at any time (subject to AFA).
- No charges to customers for e-mandate use; grievance redressal mandatory.

**Data protection (DPDPA):** purpose limitation, consent record, retention.

### 9.3 Certificate format

```json
{
  "action_id": "act_01J...",
  "case_id": "case_8891",
  "decision": "ALLOW",
  "action": {"type": "sms", "template_id": "DLT_TMPL_4471", "lang": "hi-IN"},
  "justification": {
    "consent": {"basis": "explicit", "captured_at": "2026-07-02T11:04:00+05:30", "valid": true},
    "dlt": {"registered": true, "header": "RZPRCV-S", "class": "service"},
    "timing": {"now_ist": "14:32", "window": "08:00-19:00", "ok": true},
    "budget": {"attempt": 2, "cap": 3, "window": "7d", "ok": true},
    "opt_out": {"on_record": false, "cooling_until": null},
    "mandate": {"pre_debit_notice_sent_at": "2026-08-19T09:00:00+05:30", "hours_before_debit": 25.5, "ok": true}
  },
  "rules_evaluated": ["TCCCPR.DLT.REG", "TCCCPR.HEADER.CLASS", "RBI.RECOVERY.HOURS", "..."],
  "prev_hash": "sha256:...",
  "hash": "sha256:..."
}
```

### 9.4 Bounded-authority negotiation (the showpiece)

For B2B receivables, the agent **negotiates** rather than merely chases:

- **LLM** runs the conversation.
- **A solver** runs the economics: NPV of cash-now vs full-amount-later; chooses among early-payment discount, instalment plan, extended terms.
- **The kernel** governs what may be conceded — a merchant-set policy envelope, e.g. *never concede >4%, never extend past 60 days, escalate above ₹5L to a human.*

**The India-specific kicker — use this, it is the most memorable thing in the project.** Under **Section 43B(h)** of the Income Tax Act, a buyer who fails to pay an MSME supplier within **45 days** cannot claim that expense as a deduction in that financial year. So the agent can invoke the *counterparty's own tax incentive*: *"Settling by the 45th day keeps this deductible for you this FY."* This reframes chasing as aligned-interest negotiation, and no generic dunning bot would ever find it. Model the 45-day clock explicitly as a state variable driving escalation urgency.

### 9.5 Adversarial validation

Build a red-team harness: an adversarial LLM attempts to induce non-compliant sends (jailbreak the drafter, forge consent state, push outside hours, exceed budget, message an opted-out contact). **Report block rate — target 100%** — and include the attack suite in the repo as tests. A judge who sees a red-team suite immediately upgrades their read of build quality.

---

## 10. Stopping rules (B3) — must be explicit and enumerable

The agent terminates a case when **any** fires:

1. **Resolved** — payment received (poll/webhook confirms).
2. **Opt-out** — customer requests no further contact → immediate stop + 90-day cooling flag.
3. **Budget exhausted** — max attempts per rolling window reached.
4. **Negative EV** — expected value of every remaining admissible action ≤ 0.
5. **Do-not-disturb classification** — negative uplift → never contact (may still allow silent retry).
6. **Promise-to-pay active** — pause until the promised date + grace, then re-evaluate.
7. **Dispute raised** — hand to human, stop automated contact.
8. **Human escalation threshold** — amount or sensitivity exceeds autonomy limit.
9. **Hard decline** — failure code is non-retryable; stop retrying, switch strategy or stop.
10. **Regulatory ceiling** — kernel denies all remaining actions.
11. **Global kill-switch** — operator halt.

Each stop must write a terminal ledger entry with the reason code.

---

## 11. Metrics and evaluation protocol

### 11.1 Headline metric (B1)

**Incremental rupees recovered per 1,000 at-risk cases, vs a randomised no-contact holdout, with 95% confidence intervals.**

Never report gross alone. If gross is shown, show incremental beside it and explain the gap — that contrast *is* the pitch.

### 11.2 Full metric set

**Recovery economics**
- Incremental ₹ recovered (+ CI) — headline
- Gross ₹ recovered (for contrast)
- Recovery rate by loss type, failure code, channel, language, region
- **Cost per incremental rupee recovered**
- Net value = incremental recovery − contact cost − churn cost

**Policy quality**
- Qini coefficient / AUUC
- Uplift by decile
- % of contacts sent to do-not-disturbs (**target ≈ 0** — this is the money chart)
- Contact budget utilisation

**Compliance**
- Certificate coverage: **100%** of actions (any gap is a bug)
- Red-team block rate: **target 100%**
- Violations: **must be 0**

**Agent quality**
- Reply-intent classification accuracy vs labelled set
- Promise-to-pay detection precision/recall
- Mean actions to resolution
- Human escalation rate

**Honesty artefacts**
- Sensitivity sweep showing policy-ranking stability
- **Exception list** — cases the agent could not resolve and why (mirrors Track 04's "honest exception list" language; showing it here signals you read the whole brief)

### 11.3 Baselines to beat (must include all)

1. **Do nothing** (organic recovery floor — this is what makes gross reporting a lie)
2. **Blast everyone** (contact every case, max cadence)
3. **Razorpay-current** (single retry next day, then halt)
4. **Rules-based dunning** (fixed 3-email ladder — the industry standard)
5. **Your policy**

A chart of these five on incremental-₹-and-cost axes is the single most persuasive frame in the video.

---

## 12. Repository structure

```
recovery-ledger/
├── README.md                     # problem, novelty claims, results, how to run, arch diagram
├── ENGINEERING_LOG.md            # dated log — feeds form Q12
├── ARCHITECTURE.md               # component contracts + data flow
├── COMPLIANCE.md                 # every rule + regulatory citation + how tested
├── RESULTS.md                    # metrics, charts, sensitivity analysis, exception list
├── Makefile                      # make setup / demo / eval / redteam / test
├── pyproject.toml
├── src/recovery_ledger/
│   ├── events/                   # schemas for the 4 loss types
│   ├── detector/                 # case-level + fleet-level degradation
│   ├── diagnoser/                # failure taxonomy, root cause, attribution
│   ├── policy/
│   │   ├── uplift/               # T/S/X-learner, causal forest
│   │   ├── ope/                  # IPS, SNIPS, doubly robust
│   │   └── decision.py           # EV + budget constraints
│   ├── kernel/                   # ⚠️ NO LLM IMPORTS — enforce via test
│   │   ├── rules/                # tcccpr.py, rbi_recovery.py, emandate_2026.py, dpdp.py
│   │   ├── certificate.py
│   │   └── engine.py             # deny-by-default evaluator
│   ├── executor/                 # channel adapters (+ optional razorpay_test.py)
│   ├── listener/                 # LLM intent parsing → structured
│   ├── ledger/                   # append-only, hash-chained
│   ├── negotiation/              # solver + policy envelope + 43B(h) clock
│   └── sim/                      # the recovery gym + LLM personas
├── experiments/
│   ├── tier1_criteo/             # method validation on real RCT data
│   ├── tier2_simulation/         # domain policy comparison
│   └── sensitivity/
├── redteam/                      # adversarial compliance attacks
├── tests/
└── dashboard/                    # operator view + audit trail browser
```

**Build-quality signals judges look for:** one-command demo, deterministic seeds, typed interfaces, real tests (not smoke tests), an architecture diagram in the README, and a test that *fails the build* if anything under `kernel/` imports an LLM client.

---

## 13. Build plan — 16 days (20 Aug → 5 Sept)

> Reserve the **last 3 days** for video + README + form. Non-negotiable: an unpolished submission of great work loses to a polished submission of good work.

| Days | Phase | Deliverable |
|---|---|---|
| **1–3** | **Tier 1 validation first** | Criteo/Hillstrom loaded; uplift learners + DR estimator reproducing known effects; Qini/AUUC plots. *Do this before anything else — if the causal machinery doesn't work, the whole thesis fails and you need to know on day 3, not day 13.* |
| **4–5** | Event schemas + simulator skeleton | Four loss types; latent-trait population; response model; marginal calibration to §3.2 benchmarks |
| **6–7** | **Compliance kernel** | All rules encoded; certificate emission; deny-by-default; unit tests per rule |
| **8–9** | Policy + agent loop | Uplift transfer to domain; EV decisioning; budget constraints; all 11 stopping rules; ledger hash-chaining |
| **10** | Listener + personas | LLM reply parsing; promise-to-pay; opt-out; labelled accuracy set |
| **11** | Negotiation + 43B(h) | Solver, policy envelope, tax-incentive clock |
| **12** | Fleet degradation (N6) | Change-point + attribution + retry suppression |
| **13** | Evaluation + red team | All 5 baselines; sensitivity sweep; red-team suite; RESULTS.md |
| **14–15** | Video + docs | 5-min pitch; README; architecture diagram; dashboard polish |
| **16** | Buffer + submit | Form (all 12 fields); repo public; video unlisted |

**If behind schedule, cut in this order:** (1) fleet degradation, (2) negotiation, (3) checkout-abandonment loss type, (4) Razorpay test-mode wiring. **Never cut:** Tier 1 validation, the compliance kernel, incremental measurement, stopping rules, or the audit trail — those are the four bar requirements plus the novelty.

---

## 14. Five-minute video script

Time is brutally short. Structure:

| Time | Beat |
|---|---|
| 0:00–0:30 | **The lie.** "Every recovery tool reports gross recovery. Here's why that number is meaningless: a large share of failed payments recover on their own." Show do-nothing baseline. |
| 0:30–1:15 | **The problem, sized.** Razorpay retries a failed subscription charge once, then halts. Everything after is unowned. Show the numbers from §3.2. |
| 1:15–2:15 | **The agent, running.** Live: detect → diagnose → decide → gate → act → listen → stop. Show the audit trail scrolling. |
| 2:15–3:00 | **The compliance kernel.** Show a certificate. Show the red-team attack being blocked. Say the line: *"the kernel is deliberately not an LLM — 99% compliant is 100% undeployable."* |
| 3:00–3:45 | **The measurement.** Two-tier validation. *"I didn't validate my estimator on data I generated — I validated it on Criteo's 14-million-row randomised dataset, then transferred it."* Show the 5-baseline chart. |
| 3:45–4:20 | **Do-not-disturbs.** The negative-uplift quadrant. "We deliberately don't contact these — and it makes more money." |
| 4:20–4:45 | **The 43B(h) negotiation moment.** The agent using the counterparty's own tax deadline. |
| 4:45–5:00 | **What broke.** One honest failure and the fix. Close. |

Record the demo **live-running**, not as slides. Judges are checking "does it run."

---

## 15. Form answer preparation

**Q9 — What it solves (draft angle):** Lead with the gap, not the tech. *"Razorpay retries a failed recurring charge once, then halts the subscription and hands the problem back to the merchant. Everything after that first retry is unowned revenue. This agent owns it — and reports what it actually added, not what it took credit for."*

**Q12 — What broke, and how you got out.** *They read this first.* Keep `ENGINEERING_LOG.md` from commit 1. The best answer is a **real** methodological failure, not a bug — e.g. *"My first incrementality number was inflated because my simulator's response function was something I'd invented; calibrating to aggregate benchmarks didn't fix it because aggregates constrain marginals, not causal response. I moved to two-tier validation: prove the estimator on Criteo's randomised data, then transfer."* That answer demonstrates all four judging criteria at once. **Do not manufacture this — let it happen and write it down when it does.**

---

## 16. Risks and mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| **"Your synthetic number is circular"** | 🔴 Critical | Two-tier validation (§7). Claim method validity + ranking stability, never real-world effect size. |
| **"Where's the agent? This is a notebook"** | 🔴 Critical | Agent loop is the product; one-command live demo; measurement is supporting evidence. |
| Scope overrun | 🔴 High | Cut list in §13. Two loss types deep, two shallow. |
| Compliance rules misread | 🟠 Medium | Cite every rule to source in COMPLIANCE.md; state "as I read it" where genuinely ambiguous. Being *precise about uncertainty* reads better than false confidence. |
| Criteo dataset size (3.2GB) | 🟠 Medium | Start with Hillstrom for iteration speed; use a Criteo subsample; watch disk. |
| Uplift signal too weak (0.29% conversion) | 🟠 Medium | Proper class-imbalance handling; report CIs honestly; Hillstrom as sanity check. |
| LLM cost/latency in simulation | 🟡 Low | Cache persona responses; batch; use a small model for personas. |
| Video overruns 5 min | 🟡 Low | Script and rehearse; hard-cut §14. |

---

## 17. Definition of done

- [ ] `make demo` runs the agent end to end from a clean clone
- [ ] Batch run over ≥ hundreds of cases produces headline **incremental** ₹ + CI (B1)
- [ ] Escalation ladder implemented, every rung compliance-justified (B2)
- [ ] All 11 stopping rules implemented and unit-tested (B3)
- [ ] Hash-chained audit trail, browsable; **100% certificate coverage** (B4)
- [ ] Tier 1 validation reproduces known effects on real randomised data
- [ ] All 5 baselines compared; sensitivity sweep shows stable ranking
- [ ] Red-team suite: 100% block rate, 0 violations
- [ ] Test enforcing no LLM imports under `kernel/`
- [ ] Honest exception list published
- [ ] README states novelty claims **and explicitly what is not novel**
- [ ] `ENGINEERING_LOG.md` populated with real failures
- [ ] 5-min video recorded, live demo, unlisted
- [ ] Repo public; all 12 form fields ready

---

## 18. References

**Competition**
- Buildathon — https://razorpay.com/buildathon/
- Application form — https://forms.gle/d9r2gvxp8cmoZhon9

**Razorpay product & API**
- Payment Success Rate Optimization India (2026) — https://razorpay.com/blog/payment-success-rate-optimization-india/
- Subscriptions: Payment Retries — https://razorpay.com/docs/payments/subscriptions/payment-retries/
- About Optimizer — https://razorpay.com/docs/payments/optimizer/
- Magic Checkout: Abandoned Cart Webhook — https://razorpay.com/docs/payments/magic-checkout/abandoned-cart/
- API Sandbox Setup — https://razorpay.com/docs/api/sandbox-setup/

**Regulation**
- RBI Digital Payments E-Mandate Framework 2026 — https://www.scconline.com/blog/post/2026/04/24/rbi-issues-digital-payments-e-mandate-framework-2026/
- TCCCPR 2025 amendments — https://www.sigmachambers.in/post/2025-tcccpr-amendments-a-renewed-push-by-trai-for-order-in-commercial-communications-1
- RBI draft loan-recovery norms (8am–7pm cap) — https://upstox.com/news/business-news/financial-regulations/rbi-proposes-overhaul-of-loan-recovery-norms-draft-rules-ban-harassment-cap-calls-to-8am-7pm/article-189398/
- Section 43B(h) MSME 45-day rule — https://www.indiafilings.com/learn/section-43bh-new-msme-45-days-payment-rule

**Method**
- Criteo Uplift Prediction Dataset — https://ailab.criteo.com/criteo-uplift-prediction-dataset/
- A Large Scale Benchmark for Uplift Modeling (Diemert et al.) — http://papers.adkdd.org/2018/papers/adkdd18-diemert-large-scale.pdf
- scikit-uplift datasets — https://www.uplift-modeling.com/en/latest/api/datasets/fetch_criteo.html
- Doubly Robust Policy Evaluation and Learning (Dudík et al.) — https://icml.cc/2011/papers/554_icmlpaper.pdf
- Budget Allocation using Weakly Coupled, Constrained MDPs (Google) — https://research.google.com/pubs/archive/45291.pdf
- Budgeted RL in Continuous State Space — http://papers.neurips.cc/paper/9128-budgeted-reinforcement-learning-in-continuous-state-space.pdf

**Market context**
- Involuntary churn / dunning landscape — https://www.butterpayments.com/guides/disputes-chargebacks-guides/involuntary-churn/
- Best dunning tools comparison (2026) — https://churntools.com/blog/best-dunning-tools-comparison
