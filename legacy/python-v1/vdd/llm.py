"""Layer 2: Claude. Handles what regex can't: paraphrase, sarcasm, other
languages, and image-only listings (flyers, screenshots with a crossed-out
"PROGRAMS"). Only called when rules are unsure, which keeps cost low.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from . import config
from .rules import CATEGORIES
from .schema import Listing

MODEL = os.environ.get("VDD_MODEL", "claude-opus-5")

SYSTEM = f"""You review NYC rental listings for source-of-income discrimination against \
housing voucher holders (CityFHEPS, Section 8/HCV, HASA, other rental assistance).

Law: {config.LEGAL_BASIS}

Unlawful examples: "no programs", "no vouchers", "Section 8 only" (excludes CityFHEPS), \
"must earn 40x rent" applied to everyone with no carve-out for the subsidized portion, \
"working professionals only", "income must come from employment", "no third-party payments", \
"no shelter referrals", refusals in any language, images marking programs as refused.

Lawful examples: "no pets", "no broker fee", "no smoking", "vouchers welcome", \
income requirements that explicitly apply only to the tenant's share, government-set \
income bands for affordable-housing lotteries (Housing Connect, AMI %), \
guarantor/insurance options offered as alternatives, generic "must pass background check".

Precision matters more than recall: a false complaint harms a lawful landlord and the \
credibility of the tool. If the listing is ambiguous, say so with a middling confidence.

evidence_quotes must be copied verbatim from the listing text (or transcribed exactly \
from the image). Give translation_en only if the listing is not in English."""

SCHEMA = {
    "type": "object",
    "properties": {
        "is_discriminatory": {"type": "boolean"},
        "probability_unlawful": {"type": "number", "description": "0-1; near 0 when clearly lawful, near 1 when clearly unlawful"},
        "category": {"type": "string", "enum": CATEGORIES},
        "evidence_quotes": {"type": "array", "items": {"type": "string"}},
        "explanation": {"type": "string", "description": "One or two sentences a caseworker can read."},
        "language": {"type": "string", "description": "ISO 639-1 code of the listing"},
        "translation_en": {"type": "string"},
        "image_text": {"type": "string", "description": "Text transcribed from the image, empty if none"},
    },
    "required": ["is_discriminatory", "probability_unlawful", "category", "evidence_quotes",
                 "explanation", "language", "translation_en", "image_text"],
    "additionalProperties": False,
}

_client = None


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()
    return _client


def classify_llm(listing: Listing) -> Optional[dict]:
    """Returns the parsed schema dict, or None if the call fails or is refused."""
    import anthropic

    content = []
    if listing.image_b64:
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": listing.image_media_type, "data": listing.image_b64}})
    meta = f"Source: {listing.source}. Rent: {listing.rent or 'unknown'}. Bedrooms: {listing.bedrooms if listing.bedrooms is not None else 'unknown'}."
    content.append({"type": "text", "text": f"{meta}\n\n<listing>\n{listing.text}\n</listing>"})

    try:
        resp = _get_client().messages.create(
            model=MODEL,
            max_tokens=2048,
            system=SYSTEM,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            # Server-side fallback: if a safety classifier declines, the API
            # retries on Anthropic's recommended fallback model in the same call.
            extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
            extra_body={"fallbacks": "default"},
        )
    except anthropic.RateLimitError:
        return None
    except anthropic.APIStatusError as e:
        print(f"[llm] API error {e.status_code} on {listing.id}: {e.message}")
        return None
    except anthropic.APIConnectionError:
        return None

    if resp.stop_reason == "refusal":
        return None
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if not text:
        return None
    return json.loads(text)


def grounded_fraction(quotes, haystack: str) -> float:
    """Share of quotes that actually appear in the listing. Guards against the
    model inventing a damning phrase that isn't there."""
    if not quotes:
        return 0.0
    h = " ".join(haystack.lower().split())
    hits = sum(1 for q in quotes if q and " ".join(q.lower().split()) in h)
    return hits / len(quotes)
