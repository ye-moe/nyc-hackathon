"""Import historical FirstMover NYC rental inventory into MongoDB.

Usage:
    python scanner/import_firstmover.py --limit 500
    python scanner/import_firstmover.py --limit 0
"""

import argparse
import csv
import os
from datetime import datetime, timezone
from pathlib import Path

import certifi
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT / "scanner/python/data/august_2026.csv"


def first(row, *names):
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def number(value):
    if not value:
        return None
    try:
        return float(str(value).replace(",", "").replace("$", ""))
    except (ValueError, TypeError):
        return None


def convert(row):
    listing_id = first(row, "id", "listing_id")
    url = first(row, "url", "listing_url")

    if not listing_id or not url:
        return None

    lat = number(first(row, "lat", "latitude"))
    lng = number(first(row, "lng", "lon", "longitude"))

    if lat is not None and not (-90 <= lat <= 90):
        lat = None
    if lng is not None and not (-180 <= lng <= 180):
        lng = None

    street = first(row, "street", "address")
    unit = first(row, "unit")

    address = " ".join(x for x in (street, unit) if x) or None

    return {
        "source": "firstmover",
        "source_id": str(listing_id),
        "url": url,
        "address": address,
        "neighborhood": first(row, "neighborhood"),
        "borough": first(row, "borough"),
        "zip_code": first(row, "zip_code", "zipcode"),
        "rent": number(first(row, "price", "rent")),
        "bedrooms": number(first(row, "bedrooms", "beds")),
        "bathrooms": number(first(row, "bathrooms", "baths")),
        "lat": lat,
        "lng": lng,
        "source_created_at": first(row, "created_at_utc"),
        "source_available_date": first(row, "available_date"),

        # These are historical snapshots, not verified live vacancies.
        "inventory_status": "historical_unverified",
        "dataset": "FirstMover NYC August 2026",
        "snapshot_month": "2026-08",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Number of CSV rows to examine; 0 means all rows.",
    )
    args = parser.parse_args()

    if not args.csv.is_file():
        raise SystemExit(f"CSV not found: {args.csv}")

    load_dotenv(ROOT / ".env")

    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise SystemExit("MONGODB_URI is missing from .env")

    client = MongoClient(
        uri,
        tlsCAFile=certifi.where(),
        serverSelectionTimeoutMS=10000,
    )
    client.admin.command("ping")

    db = client[os.getenv("MONGODB_DB", "voucher_detector")]
    collection = db["rental_inventory"]

    collection.create_index(
        [("source", 1), ("source_id", 1)],
        unique=True,
    )

    operations = []
    examined = 0
    prepared = 0
    skipped = 0

    with args.csv.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        print("CSV columns:", reader.fieldnames)

        for row in reader:
            if args.limit and examined >= args.limit:
                break

            examined += 1
            doc = convert(row)

            if not doc:
                skipped += 1
                continue

            prepared += 1

            key = {
                "source": doc["source"],
                "source_id": doc["source_id"],
            }

            operations.append(
                UpdateOne(
                    key,
                    {
                        "$set": doc,
                        "$setOnInsert": {
                            "imported_at": datetime.now(timezone.utc),
                        },
                    },
                    upsert=True,
                )
            )

            if len(operations) >= 500:
                collection.bulk_write(operations, ordered=False)
                operations.clear()

    if operations:
        collection.bulk_write(operations, ordered=False)

    print("\nImport complete.")
    print("CSV rows examined:", examined)
    print("Records prepared:", prepared)
    print("Skipped:", skipped)
    print(
        "FirstMover records in MongoDB:",
        collection.count_documents({"source": "firstmover"}),
    )

    client.close()


if __name__ == "__main__":
    main()
