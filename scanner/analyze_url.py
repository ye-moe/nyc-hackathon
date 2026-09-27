"""URL -> verdict in one call ("here's a link, is this legal?")."""
from __future__ import annotations

from typing import Optional, Tuple

from core import analyze
from core.schema import AnalysisResult
from scanner.fetch_listing import fetch_listing


def analyze_url(url: str, hints: Optional[dict] = None) -> Tuple[AnalysisResult, dict]:
    fetched = fetch_listing(url)
    image = ({"base64": fetched["screenshot_b64"], "mime_type": fetched.get("screenshot_media_type") or "image/jpeg"}
             if fetched.get("screenshot_b64") else None)
    # The screenshot lets Gemini read listing text that lives inside images (flyers, photo captions).
    result = analyze({"text": fetched["text"], "url": fetched["url"], "image": image,
                      "hints": {k: v for k, v in (hints or {}).items() if v is not None}})
    if fetched["via"] == "jev":
        stopped = fetched.get("stopped") or ""
        result.notes.append(f"Page read by jev browser agent in {fetched.get('elapsed_ms')} ms ({len(fetched.get('steps') or [])} actions"
                            f"{'; stopped by ' + stopped if stopped.startswith('guardrail') else ''}).")
    else:
        result.notes.append("Page read with a plain HTTP fetch"
                            + (f" (jev unavailable: {fetched['jev_error']})" if fetched.get("jev_error") else "")
                            + ". Content loaded by JavaScript may be missing.")
    return result, fetched
