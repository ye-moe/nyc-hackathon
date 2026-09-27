"""Build data/shelters/directory.json from official NYC Open Data. Re-run to refresh.

    python -m shelters.build_directory

Source (NYC Open Data, published by the city):
  dvaj-b7yx  Shelter Repair Scorecard (DOB/DHS): every DHS shelter building with
             name, provider, facility type, borough, capacity. No street
             addresses: the city doesn't publish shelter addresses for residents' safety.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import httpx

OUT = Path(__file__).resolve().parent.parent / "data" / "shelters" / "directory.json"
API = "https://data.cityofnewyork.us/resource/{}.json"

FACILITY_TYPES = ["Adult Family Commercial Hotel", "Adult Family Shelter", "Adult Commercial Hotel", "Family Commercial Hotel",
                  "Family Late Arrival", "Family Shelter", "Adult Shelter", "Safe Haven", "COVID-19"]

# Who a facility type serves (DHS categories).
TYPE_POPULATION = {
    "Family Shelter": "families_with_children", "Family Commercial Hotel": "families_with_children",
    "Family Late Arrival": "families_with_children",
    "Adult Family Shelter": "adult_families", "Adult Family Commercial Hotel": "adult_families",
    "Adult Shelter": "single_adults", "Adult Commercial Hotel": "single_adults",
    "Safe Haven": "single_adults_street_homeless", "COVID-19": "single_adults",
}

# Tags read from the shelter's own name. Marked "inferred" in the output.
NAME_TAGS = [
    ("women", r"\bwom[ae]n'?s?\b|\bladies\b|\bfemale"),
    ("men", r"(?<!wo)\bmen'?s?\b|\bmale\b"),
    ("mental_health", r"\bmica\b|mental|\bmh\b|psychiatric"),
    ("substance_use", r"\bmica\b|chemical|recovery|substance|detox"),
    ("veterans", r"veteran"),
    ("seniors", r"senior|elder|\b(50|55|60|62)\s*\+|older adult"),
    ("employment", r"employment|\bwork\b|working"),
    ("assessment", r"assessment|intake"),
    ("young_adults", r"youth|young adult"),
    ("lgbtq", r"lgbt|pride|transgender"),
    ("hiv", r"\bhiv\b|\baids\b|hasa"),
]


def get(dataset: str, **params) -> list:
    r = httpx.get(API.format(dataset), params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def parse_shelter(raw: str):
    """'Bld ID: 1005 -- Park Slope Women's Shelter, CAMBA, Adult Shelter -- Brooklyn' (several joined by ' // ')."""
    out = []
    for part in raw.split(" // "):
        part = re.sub(r"^Bld ID:\s*\d+\s*--\s*", "", part.strip())
        part = re.sub(r"\s*--\s*(Manhattan|Brooklyn|Bronx|Queens|Staten Island)\s*$", "", part)
        ftype = next((t for t in FACILITY_TYPES if part.endswith(", " + t)), None)
        if ftype:
            part = part[: -len(", " + ftype)]
        name, _, provider = part.partition(", ")
        out.append({"name": name.strip(), "provider": provider.strip() or None, "facility_type": ftype})
    return out


def tags_for(name: str) -> list:
    return sorted({tag for tag, pat in NAME_TAGS if re.search(pat, name, re.I)})


def main():
    latest = get("dvaj-b7yx", **{"$select": "max(month) as m"})[0]["m"]
    rows = get("dvaj-b7yx", **{"$where": f"month='{latest}'", "$limit": 5000,
                               "$select": "dhs_bld_id,shelter_name_all,facility_type,borough,capacity"})
    shelters = []
    for r in rows:
        for i, s in enumerate(parse_shelter(r["shelter_name_all"])):
            ftype = s["facility_type"] or r["facility_type"]
            shelters.append({
                "id": f"dhs-{r['dhs_bld_id']}" + (f"-{i}" if i else ""),
                "name": s["name"], "provider": s["provider"], "facility_type": ftype,
                "serves": TYPE_POPULATION.get(ftype, "single_adults"),
                "tags_from_name": tags_for(s["name"]),
                "borough": r["borough"],
                "capacity": int(r["capacity"]) if r.get("capacity", "").isdigit() else None,
                "address": None,   # not published by the city
                "access": "Assigned through DHS intake. You can't walk in.",
            })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "built_on": date.today().isoformat(),
        "sources": {
            "shelters": {"dataset": "https://data.cityofnewyork.us/d/dvaj-b7yx", "as_of": latest[:10],
                         "note": "Shelter Repair Scorecard, latest month published. Shelters may have opened or closed since."},
        },
        "shelters": shelters,
    }, indent=1, ensure_ascii=False))
    print(f"{len(shelters)} shelters (as of {latest[:10]}) -> {OUT}")


if __name__ == "__main__":
    main()
