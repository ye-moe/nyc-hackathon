"""Address -> (lat, lng) with NYC Planning's GeoSearch (free, no key, NYC addresses).
Results are cached in data/geo_cache.json so each address is looked up once.
Google Maps only draws the maps in the browser; it isn't used for geocoding.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Optional

import httpx

CACHE = Path(__file__).resolve().parent.parent / "data" / "geo_cache.json"
API = "https://geosearch.planninglabs.nyc/v2/search"
_lock = threading.Lock()
_cache: Optional[dict] = None


def _load() -> dict:
    global _cache
    if _cache is None:
        _cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    return _cache


def _save() -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(_cache, indent=0, sort_keys=True))


def _clean(address: str) -> str:
    a = re.sub(r"\(.*?\)", "", address)            # "(btwn Walker & White)" confuses geocoders
    a = re.sub(r"\s*,\s*", ", ", a)
    return re.sub(r"\s+", " ", a).strip(" ,")


def geocode(address: Optional[str], borough: Optional[str] = None) -> Optional[dict]:
    """{'lat', 'lng', 'label', 'confidence'} or None. Never raises."""
    if not address or not re.search(r"\d", address):
        return None
    q = _clean(address)
    if borough and borough.lower() not in q.lower():
        q = f"{q}, {borough}"
    with _lock:
        c = _load()
        if q in c:
            return c[q]
    try:
        f = httpx.get(API, params={"text": q, "size": 1}, timeout=15).json()["features"]
    except (httpx.HTTPError, ValueError, KeyError):
        return None
    hit = None
    if f:
        lng, lat = f[0]["geometry"]["coordinates"]
        p = f[0]["properties"]
        # Low-confidence matches are often the wrong street, and a match in another borough is the wrong
        # place entirely; drop both rather than mis-pin a shelter.
        same_boro = not borough or (p.get("borough") or "").lower() == borough.lower()
        if p.get("confidence", 0) >= 0.6 and same_boro:
            hit = {"lat": round(lat, 6), "lng": round(lng, 6), "label": p.get("label"), "confidence": p.get("confidence"),
                   "borough": p.get("borough")}
    with _lock:
        _load()[q] = hit
        _save()
    return hit
