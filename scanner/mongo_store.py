"""Read pre-classified MongoDB listings for Homeward NYC."""

from __future__ import annotations

import hashlib
import os
import re
import certifi
from datetime import datetime
from core.geo import geocode
from pymongo import MongoClient

from config.phrases import WELCOME
from core.schema import AnalysisResult
from scanner.store import ScannedListing

_client = None


def mongo_enabled() -> bool:
    return bool(os.environ.get("MONGODB_URI"))


def collection():
    global _client

    if _client is None:
        _client = MongoClient(
            os.environ["MONGODB_URI"],
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=5000,
        )
        _client.admin.command("ping")

    database = os.environ.get("MONGODB_DB", "voucher_detector")
    return _client[database]["listings"]


def iso_string(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value is not None else None


def convert_listing(doc: dict) -> ScannedListing:
    analysis = AnalysisResult.model_validate(doc["analysis"])

    text = doc.get("text") or analysis.analyzed_text
    extraction = analysis.extraction

    # Keep IDs stable between page refreshes and database updates.
    listing_id = hashlib.sha1(
        ((doc.get("url") or "") + text).encode("utf-8")
    ).hexdigest()[:12]

    raw_flags = [
        {
            "rule": flag.rule_id,
            "clause": flag.evidence_text,
            "explanation": flag.explanation,
            "severity": flag.severity,
        }
        for flag in analysis.flags
        if flag.severity != "info"
    ]

    welcomes = any(
        re.search(pattern, text, re.I)
        for pattern in WELCOME
    )

    bedrooms = extraction.bedrooms

    # Resolve listing location for the map.
    address = doc.get("address") or extraction.address
    borough = doc.get("borough") or extraction.borough

    lat = doc.get("lat")
    lng = doc.get("lng")

    # Only geocode when coordinates are missing.
    if (lat is None or lng is None) and address:
        location = geocode(address, borough)

        if location:
            lat = location["lat"]
            lng = location["lng"]

    return ScannedListing(
        id=listing_id,
        url=doc.get("url"),
        source=doc.get("source") or "scraper",
        discovered_at=iso_string(doc.get("discovered_at")),
        text=text,
        verdict=analysis.verdict,
        welcomes_vouchers=welcomes,
        within_voucher_limit=analysis.within_voucher_range,
        rent=extraction.monthly_rent,
        bedrooms=int(bedrooms) if bedrooms is not None else None,
        address=address,
        borough=borough,
        lat=lat,
        lng=lng,
        flags=raw_flags,
        result=analysis,
    )


def mongo_scan_all() -> list[ScannedListing]:
    records = collection().find(
        {"analysis": {"$exists": True}}
    )

    return [convert_listing(doc) for doc in records]


def mongo_get(listing_id: str) -> ScannedListing | None:
    # Use the same stable ID transformation as mongo_scan_all().
    for listing in mongo_scan_all():
        if listing.id == listing_id:
            return listing

    return None
