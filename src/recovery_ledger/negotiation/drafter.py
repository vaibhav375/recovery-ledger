"""Negotiation message drafting (spec section 9.4).

The LLM's job here is narrow and worth stating precisely, because the
division of labour is the design:

- the **solver** decided whether to concede anything and how much
- the **43B(h) clock** computed the counterparty's own tax position
- the **kernel** will approve or refuse the concession
- the **LLM** writes the sentence

It is given the numbers; it does not choose them. That is deliberate. Asked
to negotiate freely, a language model will happily invent a discount, and a
fluent invented discount is exactly the failure mode that makes agents
undeployable in a business that has to honour what it offers.

The drafted text is checked before use: any figure the model introduces that
was not supplied is grounds for falling back to a deterministic template.

**A limitation worth stating plainly, because grounding is easy to oversell.**
This checks NUMBERS, not MEANING. A small model can respect every supplied
figure and still garble the sentence around it — an observed qwen2.5:3b draft
said settling would "allow you to claim a deferral cost of approximately
Rs 10,200", which inverts what a deferral cost is. Numeric grounding cannot
catch that, and nothing here claims otherwise. Two things follow:

- `_template()` is always correct and always available, so the safe path is
  never more than one fallback away;
- for anything legally or financially load-bearing, the honest position is
  that a human reviews the wording. Semantic verification of generated text
  is an open problem, not one this project has solved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from recovery_ledger.llm.client import LLMClient, OllamaUnavailableError
from recovery_ledger.negotiation.clock import Section43BhStatus
from recovery_ledger.negotiation.solver import Offer, OfferType

SYSTEM = (
    "You write short, professional B2B payment-follow-up messages for an Indian "
    "supplier chasing an overdue invoice. Two or three sentences. Courteous and "
    "factual, never threatening. Use ONLY the figures you are given. Never invent "
    "an amount, a percentage, or a date."
)


@dataclass
class DraftedMessage:
    text: str
    used_llm: bool
    grounded: bool          # every number in the text was one we supplied
    rationale: str


def _template(amount: float, offer: Offer, status: Section43BhStatus) -> str:
    """Deterministic fallback. Always correct, never eloquent."""
    parts = [f"Invoice for Rs {amount:,.0f} is outstanding."]
    if status.applies and not status.breached:
        parts.append(
            f"{status.days_until_deadline} days remain in the 45-day MSME payment window; "
            f"settling within it keeps this expense deductible for you in the current "
            f"financial year under Section 43B(h)."
        )
    elif status.applies and status.breached:
        parts.append(
            f"The 45-day MSME window closed {abs(status.days_until_deadline)} days ago, so "
            f"under Section 43B(h) this deduction now moves to the year of actual payment."
        )
    if offer.offer_type == OfferType.EARLY_PAYMENT_DISCOUNT:
        parts.append(f"We can offer a {offer.discount_pct:.1%} early-payment discount if settled now.")
    elif offer.offer_type == OfferType.EXTENDED_TERMS:
        parts.append(f"We can extend terms by {offer.extension_days} days if that helps.")
    return " ".join(parts)


def _allowed_numbers(amount: float, offer: Offer, status: Section43BhStatus) -> set[str]:
    """Every figure the model was actually handed.

    This set was initially incomplete — it omitted the 43B(h) deferral cost,
    which `leverage_note()` supplies in the prompt. The result was that every
    draft correctly citing that figure got rejected as ungrounded and fell
    back to the template, so the LLM path would never have run at all. Caught
    by reading the rejected drafts instead of trusting the rejection: the
    model was right and the checker was wrong.
    """
    allowed = {f"{amount:.0f}", f"{round(amount):,}".replace(",", ""), "45", "43"}
    if offer.discount_pct:
        allowed |= {f"{offer.discount_pct * 100:.1f}", f"{offer.discount_pct * 100:.0f}"}
    if offer.extension_days:
        allowed.add(str(offer.extension_days))
    if status.applies:
        allowed.add(str(abs(status.days_until_deadline)))
        # the deferral cost is quoted in leverage_note(), so it is supplied
        allowed |= {
            f"{status.deferral_cost:.0f}",
            f"{round(status.deferral_cost):,}".replace(",", ""),
        }
    return allowed


def is_grounded(text: str, amount: float, offer: Offer, status: Section43BhStatus) -> bool:
    """True if every number in the draft is one we supplied.

    A negotiation message is a commitment. A model that writes "we can do 8%"
    when the solver authorised 3% has created an obligation the business did
    not agree to — so an ungrounded draft is discarded rather than sent.
    """
    allowed = _allowed_numbers(amount, offer, status)
    for raw in re.findall(r"\d[\d,]*\.?\d*", text):
        cleaned = raw.replace(",", "").rstrip(".")
        if cleaned in allowed:
            continue
        # tolerate the amount written with separators, and small ordinals
        if cleaned == f"{amount:.0f}" or cleaned in {"1", "2", "3", "2026", "2025"}:
            continue
        return False
    return True


@dataclass
class NegotiationDrafter:
    """Drafts the outbound negotiation message.

    `prefer_llm` defaults to **False**, and that default is a finding rather
    than caution. With numeric grounding passing, qwen2.5:3b still produced
    drafts that were legally wrong about Section 43B(h):

    - "Settling now will allow you to *claim* a deferral cost of Rs 10,200"
      — inverted; settling *avoids* that cost
    - "the MSME payment window closed 45 days ago" — it had closed 35 days
      ago; the model conflated the window's length with elapsed time. Both
      45 and 35 were legitimately supplied figures, so the grounding check
      could not catch it
    - "the associated *penalty* under Section 43B(h)" — there is no penalty;
      the deduction is deferred

    A negotiation message is a financial communication to a counterparty. A
    fluent, confident, wrong statement about their tax position is worse than
    a plain correct one, and would destroy the credibility the 43B(h)
    argument depends on. So the deterministic template is the default here,
    and the LLM is opt-in for contexts where a human reviews the wording.

    This is the same judgement as the compliance kernel, reached the same
    way — by measuring where a language model is and is not trustworthy,
    rather than by assuming either.
    """

    client: LLMClient
    prefer_llm: bool = False

    def draft(self, *, amount: float, offer: Offer, status: Section43BhStatus) -> DraftedMessage:
        fallback = _template(amount, offer, status)
        if not self.prefer_llm:
            return DraftedMessage(
                fallback, used_llm=False, grounded=True,
                rationale=(
                    "deterministic template (default): observed LLM drafts made "
                    "legally inaccurate claims about Section 43B(h) that numeric "
                    "grounding cannot detect"
                ),
            )

        facts = [f"Outstanding amount: Rs {amount:,.0f}"]
        if status.applies:
            facts.append(status.leverage_note())
        if offer.offer_type == OfferType.EARLY_PAYMENT_DISCOUNT:
            facts.append(f"Authorised concession: {offer.discount_pct:.1%} early-payment discount")
        elif offer.offer_type == OfferType.EXTENDED_TERMS:
            facts.append(f"Authorised concession: extend terms by {offer.extension_days} days")
        else:
            facts.append("Authorised concession: none — do not offer any discount")

        prompt = (
            "Write the follow-up message using only these facts:\n"
            + "\n".join(f"- {f}" for f in facts)
            + "\n\nMessage:"
        )
        try:
            text = self.client.complete(prompt, system=SYSTEM, temperature=0.4).strip()
        except OllamaUnavailableError:
            return DraftedMessage(fallback, used_llm=False, grounded=True,
                                  rationale="LLM unavailable; deterministic template used")

        if not text or not is_grounded(text, amount, offer, status):
            return DraftedMessage(
                fallback, used_llm=False, grounded=True,
                rationale="draft introduced a figure that was not authorised; template used instead",
            )
        return DraftedMessage(text, used_llm=True, grounded=True,
                              rationale="LLM draft, all figures grounded in supplied facts")
