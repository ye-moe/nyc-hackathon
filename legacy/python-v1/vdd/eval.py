"""Score the classifier on the labeled edge-case set.

    python -m vdd.eval              # rules only, offline
    python -m vdd.eval --llm        # rules + Claude (needs ANTHROPIC_API_KEY)
    python -m vdd.eval --holdout    # held-out set: the honest number

"Flagged" means label == discriminatory. needs_review is reported separately;
it goes to a human and never auto-drafts a complaint, so it doesn't count
against precision.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from .classifier import classify
from .schema import Listing

DATA = Path(__file__).resolve().parent.parent / "data" / "labeled_edge_cases.jsonl"


def run(use_llm: bool, verbose: bool, path: Path = DATA) -> dict:
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    tp = fp = fn = tn = 0
    review = Counter()
    by_cat = defaultdict(lambda: Counter())
    errors = []
    for row in rows:
        c = classify(Listing.from_dict(row), use_llm=use_llm)
        flagged = c.label == "discriminatory"
        y = row["label"] == 1
        if c.label == "needs_review":
            review["unlawful" if y else "lawful"] += 1
        tp += flagged and y
        fp += flagged and not y
        fn += (not flagged) and y
        tn += (not flagged) and not y
        by_cat[row["category"]]["n"] += 1
        by_cat[row["category"]]["correct"] += flagged == y
        if flagged != y:
            errors.append((row, c))

    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    # Recall counting review as "caught": what a caseworker sees in their queue.
    recall_with_review = (tp + review["unlawful"]) / (tp + fn) if tp + fn else 0.0

    print(f"\n{path.name}  ({'rules + Claude' if use_llm else 'rules only'}, n={len(rows)})")
    print("-" * 52)
    print(f"precision            {precision:6.1%}   <- the number we optimize")
    print(f"false-positive rate  {fpr:6.1%}")
    print(f"recall (auto-flag)   {recall:6.1%}")
    print(f"recall (+ review)    {recall_with_review:6.1%}")
    print(f"F1                   {f1:6.3f}")
    print(f"sent to review       {review['unlawful']} unlawful, {review['lawful']} lawful")
    print(f"confusion            TP={tp} FP={fp} FN={fn} TN={tn}")
    print("\nper category (accuracy)")
    for cat, cnt in sorted(by_cat.items()):
        print(f"  {cat:24s} {cnt['correct']:2d}/{cnt['n']:2d}")
    if errors:
        print("\nmisses")
        for row, c in errors:
            kind = "FALSE POSITIVE" if c.label == "discriminatory" else f"missed ({c.label})"
            print(f"  [{kind}] {row['id']} conf={c.confidence:.2f}  {row['text'][:70]}")
            if verbose:
                for r in c.reasons:
                    print(f"      - {r}")
    return {"precision": precision, "recall": recall, "fpr": fpr, "f1": f1}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--holdout", action="store_true", help="score the held-out set (never tune rules on it)")
    a = ap.parse_args()
    run(a.llm, a.verbose, DATA.with_name("holdout.jsonl") if a.holdout else DATA)
