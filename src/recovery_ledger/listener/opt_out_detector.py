"""Deterministic opt-out detection — a safety net under the LLM classifier.

Measured motivation, not a precaution invented after the fact. Evaluated
against the hand-authored gold set, qwen2.5:3b classified opt-out replies
with **recall 0.57**: it missed 3 of 7, and every miss was Hindi or
Hinglish — "कृपया मुझसे दोबारा संपर्क न करें" ("please do not contact me
again") came back as `wrong_person`.

Every other intent being occasionally wrong costs money. Opt-out being wrong
costs compliance: under TCCCPR, continuing to contact someone who asked you
to stop is a violation, and it starts a 90-day cooling obligation the agent
would never know to honour. That is precisely the class of decision this
project argues should not rest on a language model (README, "where AI is
used and where it is deliberately not").

So opt-out gets a deterministic detector that runs **before** the LLM and
overrides it. Rules are auditable, they behave identically every run, and
they do not degrade when a local model is swapped or unavailable.

**Bias is deliberate and asymmetric.** A false positive stops contact with
someone who did not actually ask — a revenue cost. A false negative keeps
messaging someone who did — a regulatory breach. These are not symmetric,
so the patterns lean toward detection.
"""

from __future__ import annotations

import re

# Matched case-insensitively against the raw reply. Grouped by language for
# reviewability — a compliance reviewer should be able to read this list.
OPT_OUT_PATTERNS: list[str] = [
    # English
    r"\bstop\s+(messag|text|call|contact|send)",
    r"\bdo\s*n[o']?t\s+(contact|message|text|call)",
    r"\bdon'?t\s+(contact|message|text|call)",
    r"\bunsubscribe\b",
    r"\bremove\s+my\s+(number|contact|name)",
    r"\bno\s+more\s+(messages|texts|calls)",
    r"\bleave\s+me\s+alone\b",
    r"\bopt\s*out\b",
    r"\btake\s+me\s+off\b",
    # Hinglish (Roman script)
    r"\bmat\s+(bhejo|bhejna|bhej|karo\s+contact|karo\s+message)",
    r"\bmessage\s+(mat|band|nahi\s+chahiye)",
    r"\bnumber\s+(hata|hatao|delete)",
    # Imperative only. "band karo" = "stop it"; "band kar diya" = "I cancelled
    # it", which is a DISPUTE, not an opt-out. The optional-suffix version of
    # this pattern matched both and produced a false positive on
    # "maine to subscription band kar diya tha, phir charge kyun hua".
    r"\bband\s+kar(o|do|iye)\b(?!\s*diya)",
    r"\bbas\s+karo\b",
    r"\bpareshan\s+mat\b",
    r"\bnahi\s+chahiye\s+(message|msg)",
    # Hindi (Devanagari)
    r"संदेश\s*मत",
    r"मैसेज\s*मत",
    r"संपर्क\s*न\s*कर",
    r"संपर्क\s*मत",
    r"नंबर\s*हटा",
    r"परेशान\s*मत",
    r"दोबारा\s*न\s*कर",
    r"और\s*संदेश\s*मत",
]

_COMPILED = [re.compile(p, re.IGNORECASE | re.UNICODE) for p in OPT_OUT_PATTERNS]


def is_opt_out(text: str) -> bool:
    """True if the reply unambiguously asks for contact to stop."""
    return any(p.search(text) for p in _COMPILED)


def matched_patterns(text: str) -> list[str]:
    """Which patterns fired — so a denial can be justified in the audit trail
    rather than being an opaque verdict."""
    return [p.pattern for p in _COMPILED if p.search(text)]
