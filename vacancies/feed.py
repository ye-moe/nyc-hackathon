"""Affordable vacancies: open Housing Connect lotteries + voucher-friendly listings, in one feed.

    from vacancies.feed import build_feed
    build_feed(borough="Brooklyn", bedrooms=2)

Lotteries come from NYC Open Data (HPD "Advertised Lotteries on Housing Connect"), live with a
local cache. Listings come from the scraper's output files (scanner/...), run through the
discrimination checker in core/: only listings with no issue found are kept.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional

import httpx
from pydantic import BaseModel

from config import cityfheps as C
from config.phrases import WELCOME
from core import analyze

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "vacancies" / "lotteries.json"
LOTTERIES_API = "https://data.cityofnewyork.us/resource/vy5i-a666.json"
BUILDINGS_API = "https://data.cityofnewyork.us/resource/nibs-na6y.json"
BORO = {"MN": "Manhattan", "BK": "Brooklyn", "BX": "Bronx", "QN": "Queens", "SI": "Staten Island"}
SIZES = [("unit_distribution_studio", 0), ("unit_distribution_1bed", 1), ("unit_distribution_2bed", 2),
         ("unit_distribution_3bed", 3), ("unit_distribution_4bed", 4)]
TIERS = [("applied_income_ami_extremely_low", "extremely low"), ("applied_income_ami_very_low", "very low"),
         ("applied_income_ami_low", "low"), ("applied_income_ami_moderate", "moderate"), ("applied_income_ami_middle", "middle")]
PREFS = [("lottery_mobility_percent", "mobility disability"), ("lottery_vision_hearing_percent", "vision/hearing disability"),
         ("lottery_community_board_percent", "community board residents"), ("lottery_municipal_employee_percent", "city employees"),
         ("lottery_nycha_percent", "NYCHA residents"), ("lottery_senior_percent", "seniors")]


class FeedItem(BaseModel):
    id: str
    # kind: Literal["lottery", "listing"]
    title: str
    borough: Optional[str] = None
    address: Optional[str] = None
    zip: Optional[str] = None
    bedrooms: List[int] = []            # sizes available
    rent: Optional[float] = None        # listings only
    units: Optional[int] = None         # lotteries only
    income_tiers: List[str] = []        # lotteries: which income bands have units
    set_asides: List[str] = []          # lotteries: preference percentages
    deadline: Optional[str] = None      # lotteries: application end date
    days_left: Optional[int] = None
    neighborhood: Optional[str] = None
    unit_offers: List[dict] = []        # lotteries: rent, household size, income limits per unit type
    paper_application_address: Optional[str] = None
    voucher_status: str                 # why this is here for a voucher holder
    within_voucher_limit: Optional[bool] = None
    url: Optional[str] = None
    source: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    buildings: List[dict] = []          # lotteries with several buildings: one map pin each
    kind: Literal["lottery", "listing", "inventory"]
    snapshot_month: Optional[str] = None
    availability_verified: Optional[bool] = None


class Feed(BaseModel):
    items: List[FeedItem]
    counts: dict
    hidden: dict                        # listings removed and why
    notes: List[str]
    lotteries_as_of: Optional[str] = None


# ---------------- lotteries ----------------
# Housing Connect's own public API (what housingconnect.nyc.gov shows): the live list of open lotteries
# with unit-level rent, household size, and income limits. NYC Open Data (HPD) is the fallback; it
# lags by weeks, so it can list lotteries that already closed.
HC_API = "https://a806-housingconnectapi.nyc.gov/HPDPublicAPI/api/Lottery/"
HC_SEARCH = {"UnitTypes": [], "NearbyPlaces": [], "NearbySubways": [], "Amenities": [], "Applied": None, "HPDUserId": None,
             "Boroughs": [], "Neighborhoods": [], "HouseholdSize": None, "Income": "", "HouseholdType": 1, "OwnerTypes": [],
             "PreferanceTypes": [], "LotteryTypes": [], "Min": None, "Max": None, "RentalSubsidy": None}
VOUCHER_INCOME_NOTE = ("Housing Connect: \"Minimum income listed may not apply to applicants with Section 8 or other "
                       "qualifying rental subsidies. Asset limits also apply.\"")
LAYOUT_BEDS = {"studio": 0, "1 bedroom": 1, "2 bedroom": 2, "3 bedroom": 3, "4 bedroom": 4}
MAX_CACHE_AGE_H = 6


def refresh_lotteries() -> int:
    """Live open lotteries from Housing Connect (details per lottery), falling back to NYC Open Data."""
    h = {"User-Agent": "Mozilla/5.0 (voucher-detector; read-only)", "Content-Type": "application/json"}
    try:
        found = httpx.post(HC_API + "SearchLotteries", json=HC_SEARCH, headers=h, timeout=30).json().get("rentals") or []
        details = []
        for f in found:
            d = httpx.get(HC_API + "GetLotteryAdvertisement", params={"lotteryId": f["lotteryId"]}, headers=h, timeout=30).json()
            details.append({"summary": f, "ad": d})
        data = {"source": "housing_connect", "lotteries": details}
    except (httpx.HTTPError, ValueError):
        lots = httpx.get(LOTTERIES_API, params={"lottery_status": "Active", "$limit": 500}, timeout=30).json()
        ids = ",".join(f"'{l['lottery_id']}'" for l in lots) or "''"
        blds = httpx.get(BUILDINGS_API, params={"$where": f"lottery_id in ({ids})", "$limit": 5000}, timeout=30).json()
        data = {"source": "open_data", "lotteries": lots, "buildings": blds}
    data["fetched_at"] = datetime.now(timezone.utc).isoformat()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(data, indent=1))
    return len(data["lotteries"])


def _lottery_data() -> dict:
    stale = True
    if CACHE.exists():
        age = datetime.now(timezone.utc) - datetime.fromisoformat(json.loads(CACHE.read_text())["fetched_at"])
        stale = age.total_seconds() > MAX_CACHE_AGE_H * 3600
    if stale:
        try:
            refresh_lotteries()
        except httpx.HTTPError:
            pass
    return json.loads(CACHE.read_text()) if CACHE.exists() else {"lotteries": []}


def _num(x) -> int:
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return 0


def _hc_item(summary: dict, ad: dict) -> Optional[FeedItem]:
    end = (ad.get("endDate") or "")[:10]
    if end and end < date.today().isoformat():
        return None
    blds = ad.get("lotteryBuildings") or []
    units, beds = [], set()
    for u in ad.get("units") or []:
        b = LAYOUT_BEDS.get((u.get("unitLayoutTypeName") or "").strip().lower())
        if b is not None:
            beds.add(b)
        units.append({
            "bedrooms": b, "layout": (u.get("unitLayoutTypeName") or "").strip(), "rent": u.get("actualRent"),
            "household_min": u.get("minimumHouseholdSize"), "household_max": u.get("maximumHouseholdSize"),
            "ami_percent": u.get("unitRegulatoryMechanismAmi"),
            "income_by_household_size": {str(i["houseHoldSize"]): [i.get("minimumIncome"), i.get("maximumIncome")]
                                         for i in u.get("unitIncome") or []},
            # Housing Connect leaves rent at 0 for some set-aside units whose rent depends on income.
            "rent_set_by_income": not u.get("actualRent"),
            "rent_within_voucher_limit": (u.get("actualRent") <= C.PAYMENT_STANDARD[min(b, 4)] * C.PAYMENT_STANDARD_SLACK)
                                         if (b is not None and u.get("actualRent")) else None,
        })
    # Collapse identical unit types (a 20-unit lottery often has 3 distinct offers).
    seen, distinct = set(), []
    for u in units:
        k = (u["layout"], u["rent"], u["household_min"], u["household_max"])
        if k not in seen:
            seen.add(k)
            distinct.append({**u, "count": sum(1 for v in units if (v["layout"], v["rent"], v["household_min"], v["household_max"]) == k)})
    paper = [t for task in ad.get("lotteryTasks") or [] for t in task.get("paperApplicationDelivery") or []]
    covered = [u for u in distinct if u["rent_within_voucher_limit"]]
    return FeedItem(
        id=f"lottery-{summary['lotteryId']}", kind="lottery", title=(ad.get("lotteryName") or summary.get("lotteryName") or "").strip(),
        borough=(summary.get("borough") or "").strip() or None,
        address=", ".join(filter(None, [blds[0].get("address"), blds[0].get("zip")])) if len(blds) == 1 else (f"{len(blds)} buildings" if blds else None),
        zip=blds[0].get("zip") if blds else None, bedrooms=sorted(beds), units=summary.get("units") or len(units),
        deadline=end or None, days_left=summary.get("endIn"), unit_offers=distinct,
        paper_application_address=(", ".join(filter(None, [paper[0].get("address"), paper[0].get("zip")])) if paper else None),
        neighborhood=summary.get("neighborhood"),
        voucher_status=(f"{len(covered)} of {len(distinct)} unit types have rent within the CityFHEPS limit. " if distinct else "")
                       + VOUCHER_INCOME_NOTE,
        within_voucher_limit=bool(covered) if distinct else None,
        url=f"https://housingconnect.nyc.gov/PublicWeb/details/{summary['lotteryId']}", source="NYC Housing Connect (live)",
        lat=float(blds[0]["latitude"]) if blds and blds[0].get("latitude") else None,
        lon=float(blds[0]["longitude"]) if blds and blds[0].get("longitude") else None,
        buildings=[{"address": b.get("address"), "zip": b.get("zip"), "lat": float(b["latitude"]), "lng": float(b["longitude"])}
                   for b in blds if b.get("latitude") and b.get("longitude")])


def _open_data_item(l: dict, addrs: dict) -> Optional[FeedItem]:
    end = (l.get("lottery_end_date") or "")[:10]
    if l.get("lottery_status") != "Active" or (end and end < date.today().isoformat()):
        return None
    a = addrs.get(l["lottery_id"], [])
    return FeedItem(
        id=f"lottery-{l['lottery_id']}", kind="lottery", title=l.get("lottery_name") or f"Lottery {l['lottery_id']}",
        borough=BORO.get(l.get("borough"), l.get("borough")), address=a[0] if len(a) == 1 else (f"{len(a)} buildings" if a else None),
        zip=l.get("postcode"), bedrooms=[n for k, n in SIZES if _num(l.get(k))], units=_num(l.get("unit_count")) or None,
        income_tiers=[t for k, t in TIERS if _num(l.get(k))], set_asides=[f"{_num(l.get(k))}% {t}" for k, t in PREFS if _num(l.get(k))],
        deadline=end or None, voucher_status=VOUCHER_INCOME_NOTE,
        url=f"https://housingconnect.nyc.gov/PublicWeb/details/{l['lottery_id']}", source="NYC Open Data vy5i-a666 (HPD; may lag)",
        lat=float(l["latitude"]) if l.get("latitude") else None, lon=float(l["longitude"]) if l.get("longitude") else None)


def lottery_items() -> List[FeedItem]:
    data = _lottery_data()
    if data.get("source") == "housing_connect":
        items = [_hc_item(x["summary"], x["ad"]) for x in data["lotteries"]]
    else:
        addrs: dict = {}
        for b in data.get("buildings", []):
            a = " ".join(x for x in [b.get("house_number"), b.get("street_name")] if x)
            if a:
                addrs.setdefault(b["lottery_id"], []).append(f"{a}, {BORO.get(b.get('borough'), b.get('borough', ''))} {b.get('address_zipcode', '')}".strip())
        items = [_open_data_item(l, addrs) for l in data.get("lotteries", [])]
    return [i for i in items if i]


# ---------------- listings ----------------
def listing_items(use_gemini: bool = False):
    """Voucher-friendly listings from the shared scan (scanner/store.py). Returns (items, hidden counts)."""
    from scanner.store import scan_all
    items, hidden = [], {"discriminatory": 0, "needs_review": 0}
    for s in scan_all(use_gemini):
        if s.verdict == "violation":
            hidden["discriminatory"] += 1
            continue
        if s.verdict == "needs_review":
            hidden["needs_review"] += 1
            continue
        if s.welcomes_vouchers:
            status = "Says it welcomes vouchers or programs."
        elif s.within_voucher_limit:
            status = "Rent is within the CityFHEPS limit for its size, and no discriminatory terms were found."
        else:
            status = "No discriminatory terms found." + (" Rent may be above the CityFHEPS limit." if s.within_voucher_limit is False else "")
        items.append(FeedItem(
            id=f"listing-{s.id}", kind="listing", title=(s.text[:80] + "…") if len(s.text) > 80 else s.text,
            borough=s.borough, address=s.address, bedrooms=[s.bedrooms] if s.bedrooms is not None else [], rent=s.rent,
            voucher_status=status, within_voucher_limit=s.within_voucher_limit, url=s.url, source=s.source, lat=s.lat, lon=s.lng))
    return items, hidden


# def _rank(i: FeedItem) -> tuple:
#     welcomes = i.voucher_status.startswith("Says it welcomes")
#     return (0 if i.kind == "listing" and welcomes else 1 if i.kind == "listing" and i.within_voucher_limit else 2,
#             i.deadline or "9999")




def _rank(i: FeedItem) -> tuple:
    if i.kind == "inventory":
        return (3, i.title)

    welcomes = i.voucher_status.startswith("Says it welcomes")

    return (
        0 if i.kind == "listing" and welcomes
        else 1 if i.kind == "listing" and i.within_voucher_limit
        else 2,
        i.deadline or "9999"
    )




# ---------------- historical rental inventory ----------------

# def inventory_items(limit: int = 250) -> List[FeedItem]:
    """Real FirstMover records; availability and voucher acceptance unverified."""
    import os

    if not os.getenv("MONGODB_URI"):
        return []

    from scanner.mongo_store import collection

    db = collection().database
    records = db["rental_inventory"].find(
        {"source": "firstmover"}
    ).sort("source_created_at", -1).limit(limit)

    items = []

    for doc in records:
        rent = doc.get("rent")
        beds = doc.get("bedrooms")
        address = doc.get("address")
        source_id = str(doc.get("source_id", doc["_id"]))

        items.append(
            FeedItem(
                id=f"inventory-firstmover-{source_id}",
                kind="inventory",
                title=address or f"Rental record {source_id}",
                source="FirstMover NYC (historical snapshot)",
                address=address,
                borough=doc.get("borough"),
                neighborhood=doc.get("neighborhood"),
                zip=doc.get("zip_code"),
                bedrooms=[int(beds)] if beds is not None else [],
                rent=rent,
                lat=doc.get("lat"),
                lon=doc.get("lng"),
                url=doc.get("url"),
                voucher_status=(
                    "Historical rental inventory only. "
                    "Current availability and voucher acceptance "
                    "have not been verified."
                ),
                within_voucher_limit=None,
                snapshot_month=doc.get("snapshot_month", "2026-08"),
                availability_verified=False,
            )
        )

    return items


def inventory_items(
    limit: int = 250,
    borough: Optional[str] = None,
    bedrooms: Optional[int] = None,
    max_rent: Optional[float] = None,
) -> List[FeedItem]:
    """Filter historical rental inventory in MongoDB before limiting results."""
    import os

    if not os.getenv("MONGODB_URI"):
        return []

    from scanner.mongo_store import collection

    db = collection().database

    query = {"source": "firstmover"}

    if borough:
        query["borough"] = borough

    if bedrooms is not None:
        query["bedrooms"] = bedrooms

    if max_rent is not None:
        query["rent"] = {"$lte": max_rent}

    records = (
        db["rental_inventory"]
        .find(query)
        .sort("source_created_at", -1)
        .limit(limit)
    )

    items = []

    for doc in records:
        rent = doc.get("rent")
        beds = doc.get("bedrooms")
        address = doc.get("address")
        source_id = str(doc.get("source_id", doc["_id"]))

        items.append(
            FeedItem(
                id=f"inventory-firstmover-{source_id}",
                kind="inventory",
                title=address or f"Rental record {source_id}",
                source="FirstMover NYC (historical snapshot)",
                address=address,
                borough=doc.get("borough"),
                neighborhood=doc.get("neighborhood"),
                zip=doc.get("zip_code"),
                bedrooms=[int(beds)] if beds is not None else [],
                rent=rent,
                lat=doc.get("lat"),
                lon=doc.get("lng"),
                url=doc.get("url"),
                voucher_status=(
                    "Historical rental inventory only. "
                    "Current availability and voucher acceptance "
                    "have not been verified."
                ),
                within_voucher_limit=None,
                snapshot_month=doc.get("snapshot_month", "2026-08"),
                availability_verified=False,
            )
        )

    return items



# ---------------- the feed ----------------
def _offer_fits(u: dict, household_size: Optional[int], income: Optional[float], has_voucher: bool, bedrooms: Optional[int]) -> bool:
    if bedrooms is not None and u.get("bedrooms") != bedrooms:
        return False
    if household_size is not None:
        lo, hi = u.get("household_min") or 1, u.get("household_max") or 99
        if not lo <= household_size <= hi:
            return False
    if income is not None and household_size is not None:
        lim = u.get("income_by_household_size", {}).get(str(household_size))
        if lim:
            mn, mx = lim
            if mx is not None and income > mx:
                return False
            # Voucher holders: minimum income "may not apply" (Housing Connect).
            if not has_voucher and mn is not None and income < mn:
                return False
    return True


def build_feed(borough: Optional[str] = None, bedrooms: Optional[int] = None, max_rent: Optional[float] = None,
               kind: Optional[str] = None, within_voucher_limit: bool = False, household_size: Optional[int] = None,
               income: Optional[float] = None, has_voucher: bool = True, use_gemini: bool = False) -> Feed:
    """has_voucher defaults to True: this feed is for voucher holders."""


    # Historical inventory does not need the Housing Connect API.
    if kind == "inventory":
        # records = inventory_items()
        records = inventory_items(
            borough=borough,
            bedrooms=bedrooms,
            max_rent=max_rent,
        )

        items = [
            i for i in records
            if (not borough or i.borough == borough)
            and (bedrooms is None or bedrooms in i.bedrooms)
            and (max_rent is None or i.rent is None or i.rent <= max_rent)
            and not within_voucher_limit
        ]

        return Feed(
            items=items,
            counts={
                "lotteries": 0,
                "listings": 0,
                "inventory": len(items),
            },
            hidden={
                "discriminatory": 0,
                "needs_review": 0,
            },
            notes=[
                "FirstMover August 2026 historical rental inventory.",
                "Current availability and voucher acceptance are unverified.",
            ],
            lotteries_as_of=None,
        )

    lots = []
    for i in lottery_items():
        if i.unit_offers:
            offers = [u for u in i.unit_offers if _offer_fits(u, household_size, income, has_voucher, bedrooms)
                      and (not within_voucher_limit or u.get("rent_within_voucher_limit"))
                      and (max_rent is None or (u.get("rent") or 0) <= max_rent)]
            if not offers:
                continue
            i = i.model_copy(update={"unit_offers": offers, "bedrooms": sorted({u["bedrooms"] for u in offers if u["bedrooms"] is not None})})
        lots.append(i)
    # lists, hidden = listing_items(use_gemini)
    # items = [i for i in lots + lists
    lists, hidden = listing_items(use_gemini)
    # inventory = inventory_items()
    inventory = inventory_items(
        borough=borough,
        bedrooms=bedrooms,
        max_rent=max_rent,
    )
    items = [i for i in lots + lists + inventory
             if (not borough or i.borough == borough)
             and (bedrooms is None or bedrooms in i.bedrooms)
             and (max_rent is None or i.rent is None or i.rent <= max_rent)
             and (not kind or i.kind == kind)
             and (not within_voucher_limit or i.within_voucher_limit)]
    items.sort(key=_rank)
    as_of = json.loads(CACHE.read_text()).get("fetched_at", "")[:16].replace("T", " ") + " UTC" if CACHE.exists() else None
    notes = [
        "Listings with discriminatory or questionable terms are left out (see 'hidden').",
        f"CityFHEPS rent limits by size (approx.): " + ", ".join(f"{'studio' if k == 0 else f'{k}BR'} ${v:,}" for k, v in C.PAYMENT_STANDARD.items()) + ".",
        "Lotteries: apply on Housing Connect before the deadline. " + VOUCHER_INCOME_NOTE,
    ]
    if not lists and not any(hidden.values()):
        notes.append("No scraped listings found yet. The scraper writes them to scanner/python/listings.json.")
    # return Feed(items=items, counts={"lotteries": sum(i.kind == "lottery" for i in items), "listings": sum(i.kind == "listing" for i in items)},
    #             hidden=hidden, notes=notes, lotteries_as_of=as_of)


    notes.append(
        "FirstMover inventory is an August 2026 historical snapshot. "
        "These records do not confirm present availability or voucher acceptance."
    )

    return Feed(
        items=items,
        counts={
            "lotteries": sum(i.kind == "lottery" for i in items),
            "listings": sum(i.kind == "listing" for i in items),
            "inventory": sum(i.kind == "inventory" for i in items),
        },
        hidden=hidden,
        notes=notes,
        lotteries_as_of=as_of,
    )

