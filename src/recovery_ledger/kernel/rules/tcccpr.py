"""TRAI TCCCPR, including 2025 amendments (spec section 9.2). Sources cited
in full in COMPLIANCE.md.

Silent actions (RETRY) are exempt from every rule here — none of these are
about payment retries, they're about commercial *communications*, and a
silent retry sends nothing to the customer.
"""

from __future__ import annotations

from datetime import timedelta

from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import Channel
from recovery_ledger.kernel.certificate import RuleResult
from recovery_ledger.kernel.engine import RuleContext

EXPLICIT_SERVICE_CONSENT_VALIDITY_DAYS = 7


def _is_customer_contact(context: RuleContext) -> bool:
    return context.action_type != ActionType.RETRY


class DLTRegistrationRule:
    """All commercial comms must be DLT-registered before transmission."""

    name = "TCCCPR.DLT.REGISTERED"

    def evaluate(self, context: RuleContext) -> RuleResult:
        if not _is_customer_contact(context):
            return RuleResult(rule_name=self.name, passed=True, detail={"exempt": True})
        ok = context.dlt.registered
        return RuleResult(
            rule_name=self.name, passed=ok,
            detail={"registered": context.dlt.registered, "header": context.dlt.header},
        )


class HeaderClassMatchRule:
    """Header suffix (-P/-S/-T/-G) must match the class of message actually
    being sent. We model this as: the DLT template this action would use is
    registered under a class, and that class must equal the message's
    declared class."""

    name = "TCCCPR.HEADER.CLASS_MATCH"

    def evaluate(self, context: RuleContext) -> RuleResult:
        if not _is_customer_contact(context):
            return RuleResult(rule_name=self.name, passed=True, detail={"exempt": True})
        ok = context.dlt.template_class == context.message_class
        return RuleResult(
            rule_name=self.name, passed=ok,
            detail={"template_class": context.dlt.template_class, "message_class": context.message_class},
        )


class ConsentValidityRule:
    """Inferred consent doesn't extend beyond the duration/discharge of the
    contract; explicit consent for service comms expires after 7 days.

    Read literally from the spec as cited — this project's own risk register
    (spec section 16) flags this exact clause as one to state "as I read it"
    where genuinely ambiguous: it isn't fully clear from the source whether
    ALL explicit consent for service-class messages lapses in 7 days, or
    only consent captured for a different original purpose. Encoded here as
    the strict/conservative reading (re-validate every 7 days) because a
    deny-by-default kernel should fail toward *more* restrictive when a rule
    is ambiguous, not less. See COMPLIANCE.md."""

    name = "TCCCPR.CONSENT.VALIDITY"

    def evaluate(self, context: RuleContext) -> RuleResult:
        if not _is_customer_contact(context):
            return RuleResult(rule_name=self.name, passed=True, detail={"exempt": True})

        consent = context.consent
        if consent.basis == "inferred":
            ok = consent.contract_active
            return RuleResult(
                rule_name=self.name, passed=ok,
                detail={"basis": "inferred", "contract_active": consent.contract_active},
            )

        # explicit
        if consent.captured_at is None:
            return RuleResult(rule_name=self.name, passed=False, detail={"basis": "explicit", "captured_at": None})

        if context.message_class == "service":
            age = context.now_ist - consent.captured_at
            ok = age <= timedelta(days=EXPLICIT_SERVICE_CONSENT_VALIDITY_DAYS)
            return RuleResult(
                rule_name=self.name, passed=ok,
                detail={
                    "basis": "explicit", "message_class": "service",
                    "captured_at": str(consent.captured_at), "age_days": age.days,
                    "validity_days": EXPLICIT_SERVICE_CONSENT_VALIDITY_DAYS,
                },
            )

        return RuleResult(
            rule_name=self.name, passed=True,
            detail={"basis": "explicit", "message_class": context.message_class},
        )


class OptOutOptionPresentRule:
    """Every promotional message must carry an opt-out option."""

    name = "TCCCPR.OPT_OUT.OPTION_PRESENT"

    def evaluate(self, context: RuleContext) -> RuleResult:
        if not _is_customer_contact(context) or context.message_class != "promotional":
            return RuleResult(rule_name=self.name, passed=True, detail={"exempt": True})
        ok = context.includes_opt_out_option
        return RuleResult(rule_name=self.name, passed=ok, detail={"includes_opt_out_option": ok})


class NumberSeriesRule:
    """140-series exclusively for promotional voice; 160-series for
    service/transactional (not subject to scrubbing). Ordinary 10-digit
    numbers for commercial voice/SMS risk disconnection and blacklisting."""

    name = "TCCCPR.NUMBER_SERIES"

    def evaluate(self, context: RuleContext) -> RuleResult:
        if not _is_customer_contact(context) or context.channel not in (Channel.VOICE, Channel.SMS):
            return RuleResult(rule_name=self.name, passed=True, detail={"exempt": True})

        series = context.sender_number_series
        if context.channel == Channel.VOICE and context.message_class == "promotional":
            ok = series == "140"
        elif context.message_class in ("service", "transactional"):
            ok = series == "160"
        else:
            ok = series in ("140", "160")
        return RuleResult(
            rule_name=self.name, passed=ok,
            detail={"channel": context.channel.value, "message_class": context.message_class, "series": series},
        )
