"""Voucher Discrimination Detector engine.

    from core import analyze, build_packet, draft_complaint
"""
import os
from pathlib import Path


def _load_dotenv() -> None:
    # Minimal .env reader so teammates don't need python-dotenv. Real env vars win.
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if v.strip():
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

from core.analyze import analyze  # noqa: E402
from core.complaint import approve_draft, draft_complaint  # noqa: E402
from core.gemini import GEMINI_MODEL, gemini_available  # noqa: E402
from core.packet import SUPPORTED_LANGUAGES, build_packet  # noqa: E402
from core.schema import AnalysisResult, Extraction, Flag, ListingInput  # noqa: E402

__all__ = ["analyze", "build_packet", "draft_complaint", "approve_draft", "gemini_available", "GEMINI_MODEL",
           "SUPPORTED_LANGUAGES", "AnalysisResult", "Extraction", "Flag", "ListingInput"]
