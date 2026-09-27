"""The pipeline every caller uses: agent, scanner, web, eval.
    input -> extraction (Gemini, or offline regex fallback) -> rules -> result"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core.gemini import gemini_available, gemini_extract
from core.regex_extract import regex_extract
from core.rules import run_rules
from core.schema import AnalysisResult, Extraction, ListingInput


def analyze(listing: ListingInput | dict, use_gemini: bool = True) -> AnalysisResult:
    inp = listing if isinstance(listing, ListingInput) else ListingInput.model_validate(listing)
    use_gemini = use_gemini and gemini_available()
    notes = []
    text = inp.text or ""
    extractor = "regex"

    if use_gemini:
        try:
            g = gemini_extract(inp.text, inp.image)
            # Phrase lists run over everything we can read: typed text, text
            # read from the image, and the English translation.
            text = "\n".join(t for t in [inp.text, g.transcribed_text, g.english_text] if t)
            extraction = _merge(g, regex_extract(text))
            extractor = "gemini"
        except Exception as e:
            notes.append(f"Read with the offline checker ({_reason(e)}).")
            extraction = regex_extract(text)
    else:
        extraction = regex_extract(text)

    if inp.image and extractor != "gemini" and not inp.text:
        notes.append("Couldn't read the image. Try again, or paste the listing text.")
        extraction.confidence = 0

    h = inp.hints
    if h:
        if extraction.bedrooms is None:
            extraction.bedrooms = h.bedrooms
        if extraction.monthly_rent is None:
            extraction.monthly_rent = h.monthly_rent

    flags, verdict, within, rule_notes = run_rules(extraction, text)
    return AnalysisResult(
        id=inp.id or str(uuid.uuid4()),
        verdict="needs_review" if extraction.confidence == 0 else verdict,
        flags=flags,
        extraction=extraction,
        extractor=extractor,
        analyzed_text=text,
        within_voucher_range=within,
        notes=notes + rule_notes,
        analyzed_at=datetime.now(timezone.utc).isoformat(),
    )


def _reason(e: Exception) -> str:
    """Short, user-facing reason. Full error goes to the debug log (VDD_DEBUG=1)."""
    from core.gemini import _debug
    msg = str(e)
    _debug(f"extract failed: {msg[:300]}")
    if "quota" in msg.lower() or "RESOURCE_EXHAUSTED" in msg:
        return "Gemini quota used up"
    if "timed out" in msg.lower():
        return "Gemini timed out"
    if "503" in msg or "UNAVAILABLE" in msg:
        return "Gemini busy"
    return "Gemini error"


def _merge(g: Extraction, r: Extraction) -> Extraction:
    """Gemini wins on everything it found; regex fills gaps (e.g. a rent that's only in the title)."""
    data = r.model_dump()
    data.update({k: v for k, v in g.model_dump().items() if v is not None})
    data["explicit_exclusions"] = g.model_dump()["explicit_exclusions"]
    return Extraction.model_validate(data)
