"""HTTP API for Person 3's UI.

    uvicorn vdd.api:app --reload --port 8000
    open http://localhost:8000/docs
"""
from __future__ import annotations

from typing import List, Optional

import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import buildings, llm
from .classifier import classify
from .schema import Listing

app = FastAPI(title="Voucher Discrimination Detector — models")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ListingIn(BaseModel):
    id: str
    text: str = ""
    source: str = "unknown"
    url: Optional[str] = None
    rent: Optional[float] = None
    bedrooms: Optional[int] = None
    address: Optional[str] = None
    bbl: Optional[str] = None
    image_b64: Optional[str] = None
    image_media_type: str = "image/png"


class BatchIn(BaseModel):
    listings: List[ListingIn]
    use_llm: bool = True


class BuildingsIn(BaseModel):
    buildings: List[dict]


@app.get("/health")
def health():
    return {"ok": True, "llm_enabled": llm.available(), "model": llm.MODEL}


@app.post("/classify")
def classify_one(item: ListingIn, use_llm: bool = True):
    return classify(Listing.from_dict(item.dict()), use_llm=use_llm).to_dict()


@app.post("/classify/batch")
def classify_batch(body: BatchIn):
    results = [classify(Listing.from_dict(l.dict()), use_llm=body.use_llm).to_dict() for l in body.listings]
    results.sort(key=lambda r: -r["confidence"])   # queue order for caseworkers
    return {"results": results,
            "counts": {k: sum(r["label"] == k for r in results) for k in ("discriminatory", "needs_review", "clean")}}


@app.post("/buildings/score")
def score_buildings(body: BuildingsIn):
    return _records(buildings.score(pd.DataFrame(body.buildings)))


@app.get("/buildings/mock")
def mock_buildings():
    """Scored fake buildings so the map can be built before real data exists."""
    return _records(buildings.score(buildings.make_mock()))


def _records(df: pd.DataFrame) -> list:
    return df.astype(object).where(df.notna(), None).to_dict(orient="records")
