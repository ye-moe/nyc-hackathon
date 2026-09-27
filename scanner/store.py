"""The shared scraped-listings layer. Voucher Guard (flagged listings) and Open Doors
(voucher-friendly listings) both read from here, so every listing is checked once.

Scraper contract (what the scraper writes to scanner/python/listings.json, a JSON array):
    required: url, text
    optional: source ("craigslist", "streeteasy", ...), discovered_at (ISO time),
              address, borough, rent (monthly $), bedrooms (0 = studio),
              image_url, lat, lng
Anything the scraper leaves out is extracted from the text where possible.
"""
from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel

from config.phrases import WELCOME
from core import analyze
from core.geo import geocode
from core.schema import AnalysisResult

ROOT = Path(__file__).resolve().parent.parent
LISTING_FILES = [ROOT / "scanner" / "python" / "listings.json", ROOT / "scanner" / "data" / "listings.json",
                 ROOT / "scanner" / "data" / "cached_listings.json"]


class ScannedListing(BaseModel):
    id: str
    url: Optional[str] = None
    source: str = "scraper"
    discovered_at: Optional[str] = None
    text: str
    verdict: str
    welcomes_vouchers: bool
    within_voucher_limit: Optional[bool] = None
    rent: Optional[float] = None
    bedrooms: Optional[int] = None
    address: Optional[str] = None
    borough: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    flags: List[dict] = []           # non-info flags: rule, clause, explanation
    result: AnalysisResult           # full analysis, for packets and complaint drafts


_cache: dict = {}


def listing_files() -> List[Path]:
    return [f for f in LISTING_FILES if f.exists()]


def raw_listings() -> list:
    """First file found wins, so a real scrape replaces the sample data."""
    for f in LISTING_FILES:
        if f.exists():
            return json.loads(f.read_text())
    return []


def _scan_one(raw: dict, use_gemini: bool) -> ScannedListing:
    text = raw.get("text") or ""
    key = hashlib.sha1(((raw.get("url") or "") + text).encode()).hexdigest()[:12]
    r = analyze({"id": key, "text": text, "url": raw.get("url"),
                 "hints": {"monthly_rent": raw.get("rent"), "bedrooms": raw.get("bedrooms")}}, use_gemini=use_gemini)
    ex = r.extraction
    address = raw.get("address") or ex.address
    borough = raw.get("borough") or ex.borough
    lat, lng = raw.get("lat"), raw.get("lng")
    if lat is None and address:
        g = geocode(address, borough)
        if g:
            lat, lng = g["lat"], g["lng"]
    return ScannedListing(
        id=key, url=raw.get("url"), source=raw.get("source") or "scraper", discovered_at=raw.get("discovered_at"), text=text,
        verdict=r.verdict, welcomes_vouchers=any(re.search(p, text, re.I) for p in WELCOME),
        within_voucher_limit=r.within_voucher_range, rent=ex.monthly_rent,
        bedrooms=int(ex.bedrooms) if ex.bedrooms is not None else None, address=address, borough=borough, lat=lat, lng=lng,
        flags=[{"rule": f.rule_id, "clause": f.evidence_text, "explanation": f.explanation, "severity": f.severity}
               for f in r.flags if f.severity != "info"],
        result=r)


# def scan_all(use_gemini: bool = False) -> List[ScannedListing]:
#     """Check every scraped listing (cached by url+text, so re-scans only process new listings)."""
#     raws = raw_listings()
#     todo = []
#     for raw in raws:
#         k = (raw.get("url") or "") + (raw.get("text") or "")
#         if k not in _cache:
#             todo.append((k, raw))
#     with ThreadPoolExecutor(max_workers=4) as pool:
#         for (k, _), s in zip(todo, pool.map(lambda kr: _scan_one(kr[1], use_gemini), todo)):
#             _cache[k] = s
#     return [_cache[(r.get("url") or "") + (r.get("text") or "")] for r in raws]


def scan_all(use_gemini: bool = False) -> List[ScannedListing]:
    """Read MongoDB when configured; otherwise use local JSON."""

    if __import__("os").environ.get("MONGODB_URI"):
        from scanner.mongo_store import mongo_scan_all
        return mongo_scan_all()

    # Keep the existing JSON implementation below.
    raws = raw_listings()
    todo = []

    for raw in raws:
        k = (raw.get("url") or "") + (raw.get("text") or "")
        if k not in _cache:
            todo.append((k, raw))

    with ThreadPoolExecutor(max_workers=4) as pool:
        for (k, _), s in zip(
            todo,
            pool.map(lambda kr: _scan_one(kr[1], use_gemini), todo)
        ):
            _cache[k] = s

    return [
        _cache[(r.get("url") or "") + (r.get("text") or "")]
        for r in raws
    ]



# def get(listing_id: str) -> Optional[ScannedListing]:
#     return next((s for s in scan_all() if s.id == listing_id), None)


def get(listing_id: str) -> Optional[ScannedListing]:
    return next(
        (s for s in scan_all() if s.id == listing_id),
        None
    )
