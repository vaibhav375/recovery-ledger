"""Negotiation: the 43B(h) clock, the NPV solver, the kernel envelope, and
the grounding guard on LLM-drafted offers (spec section 9.4)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import CustomerProfile, OverdueReceivableCase
from recovery_ledger.kernel.engine import RuleContext
from recovery_ledger.kernel.rules.negotiation import NegotiationEnvelopeRule
from recovery_ledger.llm.client import MockLLMClient
from recovery_ledger.negotiation.clock import MSME_PAYMENT_WINDOW_DAYS, evaluate_43bh
from recovery_ledger.negotiation.drafter import NegotiationDrafter, is_grounded
from recovery_ledger.negotiation.solver import (
    NegotiationSolver,
    Offer,
    OfferType,
    PolicyEnvelope,
    breakeven_discount,
)

NOW = datetime(2026, 8, 24, tzinfo=timezone.utc)


def _status(days_overdue_of_due=10, msme=True, amount=200_000.0):
    return evaluate_43bh(invoice_due_date=NOW - timedelta(days=days_overdue_of_due),
                         now=NOW, is_msme_counterparty=msme, amount=amount)


# --- Section 43B(h) clock ----------------------------------------------------

def test_clock_does_not_apply_to_non_msme_counterparties():
    assert _status(msme=False).applies is False


def test_clock_counts_down_from_the_45_day_window():
    s = _status(days_overdue_of_due=5)
    assert s.days_until_deadline == MSME_PAYMENT_WINDOW_DAYS - 5


def test_clock_reports_breach_after_the_window_closes():
    s = _status(days_overdue_of_due=60)
    assert s.breached and s.urgency == "breached"


def test_urgency_escalates_as_the_deadline_approaches():
    order = [_status(d).urgency for d in (5, 30, 42, 60)]
    assert order == ["routine", "elevated", "critical", "breached"]


def test_leverage_note_does_not_overstate_the_tax_consequence():
    """43B(h) DEFERS the deduction to the year of payment; it does not
    destroy it. Claiming otherwise would be wrong, and a CFO would know."""
    breached = _status(days_overdue_of_due=60).leverage_note().lower()
    assert "year payment is actually made" in breached or "year of actual payment" in breached
    assert "lose the deduction" not in breached


def test_deferral_cost_is_the_time_value_not_the_whole_deduction():
    s = _status(amount=1_000_000.0)
    assert 0 < s.deferral_cost < 0.25 * 1_000_000.0


# --- solver ------------------------------------------------------------------

def test_breakeven_discount_grows_with_delay():
    assert breakeven_discount(15, 0.18) < breakeven_discount(90, 0.18)


def test_breakeven_is_zero_for_no_delay():
    assert breakeven_discount(0, 0.18) == 0.0


def test_solver_never_exceeds_the_envelope():
    solver = NegotiationSolver(envelope=PolicyEnvelope(max_discount_pct=0.02))
    offer = solver.best_offer(amount=200_000, expected_delay_days=365)
    assert offer.discount_pct <= 0.02


def test_solver_declines_to_pay_for_leverage_it_already_has():
    """The 43B(h) showpiece: inside the counterparty's own window, settling
    early is already in THEIR interest, so conceding margin buys nothing."""
    offer = NegotiationSolver().best_offer(
        amount=200_000, expected_delay_days=90, days_until_43bh_deadline=10)
    assert offer.offer_type == OfferType.NONE
    assert offer.discount_pct == 0.0
    assert "43B(h)" in offer.rationale


def test_solver_escalates_above_the_autonomy_limit():
    offer = NegotiationSolver().best_offer(amount=900_000, expected_delay_days=90)
    assert offer.offer_type == OfferType.NONE
    assert "human" in offer.rationale.lower()


def test_solver_skips_a_discount_too_small_to_be_worth_offering():
    offer = NegotiationSolver().best_offer(amount=200_000, expected_delay_days=2)
    assert offer.offer_type == OfferType.NONE


# --- kernel envelope ---------------------------------------------------------

def _ctx(**kw):
    case = OverdueReceivableCase(
        case_id="r", customer=CustomerProfile(customer_id="b", is_b2b=True),
        amount_at_risk=kw.pop("amount", 200_000.0), detected_at=NOW, invoice_id="INV",
        due_date=NOW, days_overdue=30, is_msme_counterparty=True)
    return RuleContext(case=case, action_type=kw.pop("action", ActionType.NEGOTIATE),
                       channel=None, now_ist=NOW, attempts_in_window=0, attempt_cap=3,
                       window_days=7, **kw)


def test_envelope_allows_a_concession_within_bounds():
    assert NegotiationEnvelopeRule().evaluate(_ctx(offer_discount_pct=0.03)).passed


def test_envelope_denies_an_over_cap_discount_even_though_the_solver_would_not_propose_one():
    """The check lives in the kernel precisely so it holds when the component
    that proposed the number is wrong, swapped, or compromised."""
    assert not NegotiationEnvelopeRule().evaluate(_ctx(offer_discount_pct=0.10)).passed


def test_envelope_denies_over_long_extensions_and_too_many_instalments():
    assert not NegotiationEnvelopeRule().evaluate(_ctx(offer_extension_days=120)).passed
    assert not NegotiationEnvelopeRule().evaluate(_ctx(offer_instalments=9)).passed


def test_envelope_requires_a_human_above_the_autonomy_limit():
    assert not NegotiationEnvelopeRule().evaluate(_ctx(amount=900_000, offer_discount_pct=0.01)).passed


def test_envelope_is_exempt_for_actions_that_concede_nothing():
    assert NegotiationEnvelopeRule().evaluate(
        _ctx(action=ActionType.NUDGE, offer_discount_pct=0.99)).passed


# --- drafting guard ----------------------------------------------------------

def test_a_hallucinated_discount_is_rejected():
    offer = Offer(OfferType.NONE)
    assert not is_grounded("We can do 9% off if you pay today.", 340_000, offer, _status())


def test_supplied_figures_are_accepted():
    offer = Offer(OfferType.EARLY_PAYMENT_DISCOUNT, discount_pct=0.03)
    s = _status(amount=340_000)
    text = (f"Rs 340,000 is outstanding. {s.days_until_deadline} days remain in the "
            f"45-day window under Section 43B(h). We can offer 3.0%.")
    assert is_grounded(text, 340_000, offer, s)


def test_the_43bh_deferral_cost_counts_as_supplied():
    """It is quoted to the model in the prompt, so a draft citing it is
    grounded. Omitting it from the allow-list silently disabled the entire
    LLM path — every draft fell back to the template."""
    s = _status(amount=340_000)
    offer = Offer(OfferType.NONE)
    assert is_grounded(f"Settling avoids roughly Rs {s.deferral_cost:,.0f} in deferral cost.",
                       340_000, offer, s)


def test_ungrounded_draft_falls_back_to_the_deterministic_template():
    drafter = NegotiationDrafter(
        client=MockLLMClient(default_response="Pay Rs 999999 now for 40% off"), prefer_llm=True)
    msg = drafter.draft(amount=340_000, offer=Offer(OfferType.NONE), status=_status())
    assert msg.used_llm is False
    assert "999999" not in msg.text and "40%" not in msg.text


def test_negotiation_messages_use_the_template_by_default():
    """Measured decision, not caution: LLM drafts made legally inaccurate
    claims about 43B(h) that numeric grounding cannot catch (see the
    NegotiationDrafter docstring). A wrong statement about a counterparty's
    tax position is worse than a plain correct one."""
    drafter = NegotiationDrafter(client=MockLLMClient(default_response="anything at all"))
    msg = drafter.draft(amount=340_000, offer=Offer(OfferType.NONE), status=_status())
    assert msg.used_llm is False
    assert "340,000" in msg.text


def test_unavailable_model_still_produces_a_correct_message():
    from recovery_ledger.llm.client import OllamaClient
    drafter = NegotiationDrafter(client=OllamaClient(host="http://localhost:1", timeout_seconds=0.5))
    msg = drafter.draft(amount=340_000, offer=Offer(OfferType.NONE), status=_status())
    assert msg.used_llm is False and "340,000" in msg.text
