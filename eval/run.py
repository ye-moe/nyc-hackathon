"""Precision / recall / confusion matrix, overall and per rule.

    python -m eval.run                       # dev set, offline regex extractor
    python -m eval.run --holdout             # held-out v1 (contaminated)
    python -m eval.run --v2                  # blind held-out v2: the number for the pitch
    python -m eval.run --v2 --gemini         # with Gemini extraction (needs GEMINI_API_KEY)
    python -m eval.run --file data/labeled/real.jsonl -v

Labeled rows: {id, text, label: violation|needs_review|no_issue_found, hints?, verified_by}
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from core import analyze

ROOT = Path(__file__).resolve().parent.parent
LABELS = ["violation", "needs_review", "no_issue_found"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--holdout", action="store_true")
    ap.add_argument("--v2", action="store_true")
    ap.add_argument("--gemini", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    path = Path(a.file) if a.file else ROOT / "data/labeled" / ("holdout_v2.jsonl" if a.v2 else "holdout.jsonl" if a.holdout else "dev.jsonl")
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

    m = {g: {p: 0 for p in LABELS} for g in LABELS}
    per_rule = {r: {"tp": 0, "fp": 0} for r in ("R1", "R2", "R3")}
    misses = []
    for row in rows:
        r = analyze({"id": row["id"], "text": row["text"], "hints": row.get("hints")}, use_gemini=a.gemini)
        m[row["label"]][r.verdict] += 1
        # A rule "fires" when it raised a review or violation; correct if gold isn't no_issue_found.
        for rid in {f.rule_id for f in r.flags if f.severity != "info" and f.rule_id != "R4"}:
            per_rule[rid]["fp" if row["label"] == "no_issue_found" else "tp"] += 1
        if r.verdict != row["label"]:
            misses.append(f"  {row['id']}  gold={row['label']:<14} got={r.verdict:<14} {row['text'][:70]}")
            if a.verbose:
                misses += [f"        {f.rule_id} {f.code} ({f.severity}): \"{f.evidence_text}\"" for f in r.flags]

    pct = lambda n, d: f"{100 * n / d:.1f}%" if d else "n/a"
    v_tp = m["violation"]["violation"]
    v_pred = sum(m[l]["violation"] for l in LABELS)
    v_gold = sum(m["violation"].values())
    flagged = lambda l: m[l]["violation"] + m[l]["needs_review"]
    clean_gold = sum(m["no_issue_found"].values())
    unverified = sum(1 for r in rows if not r.get("verified_by"))

    print(f"\n{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}  n={len(rows)}  extractor={'gemini' if a.gemini else 'regex (offline)'}")
    print("─" * 64)
    print(f"violation precision   {pct(v_tp, v_pred):>7}   ({v_tp}/{v_pred})  <- protect this")
    print(f"violation recall      {pct(v_tp, v_gold):>7}   ({v_tp}/{v_gold})")
    print(f"caught (viol+review)  {pct(flagged('violation'), v_gold):>7}   unlawful listings that reach a human")
    print(f"false alarms          {pct(flagged('no_issue_found'), clean_gold):>7}   lawful listings flagged at all")
    print(f"exact-label accuracy  {pct(sum(m[l][l] for l in LABELS), len(rows)):>7}")
    print("\nconfusion matrix (rows = gold, cols = predicted)")
    print(" " * 16 + "".join(f"{l:>16}" for l in LABELS))
    for g in LABELS:
        print(f"{g:<16}" + "".join(f"{m[g][p]:>16}" for p in LABELS))
    print("\nper rule (fired = raised review or violation)")
    for rid, c in per_rule.items():
        print(f"  {rid}  fired {c['tp'] + c['fp']:>3}   precision {pct(c['tp'], c['tp'] + c['fp']):>7}   ({c['fp']} on lawful listings)")
    if misses:
        print("\nmismatches\n" + "\n".join(misses))
    if unverified:
        print(f"\n⚠ {unverified}/{len(rows)} labels have no verified_by. Have a person check each one before quoting these numbers.")


if __name__ == "__main__":
    main()
