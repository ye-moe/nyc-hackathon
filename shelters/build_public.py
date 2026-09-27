"""Merge hand-checked seed shelters + research files into data/shelters/public_shelters.json.

    python -m shelters.build_public

Only shelters with a published street address and a source URL are kept.
Domestic violence shelters are dropped even if one slipped through (their locations are confidential).
Each shelter is cross-checked against the city's DHS directory (NYC Open Data) by name.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from shelters.access_points import SEED_SHELTERS

ROOT = Path(__file__).resolve().parent.parent / "data" / "shelters"
OUT = ROOT / "public_shelters.json"
HOUSEHOLDS = {"single", "adult_family", "family_with_children", "youth_alone"}
DV = re.compile(r"domestic violence|\bDV\b|battered|abuse survivors", re.I)


def source_date(url: str):
    """City Record notice IDs start with the publication date: RequestDetail/20210326007 -> 2021-03-26."""
    m = re.search(r"RequestDetail/(\d{4})(\d{2})(\d{2})", url)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def norm_addr(a: str) -> str:
    a = re.sub(r"\(.*?\)", "", a.lower()).replace(".", "")
    for full, short in (("street", "st"), ("avenue", "ave"), ("west", "w"), ("east", "e"), ("north", "n"),
                        ("south", "s"), ("boulevard", "blvd"), ("place", "pl"), ("road", "rd")):
        a = re.sub(rf"\b{full}\b", short, a)
    return re.sub(r"[^a-z0-9]", "", a.split(",")[0])


def main():
    directory = json.loads((ROOT / "directory.json").read_text())
    by_name = {s["name"].lower(): s for s in directory["shelters"]}
    rows, problems = [], []
    for f in [None, *sorted((ROOT / "research").glob("*.json"))]:
        items = SEED_SHELTERS if f is None else json.loads(f.read_text())
        for r in items:
            where = "seed" if f is None else f.name
            if not r.get("address") or not re.search(r"\d", r["address"]) or not r.get("source_url"):
                problems.append(f"{where}: {r.get('name')}: no street address or source, dropped"); continue
            if DV.search(" ".join(str(r.get(k, "")) for k in ("name", "facility_type", "populations", "access"))):
                problems.append(f"{where}: {r.get('name')}: domestic violence shelter, dropped (confidential)"); continue
            hh = [h for h in r.get("household") or [] if h in HOUSEHOLDS]
            if not hh:
                problems.append(f"{where}: {r.get('name')}: no household type, dropped"); continue
            d = by_name.get((r.get("dhs_directory_name") or "").lower())
            rows.append({
                "name": r["name"], "provider": r.get("provider"), "address": r["address"], "borough": r.get("borough"),
                "phone": r.get("phone"), "facility_type": r.get("facility_type") or (d or {}).get("facility_type"),
                "household": hh, "gender": [g for g in r.get("gender") or [] if g in ("man", "woman")] or ["man", "woman"],
                "gender_stated": bool([g for g in r.get("gender") or [] if g in ("man", "woman")]),
                "min_age": r.get("min_age"), "max_age": r.get("max_age"), "populations": sorted(set(r.get("populations") or [])),
                "access": r.get("access") or "DHS intake assignment",
                "beds": (d or {}).get("capacity"), "in_city_directory": bool(d),
                "source_url": r["source_url"], "source_type": r.get("source_type"), "quote": r.get("quote"),
                "source_date": source_date(r["source_url"]), "caveats": r.get("notes"),
            })
    # De-duplicate by street address (the seed wins, it was checked by hand).
    seen, out = set(), []
    for r in rows:
        k = norm_addr(r["address"])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    # Coordinates for the map (NYC GeoSearch, cached). Unmatched addresses stay off the map, not mis-pinned.
    from concurrent.futures import ThreadPoolExecutor
    from core.geo import geocode
    with ThreadPoolExecutor(max_workers=6) as pool:
        geos = list(pool.map(lambda r: geocode(r["address"], r.get("borough")), out))
    for i, (r, g) in enumerate(zip(out, geos)):
        r["id"] = f"shelter-{i:03d}"
        r["lat"], r["lng"] = (g["lat"], g["lng"]) if g else (None, None)
        if not g:
            problems.append(f"{r['name']}: address not geocoded, list only (not on map)")
    OUT.write_text(json.dumps({"built_on": date.today().isoformat(), "shelters": out}, indent=1, ensure_ascii=False))
    print(f"{len(out)} shelters with public addresses -> {OUT}")
    for p in problems:
        print("  !", p)


if __name__ == "__main__":
    main()
