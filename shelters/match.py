"""Narrow NYC homeless shelters (with public addresses) down to the ones a person is eligible for.

    from shelters.match import match, Profile
    match(Profile(household="single", age=34, gender="woman", borough="Brooklyn"))

Nothing here is stored: the profile is used for one match and discarded.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from urllib.parse import quote
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from shelters.access_points import DHS_PAGES, INTAKE, WHAT_TO_BRING

DATA = Path(__file__).resolve().parent.parent / "data" / "shelters" / "public_shelters.json"

Household = Literal["single", "adult_family", "family_with_children", "youth_alone"]
Gender = Literal["man", "woman", "nonbinary", "unspecified"]
Population = Literal["mental_health", "substance_use", "hiv", "medical"]
HH_LABEL = {"single": "single adults", "adult_family": "adult families", "family_with_children": "families with children",
            "youth_alone": "young people on their own"}


# Research notes that say a site may not be operating, or that its address is disputed.
DOUBT = re.compile(r"reopen|re-open|not (yet )?(open|operating)|clos(ed|ing)|projected|may not be|conflict|relocat|moved to|"
                   r"uncertain|\bdoubt\b|\bcaution\b|differs", re.I)


def doubt_note(text: Optional[str]) -> Optional[str]:
    """First sentence of a research note, only when it casts doubt on the site being open or where it is."""
    if not text:
        return None
    first = text.split(". ")[0].strip()
    return (first[:160].rstrip(".") + ".") if DOUBT.search(first) else None


class Profile(BaseModel):
    household: Household = Field(description="single adult; adults with no minor children; family with children under 18; or a young person on their own")
    age: Optional[int] = Field(None, ge=0, le=120)
    gender: Gender = "unspecified"
    fleeing_violence: bool = False
    veteran: bool = False
    lgbtq: bool = False
    employed: bool = False
    needs: List[Population] = Field(default_factory=list)
    in_dhs_shelter_last_12_months: bool = False
    borough: Optional[Literal["Manhattan", "Brooklyn", "Bronx", "Queens", "Staten Island"]] = None


class Shelter(BaseModel):
    id: str
    name: str
    provider: Optional[str] = None
    address: str
    borough: Optional[str] = None
    phone: Optional[str] = None
    facility_type: Optional[str] = None
    serves: str                     # plain-language who it's for
    populations: List[str] = []
    beds: Optional[int] = None
    access: str
    why: str                        # why it fits this person
    source_url: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    walk_in: bool = False           # takes people directly (walk in / call), not only via DHS assignment
    details: dict = {}              # dropdown: how to get in, eligibility, what to bring, links


class Excluded(BaseModel):
    name: str
    address: str
    reason: str


class MatchResult(BaseModel):
    how_to_get_in: str
    shelters: List[Shelter]
    total: int
    by_borough: dict
    not_eligible: List[Excluded]
    note: str


@lru_cache(maxsize=1)
def public_shelters() -> List[dict]:
    return json.loads(DATA.read_text())["shelters"] if DATA.exists() else []


def _household(p: Profile) -> str:
    if p.household == "single" and p.age is not None and p.age < 18:
        return "youth_alone"
    return p.household


def _serves(s: dict) -> str:
    who = " / ".join(HH_LABEL[h] for h in s["household"])
    g = s["gender"]
    if g == ["man"]:
        who = "men (" + who + ")"
    elif g == ["woman"]:
        who = "women (" + who + ")"
    elif "single" in s["household"] and not s.get("gender_stated", True):
        who += " (gender not stated in the source; confirm at intake)"
    ages = ""
    if s.get("min_age") and s.get("max_age"):
        ages = f", ages {s['min_age']}–{s['max_age']}"
    elif s.get("max_age"):
        ages = f", up to age {s['max_age']}"
    elif s.get("min_age") and s["min_age"] > 18:
        ages = f", ages {s['min_age']}+"
    return who.capitalize() + ages


def _ineligible(s: dict, p: Profile, hh: str) -> Optional[str]:
    if hh not in s["household"]:
        if hh == "youth_alone" and "single" in s["household"]:
            return "Adults 18+ only."
        return "For " + " / ".join(HH_LABEL[h] for h in s["household"]) + " only."
    # Nonbinary and unspecified people can use the shelter that matches their gender identity.
    if hh == "single" and p.gender in ("man", "woman") and p.gender not in s["gender"]:
        return "Women only." if p.gender == "man" else "Men only."
    if p.age is not None:
        if s.get("min_age") and p.age < s["min_age"]:
            return f"Ages {s['min_age']}+ only."
        if s.get("max_age") and p.age > s["max_age"]:
            return f"Up to age {s['max_age']} only."
    elif s.get("max_age") and hh != "youth_alone":
        return f"Up to age {s['max_age']} only (add your age to check)."
    if s.get("min_age") and s["min_age"] >= 50 and p.age is None:
        return f"Ages {s['min_age']}+ only (add your age to check)."
    # Population-specific shelters (e.g. veterans) are only for that group.
    pops = set(s["populations"])
    if "veterans" in pops and not p.veteran:
        return "For veterans."
    return None


def _walk_in(s: dict) -> bool:
    return bool(re.search(r"walk[\s-]*in|call for bed|call ahead|first come", s["access"], re.I))


def _details(s: dict, hh: str, how: str) -> dict:
    """Everything for the shelter's dropdown."""
    elig = [_serves(s) + "."]
    if s.get("min_age"):
        elig.append(f"Minimum age: {s['min_age']}.")
    if s.get("max_age"):
        elig.append(f"Maximum age: {s['max_age']}.")
    if s["populations"]:
        elig.append("Special focus: " + ", ".join(p.replace("_", " ") for p in s["populations"]) + ".")
    if s.get("in_city_directory"):
        elig.append("Listed in the city's DHS shelter directory" + (f" ({s['beds']} beds)." if s.get("beds") else "."))
    get_in = s["access"]
    if not _walk_in(s) and "intake" in get_in.lower():
        get_in += " " + how
    links = [{"label": "Source for this listing", "url": s["source_url"].split(" ")[0]}]
    if hh in DHS_PAGES and not _walk_in(s):
        label, url = DHS_PAGES[hh]
        links.append({"label": label, "url": url})
    links.append({"label": "Directions (Google Maps)", "url": "https://www.google.com/maps/search/?api=1&query=" + quote(s["address"])})
    return {
        "how_to_get_in": get_in,
        "eligibility": elig,
        "what_to_bring": WHAT_TO_BRING.get(hh, []),
        "links": links,
        "contact": {"address": s["address"], "phone": s.get("phone"), "provider": s.get("provider")},
        "source_quote": s.get("quote"),
        "source_date": s.get("source_date"),
        "caveats": s.get("caveats"),
        "confirm": ("Source dated " + s["source_date"] + ". Call ahead or check with 311 that it's still operating."
                    if s.get("source_date") and s["source_date"] < "2025-01-01" else None),
    }


def match(p: Profile) -> MatchResult:
    hh = _household(p)
    how = (INTAKE["dv"] + " ") if p.fleeing_violence else ""
    if hh == "youth_alone":
        how += INTAKE["youth"]
    elif p.in_dhs_shelter_last_12_months and hh in ("single", "adult_family"):
        how += INTAKE["returning"]
    elif hh == "single":
        how += INTAKE[{"man": "single_man", "woman": "single_woman"}.get(p.gender, "single_any")]
    else:
        how += INTAKE[hh]

    wanted = set(p.needs) | ({"veterans"} if p.veteran else set()) | ({"seniors"} if (p.age or 0) >= 50 else set()) | \
        ({"employment"} if p.employed else set()) | ({"lgbtq"} if p.lgbtq else set())

    fits, excluded = [], []
    for s in public_shelters():
        reason = _ineligible(s, p, hh)
        if reason:
            excluded.append(Excluded(name=s["name"], address=s["address"], reason=reason))
            continue
        hits = wanted & set(s["populations"])
        why = []
        if hits:
            why.append("Serves " + ", ".join(h.replace("_", " ") for h in sorted(hits)) + ".")
        if p.borough and s.get("borough") == p.borough:
            why.append(f"In {p.borough}.")
        if not why:
            why.append(f"Takes {_serves(s).lower()}.")
        # Confirmed for this person's gender beats "gender not stated" for single adults.
        confirmed = 1 if (hh != "single" or p.gender not in ("man", "woman") or s.get("gender_stated", True)) else 0
        # Sites whose research notes doubt they're open (or where they are) go below the rest.
        sure = 0 if doubt_note(s.get("caveats")) else 1
        fits.append((sure, len(hits), confirmed, 1 if p.borough and s.get("borough") == p.borough else 0, s, " ".join(why)))

    fits.sort(key=lambda t: (t[0], t[1], t[2], t[3], t[4].get("beds") or 0), reverse=True)
    shelters = [Shelter(id=s["id"], name=s["name"], provider=s.get("provider"), address=s["address"], borough=s.get("borough"),
                        phone=s.get("phone"), facility_type=s.get("facility_type"), serves=_serves(s), populations=s["populations"],
                        beds=s.get("beds"), access=s["access"], why=why, source_url=s["source_url"],
                        lat=s.get("lat"), lng=s.get("lng"), walk_in=_walk_in(s), details=_details(s, hh, how))
                for _, _, _, _, s, why in fits]
    by_boro: dict = {}
    for s in shelters:
        by_boro[s.borough] = by_boro.get(s.borough, 0) + 1
    note = ("Only shelters with a publicly published address are listed; each links to its source. City (DHS) shelters are "
            "assigned after intake, so you usually can't choose or walk in; the list shows which ones fit you. "
            "Domestic violence shelters are confidential and never listed.")
    return MatchResult(how_to_get_in=how, shelters=shelters, total=len(shelters), by_borough=by_boro,
                       not_eligible=excluded, note=note)
