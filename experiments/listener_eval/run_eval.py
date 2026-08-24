"""Reply-intent classification accuracy against a labelled set (spec 8.5).

Spec section 8.5 permits an LLM for inbound reply classification on the
condition that it is "validated against a labelled set, report accuracy".
This is that validation.

The labelled set is the cached persona corpus (`data/persona_corpus.json`):
each reply's label is the intent that *generated* it, so labels come for
free by construction. That has a caveat this report does not hide — a small
model sometimes writes a line that drifts off its own brief, so some labels
are wrong. Disagreements are therefore sampled and printed, so the reader
can see how much of the error is the classifier and how much is the corpus.

Promise-to-pay precision/recall is reported separately because spec section
11.2 asks for it by name, and opt-out recall is called out because it is the
one intent where a miss has a compliance consequence rather than merely an
economic one.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from recovery_ledger.listener.listener import ReplyIntent
from recovery_ledger.listener.llm_listener import LLMListener
from recovery_ledger.llm.client import OllamaClient, build_default_client
from recovery_ledger.sim.personas import PersonaGenerator

HERE = Path(__file__).parent


def prf(tp: int, fp: int, fn: int) -> tuple[float, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return precision, recall


def evaluate(listener: LLMListener, corpus) -> dict:
    predictions = [(r, listener.classify(r.text)) for r in corpus]
    correct = sum(1 for r, p in predictions if p == r.intent)

    by_lang: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    per_intent: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    confusion: Counter = Counter()

    for r, pred in predictions:
        lang = r.language.value
        by_lang[lang][1] += 1
        if pred == r.intent:
            by_lang[lang][0] += 1
            per_intent[r.intent.value]["tp"] += 1
        else:
            per_intent[r.intent.value]["fn"] += 1
            per_intent[pred.value]["fp"] += 1
            confusion[(r.intent.value, pred.value)] += 1

    intents = {}
    for name, c in per_intent.items():
        p, rc = prf(c["tp"], c["fp"], c["fn"])
        intents[name] = {"precision": round(p, 4), "recall": round(rc, 4), **c}

    return {
        "n": len(predictions),
        "accuracy": round(correct / len(predictions), 4) if predictions else 0.0,
        "accuracy_by_language": {k: round(v[0] / v[1], 4) for k, v in by_lang.items()},
        "per_intent": intents,
        "top_confusions": [{"true": t, "predicted": p, "n": n}
                           for (t, p), n in confusion.most_common(8)],
        "disagreements": [
            {"text": r.text, "true": r.intent.value, "predicted": pred.value,
             "language": r.language.value}
            for r, pred in predictions if pred != r.intent
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="qwen2.5:3b")
    ap.add_argument("--limit", type=int, default=0, help="0 = whole set")
    ap.add_argument("--set", choices=["gold", "generated"], default="gold",
                    help="gold = hand-authored labels (headline); generated = LLM persona corpus")
    args = ap.parse_args()

    if args.set == "gold":
        import sys as _sys
        _sys.path.insert(0, str(HERE))
        from gold_set import gold_replies
        corpus = gold_replies()
    else:
        corpus = PersonaGenerator(build_default_client()).load_cache()
        if not corpus:
            raise SystemExit("No cached corpus. Generate it first (see personas.py).")
    if args.limit:
        corpus = corpus[: args.limit]

    listener = LLMListener(client=OllamaClient(model=args.model), reply_source=lambda *a: None)
    print(f"Classifying {len(corpus)} labelled replies with {args.model} ...")
    result = evaluate(listener, corpus)
    result["model"] = args.model
    result["set"] = args.set

    print(f"\nOverall accuracy: {result['accuracy']:.1%}  (n={result['n']})")
    print("By language:", {k: f"{v:.1%}" for k, v in result["accuracy_by_language"].items()})
    print(f"\n{'intent':18s} {'precision':>10s} {'recall':>8s}   tp/fp/fn")
    for name, m in sorted(result["per_intent"].items()):
        print(f"  {name:16s} {m['precision']:>10.2f} {m['recall']:>8.2f}   {m['tp']}/{m['fp']}/{m['fn']}")

    print("\nMost common confusions (true -> predicted):")
    for c in result["top_confusions"]:
        print(f"  {c['true']:16s} -> {c['predicted']:16s} x{c['n']}")

    print("\nSample disagreements (is this a classifier error, or a bad label?):")
    for d in result["disagreements"][:10]:
        print(f"  [{d['true']} -> {d['predicted']}] {d['text']}")

    (HERE / f"results_listener_{args.set}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nWrote {HERE / f'results_listener_{args.set}.json'}")


if __name__ == "__main__":
    main()
