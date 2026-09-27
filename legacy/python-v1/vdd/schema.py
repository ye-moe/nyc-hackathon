"""Shared data contract between Person 1 (pipeline), Person 2 (models), Person 3 (UI)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List, Optional


@dataclass
class Listing:
    """One row of Person 1's listings table."""
    id: str
    text: str
    source: str = "unknown"            # streeteasy | craigslist | facebook
    url: Optional[str] = None
    rent: Optional[float] = None        # monthly, USD
    bedrooms: Optional[int] = None
    address: Optional[str] = None
    bbl: Optional[str] = None           # borough-block-lot, joins to buildings
    image_b64: Optional[str] = None     # screenshot/flyer; sent to the vision model
    image_media_type: str = "image/png"

    @classmethod
    def from_dict(cls, d: dict) -> "Listing":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


@dataclass
class Evidence:
    quote: str
    start: int = -1                     # char offsets into Listing.text, -1 if not located
    end: int = -1
    rule_id: Optional[str] = None


@dataclass
class Classification:
    listing_id: str
    label: str                          # discriminatory | needs_review | clean
    confidence: float                   # 0..1 probability the listing is unlawful
    category: str                       # see rules.CATEGORIES
    reasons: List[str] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    language: str = "en"
    translation_en: Optional[str] = None
    income_analysis: Optional[dict] = None
    legal_basis: Optional[str] = None
    signals: dict = field(default_factory=dict)   # per-layer scores, for debugging/UI

    def to_dict(self) -> dict:
        return asdict(self)
