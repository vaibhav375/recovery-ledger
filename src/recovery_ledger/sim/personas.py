"""LLM-generated customer replies (spec section 7.3).

The simulator decides a customer's *intent*; this turns that intent into the
kind of free text a real person would actually send — in English, Hindi, or
Hinglish. That matters for two reasons:

1. It forces the Listener to be real. Classifying a synthetic enum back into
   itself proves nothing; classifying "bhai paisa kat gaya tha, phir bhi
   message aa raha hai" proves something.
2. **It generates its own labelled set.** Because the ground-truth intent is
   what produced the text, every generated reply is labelled by
   construction — which is exactly what spec section 8.5 requires when it
   says reply-intent classification must be "validated against a labelled
   set" with reported accuracy.

Generation is cached to disk. A cached corpus makes the listener evaluation
reproducible by anyone who clones this repo *without* needing Ollama
installed, and keeps repeat runs instant instead of minutes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from recovery_ledger.events.schemas import Language
from recovery_ledger.listener.listener import ReplyIntent
from recovery_ledger.llm.client import LLMClient, MockLLMClient

DEFAULT_CACHE = Path(__file__).resolve().parents[3] / "data" / "persona_corpus.json"

# What each intent means, phrased as a situation rather than a label, so the
# model writes a person rather than a category.
INTENT_BRIEF: dict[ReplyIntent, str] = {
    ReplyIntent.PAID: "You have already paid this. You are mildly irritated at being chased for it.",
    ReplyIntent.PROMISE_TO_PAY: "You cannot pay right now but you will on a specific near-future date, usually payday.",
    ReplyIntent.DISPUTE: "You believe the amount or the charge itself is wrong and you are contesting it.",
    ReplyIntent.OPT_OUT: "You want them to stop contacting you entirely. Firm, not abusive.",
    ReplyIntent.WRONG_PERSON: "They have the wrong number. This is not your account and you do not know who they mean.",
    ReplyIntent.NEGOTIATE: "You want to pay less, or in instalments, or you are asking for more time in exchange for something.",
}

LANGUAGE_BRIEF: dict[Language, str] = {
    Language.EN: "plain Indian English",
    Language.HI: "Hindi written in Devanagari script",
    Language.HINGLISH: "Hinglish — Hindi and English mixed, written in Roman script, the way people actually text",
}

SYSTEM = (
    "You write short, realistic replies from Indian customers to a payment-recovery "
    "message. One or two sentences. Casual, like a real SMS or WhatsApp reply. "
    "Never explain yourself, never use quotation marks, never number the lines."
)

# Few-shot style anchors, per language. Measured, not assumed: without these
# qwen2.5:3b produced barely-coherent Hinglish ("Sab kochi? Bhai aapke yaar pay
# day ho jayega") while with them it produces "Abhi paise nahi hoga, 15th
# January ka salary aayega tab karunga". The examples anchor register and
# script; they deliberately span different intents so they steer *style*
# rather than leaking the target intent.
STYLE_ANCHORS: dict[Language, str] = {
    Language.EN: (
        "i already paid this last week, please check your records\n"
        "dont message me again about this\n"
        "can you give me time till month end"
    ),
    Language.HI: (
        "मैंने पिछले हफ्ते ही भुगतान कर दिया है, कृपया जाँच लें\n"
        "मुझे अब और संदेश मत भेजिए\n"
        "क्या महीने के अंत तक समय मिल सकता है"
    ),
    Language.HINGLISH: (
        "maine already pay kar diya hai, apna record check karo\n"
        "mujhe aur message mat bhejo please\n"
        "bhai month end tak time mil sakta hai kya"
    ),
}


@dataclass(frozen=True)
class LabelledReply:
    """A customer reply whose true intent is known because it produced it."""

    text: str
    intent: ReplyIntent
    language: Language


def _prompt(intent: ReplyIntent, language: Language, n: int) -> str:
    return (
        f"Style reference — how real customers write (do NOT copy these, they are "
        f"different situations):\n{STYLE_ANCHORS[language]}\n\n"
        f"Now write {n} different replies from a customer in this situation:\n"
        f"{INTENT_BRIEF[intent]}\n\n"
        f"Language: {LANGUAGE_BRIEF[language]}.\n"
        f"Every line must clearly express that situation and nothing else.\n"
        f"Output exactly {n} lines. One reply per line. No numbering, no blank lines."
    )


def _parse_lines(raw: str, limit: int) -> list[str]:
    lines: list[str] = []
    for line in raw.splitlines():
        cleaned = line.strip().lstrip("0123456789.)-• ").strip().strip('"').strip()
        if len(cleaned) >= 4:
            lines.append(cleaned)
    return lines[:limit]


class PersonaGenerator:
    """Generates (and caches) labelled customer replies."""

    def __init__(self, client: LLMClient, *, cache_path: Path = DEFAULT_CACHE):
        self.client = client
        self.cache_path = cache_path

    def load_cache(self) -> list[LabelledReply]:
        if not self.cache_path.exists():
            return []
        raw = json.loads(self.cache_path.read_text())
        return [
            LabelledReply(text=r["text"], intent=ReplyIntent(r["intent"]), language=Language(r["language"]))
            for r in raw
        ]

    def build_corpus(
        self,
        *,
        per_combination: int = 6,
        languages: list[Language] | None = None,
        intents: list[ReplyIntent] | None = None,
    ) -> list[LabelledReply]:
        """One LLM call per (intent, language) pair, each returning several
        replies — batching keeps a ~100-example corpus to ~18 calls rather
        than ~100, which is the difference between a minute and a coffee."""
        languages = languages or [Language.EN, Language.HI, Language.HINGLISH]
        intents = intents or list(INTENT_BRIEF)

        corpus: list[LabelledReply] = []
        for intent in intents:
            for language in languages:
                raw = self.client.complete(
                    _prompt(intent, language, per_combination), system=SYSTEM, temperature=0.9
                )
                for text in _parse_lines(raw, per_combination):
                    corpus.append(LabelledReply(text=text, intent=intent, language=language))
        return corpus

    def save_cache(self, corpus: list[LabelledReply]) -> Path:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(
            [{"text": r.text, "intent": r.intent.value, "language": r.language.value} for r in corpus],
            indent=1, ensure_ascii=False,
        ))
        return self.cache_path


def mock_generator() -> PersonaGenerator:
    """Offline generator producing deterministic stand-in replies, so tests
    and a clean clone never require Ollama."""
    canned = {
        ReplyIntent.PAID: "I already paid this yesterday, please check",
        ReplyIntent.PROMISE_TO_PAY: "I will pay on the 5th when my salary comes",
        ReplyIntent.DISPUTE: "This amount is wrong, I never agreed to this charge",
        ReplyIntent.OPT_OUT: "Stop messaging me, remove my number",
        ReplyIntent.WRONG_PERSON: "Wrong number, I don't know this person",
        ReplyIntent.NEGOTIATE: "Can I pay half now and half next month",
    }
    return PersonaGenerator(MockLLMClient(responses={
        INTENT_BRIEF[i][:40]: "\n".join([text] * 6) for i, text in canned.items()
    }, default_response="\n".join(["I will pay soon"] * 6)))
