"""Where each kernel rule comes from.

The kernel already refuses actions and names the rule that refused them. This
module answers the next question a compliance officer asks: *says who?*

Two disciplines are enforced here, because getting this wrong would be worse
than not doing it at all:

1. **No invented clause numbers.** `clause` is filled in only where the
   section/regulation number was checked against the instrument itself.
   Everywhere else it is `None` and `confidence` is `"spec"`, meaning the rule
   was encoded from the buildathon spec's summary of the requirement and the
   instrument named below is our identification of what that summary refers
   to. A missing clause number is information; a plausible-looking wrong one
   is a liability.

2. **Policy is labelled as policy.** Three of the thirteen rules are not law.
   They are this project's own operating limits, and they say so
   (`kind="policy"`, `instrument=None`). Presenting an internal contact budget
   as a regulatory requirement would be exactly the kind of compliance theatre
   the kernel exists to avoid.

Citations deliberately do **not** go into the ledger. A citation is a property
of the rule, not of the event: putting it on all 13 rule results of all 5,712
certificates would add tens of megabytes of duplicated text to the audit
trail and change nothing about what the trail proves. The ledger stores the
rule name; this registry resolves it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Kind = Literal["circular", "regulation", "statute", "policy"]
Confidence = Literal["primary", "spec"]


@dataclass(frozen=True)
class Citation:
    """One rule's source.

    kind        what sort of instrument this is (or "policy" for our own rules)
    instrument  the instrument's name, or None for internal policy
    reference   its identifying number/date, where we could name it
    clause      section/regulation number — only when checked against the
                instrument; None otherwise (see module docstring)
    requirement one sentence: what the source actually requires
    encoded_as  one sentence: what this project's rule actually checks, which
                is not always the same thing
    confidence  "primary" (requirement taken from the instrument) or "spec"
                (taken from the buildathon spec's summary of it)
    note        anything a reader would otherwise get wrong
    url         where to go and read it
    """

    kind: Kind
    instrument: str | None
    reference: str | None
    clause: str | None
    requirement: str
    encoded_as: str
    confidence: Confidence
    note: str | None = None
    url: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


_TCCCPR = "TRAI Telecom Commercial Communications Customer Preference Regulations, 2018"
_TCCCPR_REF = "No. 6 of 2018, as amended"
_TCCCPR_URL = "https://www.trai.gov.in/"
_RBI_AGENTS = (
    "RBI — Outsourcing of Financial Services: Responsibilities of regulated "
    "entities employing Recovery Agents"
)
_RBI_AGENTS_REF = "DOR.ORG.REC.65/21.04.158/2022-23, 12 August 2022"
_RBI_URL = "https://www.rbi.org.in/"


REGISTRY: dict[str, Citation] = {
    # ── RBI recovery-agent norms ─────────────────────────────────────────
    "RBI.RECOVERY.HOURS": Citation(
        kind="circular",
        instrument=_RBI_AGENTS,
        reference=_RBI_AGENTS_REF,
        clause=None,
        requirement=(
            "Regulated entities must ensure their recovery agents do not "
            "contact borrowers before 8:00 a.m. or after 7:00 p.m."
        ),
        encoded_as=(
            "Customer-facing actions are denied outside 08:00–19:00 IST. "
            "RETRY and WAIT are exempt — a silent retry is not contact."
        ),
        confidence="primary",
        note=(
            "The window is the circular's. The RETRY/WAIT exemption is our "
            "reading: the prohibition is on contacting the borrower, and a "
            "background retry does not reach them."
        ),
        url=_RBI_URL,
    ),
    "RBI.RECOVERY.TONE_CEILING": Citation(
        kind="circular",
        instrument=_RBI_AGENTS,
        reference=_RBI_AGENTS_REF,
        clause=None,
        requirement=(
            "Recovery agents must not resort to intimidation or harassment, "
            "verbal or physical, in the recovery process."
        ),
        encoded_as=(
            "Message tone intensity (0 neutral … 3 firm) is capped by genuine "
            "attempt history: ≤1 on the first contact, ≤2 on the second, ≤3 "
            "thereafter. An escalation ladder cannot open at its top rung."
        ),
        confidence="primary",
        note=(
            "The prohibition is the circular's; the 0–3 intensity scale is "
            "this project's invention. No regulator publishes a numeric tone "
            "scale — this is a machine-checkable proxy for it, not a "
            "restatement of law."
        ),
        url=_RBI_URL,
    ),
    # ── TRAI TCCCPR ──────────────────────────────────────────────────────
    "TCCCPR.DLT.REGISTERED": Citation(
        kind="regulation",
        instrument=_TCCCPR,
        reference=_TCCCPR_REF,
        clause=None,
        requirement=(
            "Commercial communication may be sent only by senders registered "
            "on the distributed-ledger (DLT) platform, using registered "
            "headers and registered content templates."
        ),
        encoded_as="An unregistered sender or template denies the action.",
        confidence="spec",
        url=_TCCCPR_URL,
    ),
    "TCCCPR.HEADER.CLASS_MATCH": Citation(
        kind="regulation",
        instrument=_TCCCPR,
        reference=_TCCCPR_REF,
        clause=None,
        requirement=(
            "Headers are registered against a communication category, and a "
            "header may not be used to send a different category of message."
        ),
        encoded_as=(
            "The template's registered class (-P/-S/-T/-G) must equal the "
            "message's declared class. Promotional content on a service "
            "header is denied."
        ),
        confidence="spec",
        url=_TCCCPR_URL,
    ),
    "TCCCPR.CONSENT.VALIDITY": Citation(
        kind="regulation",
        instrument=_TCCCPR,
        reference=_TCCCPR_REF,
        clause=None,
        requirement=(
            "Commercial communication requires a valid basis — explicit "
            "consent, or an inferred basis arising from an existing "
            "relationship — and that basis can lapse."
        ),
        encoded_as=(
            "Inferred consent lapses when the underlying contract is no "
            "longer active; explicit consent for service-class messages "
            "expires 7 days after capture."
        ),
        confidence="spec",
        note=(
            "The 7-day expiry is the least certain rule in the kernel. "
            "COMPLIANCE.md records the ambiguity rather than resolving it "
            "silently: the project chose the stricter reading, which can only "
            "cost recovery, never compliance."
        ),
        url=_TCCCPR_URL,
    ),
    "TCCCPR.OPT_OUT.OPTION_PRESENT": Citation(
        kind="regulation",
        instrument=_TCCCPR,
        reference=_TCCCPR_REF,
        clause=None,
        requirement=(
            "Promotional communication must carry a means for the recipient "
            "to opt out."
        ),
        encoded_as=(
            "Promotional-class messages without an opt-out affordance are "
            "denied. Service and transactional classes are exempt from this "
            "specific check."
        ),
        confidence="spec",
        url=_TCCCPR_URL,
    ),
    "TCCCPR.OPT_OUT.COOLING": Citation(
        kind="regulation",
        instrument=_TCCCPR,
        reference=_TCCCPR_REF,
        clause=None,
        requirement=(
            "A recipient's revocation of consent must be honoured, and a "
            "sender may not immediately re-solicit consent after it."
        ),
        encoded_as=(
            "After an opt-out, no further contact and no consent request for "
            "90 days unless the customer opts back in."
        ),
        confidence="spec",
        url=_TCCCPR_URL,
    ),
    "TCCCPR.NUMBER_SERIES": Citation(
        kind="regulation",
        instrument=_TCCCPR,
        reference=_TCCCPR_REF,
        clause=None,
        requirement=(
            "Commercial calling and messaging must originate from the "
            "numbering series allocated for that category — the 140 series "
            "for promotional traffic, the 160 series for transactional and "
            "service traffic."
        ),
        encoded_as=(
            "The sender's number series must match the declared message "
            "class."
        ),
        confidence="spec",
        note=(
            "Series allocation has been directed by TRAI across several "
            "instruments rather than one clause; the project models it as a "
            "single series-to-class check."
        ),
        url=_TCCCPR_URL,
    ),
    # ── e-mandate ────────────────────────────────────────────────────────
    "EMANDATE2026.PRE_DEBIT_NOTICE": Citation(
        kind="circular",
        instrument="RBI framework for e-mandates on recurring transactions",
        reference=None,
        clause=None,
        requirement=(
            "The issuer must send the customer a pre-debit notification at "
            "least 24 hours before a recurring mandate is charged, carrying "
            "the transaction details and a way to opt out."
        ),
        encoded_as=(
            "A debit attempt (modelled as RETRY against a mandate-backed "
            "case) is denied unless a pre-debit notice was sent ≥24 hours "
            "earlier."
        ),
        confidence="spec",
        note=(
            "The rule id names the buildathon spec's forward-dated "
            "'E-Mandate Framework, 2026'. The 24-hour pre-debit notification "
            "it describes is the same requirement RBI's existing e-mandate "
            "framework for recurring transactions already imposes, which is "
            "why the rule is encoded against a real obligation rather than a "
            "hypothetical one. AFA requirements for mandate registration and "
            "modification are deliberately not encoded — no ActionType in "
            "this project can register or modify a mandate, so the rule "
            "would be vacuous."
        ),
        url=_RBI_URL,
    ),
    # ── data protection ──────────────────────────────────────────────────
    "DPDPA.CONSENT_RECORD": Citation(
        kind="statute",
        instrument="Digital Personal Data Protection Act, 2023",
        reference="Act No. 22 of 2023",
        clause="ss. 5–6 (notice and consent)",
        requirement=(
            "Personal data may be processed only for a lawful purpose for "
            "which the data principal has given consent, preceded by notice."
        ),
        encoded_as=(
            "Customer contact requires an on-record consent capture "
            "timestamp. The rule checks that a record exists, not that the "
            "consent is still current — TCCCPR.CONSENT.VALIDITY does that."
        ),
        confidence="primary",
        note=(
            "Purpose limitation and retention are not encoded as per-action "
            "rules. They are properties of what the system stores, not "
            "predicates about one candidate action; COMPLIANCE.md records "
            "retention as an open gap rather than faking a rule for it."
        ),
        url="https://www.meity.gov.in/",
    ),
    # ── this project's own operating limits, not law ─────────────────────
    "POLICY.CONTACT_BUDGET": Citation(
        kind="policy",
        instrument=None,
        reference=None,
        clause=None,
        requirement=(
            "Internal limit. No regulator sets this number; the project sets "
            "it so an agent cannot pursue one customer indefinitely."
        ),
        encoded_as=(
            "At most 3 contact attempts per rolling 7-day window per case."
        ),
        confidence="primary",
        note="Policy, not law. Tightening it costs recovery and breaks nothing.",
    ),
    "POLICY.PROMISE_TO_PAY_WINDOW": Citation(
        kind="policy",
        instrument=None,
        reference=None,
        clause=None,
        requirement=(
            "Internal limit, adopted because chasing a customer who has "
            "already committed to a date is the harassment pattern the RBI "
            "norms exist to prevent, even where no single message breaches "
            "them."
        ),
        encoded_as=(
            "Once a customer promises a payment date, contact is denied "
            "until that date plus a two-day grace period."
        ),
        confidence="primary",
        note="Policy, not law — but the reason for it is the law's reason.",
    ),
    "POLICY.NEGOTIATION_ENVELOPE": Citation(
        kind="policy",
        instrument=None,
        reference=None,
        clause=None,
        requirement=(
            "Internal limit. The agent may not concede more than the "
            "envelope the operator authorised, and may not offer a discount "
            "that destroys more value than the delay it avoids."
        ),
        encoded_as=(
            "A settlement offer is denied if it exceeds the authorised "
            "discount ceiling or the case's autonomy limit in rupees."
        ),
        confidence="primary",
        note=(
            "The envelope is sized against Section 43B(h) of the Income-tax "
            "Act, 1961 (inserted by the Finance Act, 2023) read with s. 15 "
            "of the MSMED Act, 2006: a buyer who does not pay a micro or "
            "small enterprise within the statutory window has the deduction "
            "deferred to the year of actual payment, which is what makes "
            "early settlement the buyer's own interest. That statute shapes "
            "the negotiation; it does not impose this rule."
        ),
    ),
}


def citation_for(rule_name: str) -> Citation | None:
    """The source for a rule, or None if the rule is not registered."""
    return REGISTRY.get(rule_name)


def registry_json() -> dict[str, dict]:
    """The whole registry, for the dashboard to resolve rule names against."""
    return {name: c.to_dict() for name, c in REGISTRY.items()}
