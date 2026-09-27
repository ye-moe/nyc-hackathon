"""Ensemble: rules first, Claude when rules are unsure, calibrated to favor precision.

Decision logic:
  1. Rules score >= 0.9 with no welcoming language -> flag without an LLM call.
  2. Otherwise, if an API key is set, ask Claude and blend the two scores.
  3. An LLM-only flag (rules found nothing) is capped in the review band unless
     its quoted evidence is found verbatim in the listing.
"""
from __future__ import annotations

from typing import Iterable, List

from . import config, llm
from .rules import classify_rules
from .schema import Classification, Evidence, Listing


def _label(conf: float) -> str:
    if conf >= config.FLAG_THRESHOLD:
        return "discriminatory"
    if conf >= config.REVIEW_THRESHOLD:
        return "needs_review"
    return "clean"


def classify(listing: Listing, use_llm: bool = True) -> Classification:
    r = classify_rules(listing.text, listing.rent, listing.bedrooms)
    signals = {"rules": r.score, "suppressed_by": r.suppressed_by}
    conf, category, reasons, evidence = r.score, r.category, list(r.reasons), list(r.evidence)
    language, translation = r.language, None

    confident_rule = r.score >= 0.9 and not r.suppressed_by
    needs_llm = listing.image_b64 is not None or not confident_rule
    if use_llm and needs_llm and llm.available():
        out = llm.classify_llm(listing)
        if out is not None:
            haystack = listing.text + "\n" + (out.get("image_text") or "")
            grounded = llm.grounded_fraction(out["evidence_quotes"], haystack)
            p = max(0.0, min(1.0, float(out["probability_unlawful"])))
            signals.update(llm=round(p, 3), llm_grounded=round(grounded, 2))

            if r.score < 0.3:
                # LLM is the only witness. Trust it only as far as its evidence is real.
                conf = p if grounded >= 0.5 else min(p, config.FLAG_THRESHOLD - 0.01)
            else:
                conf = 0.45 * r.score + 0.55 * p
            if out["is_discriminatory"] and out["category"] != "none":
                category = out["category"] if r.category == "none" else category
            reasons.insert(0, out["explanation"])
            for q in out["evidence_quotes"]:
                i = listing.text.lower().find(q.lower())
                if not any(e.quote.lower() == q.lower() for e in evidence):
                    evidence.append(Evidence(quote=q, start=i, end=i + len(q) if i >= 0 else -1, rule_id="llm"))
            language = out.get("language") or language
            translation = out.get("translation_en") or None
            if out.get("image_text"):
                signals["image_text"] = out["image_text"]

    conf = round(conf, 3)
    label = _label(conf)
    if label == "clean":
        # Keep only the "why we let it through" notes; hit explanations would mislead.
        reasons = [r for r in reasons if r.startswith(("Discounted", "Income band"))]
    return Classification(
        listing_id=listing.id,
        label=label,
        confidence=conf,
        category=category if label != "clean" else "none",
        reasons=reasons,
        evidence=evidence,
        language=language,
        translation_en=translation,
        income_analysis=r.income,
        legal_basis=config.LEGAL_BASIS if label != "clean" else None,
        signals=signals,
    )


def classify_many(listings: Iterable[Listing], use_llm: bool = True) -> List[Classification]:
    return [classify(l, use_llm=use_llm) for l in listings]
