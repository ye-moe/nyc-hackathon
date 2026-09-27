"""HTTP API so the TypeScript pieces (Photon iMessage agent, Next.js dashboard)
can use the Python engine.

    uvicorn core.api:app --reload --port 8000      docs at http://localhost:8000/docs
                                                   web app at http://localhost:8000/
"""
from __future__ import annotations

from pathlib import Path

from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import analyze, approve_draft, build_packet, draft_complaint, gemini_available, GEMINI_MODEL
from core.complaint import ComplaintDraft, Contact, ListingInfo, Reporter, Respondent
from core.schema import AnalysisResult, ListingInput

app = FastAPI(title="Voucher Discrimination Detector")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])




from shelters.match import MatchResult, Profile, match as match_shelters, public_shelters  # noqa: E402



@app.post("/shelters/match", response_model=MatchResult)
def shelters_match(profile: Profile):
    """Narrow NYC shelters (public addresses only) to the ones this person is eligible for. Nothing is stored."""
    return match_shelters(profile)


@app.get("/shelters")
def shelters_list():
    """All NYC homeless shelters with publicly published addresses, each with its source."""
    return public_shelters()


from vacancies.feed import Feed, build_feed, refresh_lotteries  # noqa: E402



@app.get("/vacancies", response_model=Feed)
def vacancies(borough: Optional[str] = None, bedrooms: Optional[int] = None, max_rent: Optional[float] = None,
              kind: Optional[str] = None, within_voucher_limit: bool = False, household_size: Optional[int] = None,
              income: Optional[float] = None, has_voucher: bool = True):
    """Open Housing Connect lotteries + voucher-friendly listings in one feed."""
    return build_feed(borough, bedrooms, max_rent, kind, within_voucher_limit, household_size, income, has_voucher)


@app.post("/vacancies/refresh")
def vacancies_refresh():
    return {"open_lotteries": refresh_lotteries()}


# ---------------- Deliverables for Open Doors and Shelter Match ----------------
from fastapi.responses import Response  # noqa: E402

from shelters.packet import IntakePacket, build_intake_packet  # noqa: E402
from vacancies.plan import HousingPlan, build_plan  # noqa: E402


class PlanRequest(BaseModel):
    household_size: Optional[int] = None
    income: Optional[float] = None
    has_voucher: bool = True
    voucher_type: str = "CityFHEPS"
    bedrooms: Optional[int] = None
    borough: Optional[str] = None
    item_ids: Optional[list] = None       # feed item ids to include; default = best matches
    client_language: Optional[str] = None


@app.post("/vacancies/plan", response_model=HousingPlan)
def vacancies_plan(req: PlanRequest):
    """Open Doors deliverable: Housing Plan (lottery shortlist + deadlines, documents, landlord letters, calendar)."""
    return build_plan(req.household_size, req.income, req.has_voucher, req.voucher_type, req.bedrooms, req.borough,
                      req.item_ids, req.client_language)


@app.post("/vacancies/plan.ics")
def vacancies_plan_ics(req: PlanRequest):
    """The plan's lottery deadlines as a calendar file (Google / Apple / Outlook)."""
    plan = build_plan(req.household_size, req.income, req.has_voucher, req.voucher_type, req.bedrooms, req.borough, req.item_ids)
    return Response(plan.calendar_ics, media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="housing-deadlines.ics"'})


class PacketRequest2(Profile):
    shelter_ids: Optional[list] = None
    client_language: Optional[str] = None


@app.post("/shelters/intake-packet", response_model=IntakePacket)
def shelters_intake_packet(req: PacketRequest2):
    """Shelter Match deliverable: Intake Ready Packet (door, documents, shortlist, rights, if denied; printable + SMS)."""
    profile = Profile(**req.model_dump(exclude={"shelter_ids", "client_language"}))
    return build_intake_packet(profile, req.shelter_ids, req.client_language)


# ---------------- Voucher Guard: scraped listings checked for discrimination ----------------
import os  # noqa: E402

from scanner.store import get as get_scanned, scan_all  # noqa: E402


@app.get("/guard/listings")
def guard_listings(verdict: str = "flagged", borough: Optional[str] = None, rule: Optional[str] = None):
    """Scraped listings with their verdicts. verdict: flagged (violation + needs_review), violation, needs_review, all."""
    wanted = {"flagged": {"violation", "needs_review"}, "all": {"violation", "needs_review", "no_issue_found"}}.get(verdict, {verdict})
    rows = [x for x in scan_all() if x.verdict in wanted and (not borough or x.borough == borough)
            and (not rule or any(f["rule"] == rule for f in x.flags))]
    rows.sort(key=lambda x: (x.verdict != "violation", x.discovered_at or ""))
    all_rows = scan_all()
    return {
        "counts": {v: sum(x.verdict == v for x in all_rows) for v in ("violation", "needs_review", "no_issue_found")},
        "total_scanned": len(all_rows),
        "items": [x.model_dump(exclude={"result"}) for x in rows],
    }


@app.get("/guard/listings/{listing_id}")
def guard_listing(listing_id: str):
    """One scraped listing with its full analysis (feed it to /packet or /complaint)."""
    x = get_scanned(listing_id)
    if not x:
        raise HTTPException(404, "Listing not found")
    return x


@app.get("/config")
def config():
    """Browser config. The Maps JavaScript key is a public browser key; restrict it by referrer in Google Cloud."""
    return {"google_maps_api_key": os.environ.get("GOOGLE_MAPS_API_KEY", "")}




@app.get("/health")
def health():
    return {"ok": True, "gemini": gemini_available(), "model": GEMINI_MODEL}


class AnalyzeRequest(ListingInput):
    use_gemini: bool = True


@app.post("/analyze", response_model=AnalysisResult)
def analyze_listing(req: AnalyzeRequest):
    return analyze(req, use_gemini=req.use_gemini)


class AnalyzeUrlRequest(BaseModel):
    url: str
    bedrooms: Optional[float] = None
    monthly_rent: Optional[float] = None


@app.post("/analyze-url")
def analyze_listing_url(req: AnalyzeUrlRequest):
    from scanner.analyze_url import analyze_url
    result, fetched = analyze_url(req.url, {"bedrooms": req.bedrooms, "monthly_rent": req.monthly_rent})
    return {"result": result, "fetched": {k: v for k, v in fetched.items() if k != "screenshot_b64"}}


class PacketRequest(BaseModel):
    result: AnalysisResult
    tenant_language: Optional[str] = None
    packet_url: Optional[str] = None
    listing_url: Optional[str] = None


@app.post("/packet")
def packet(req: PacketRequest):
    return build_packet(req.result, req.tenant_language, req.packet_url, req.listing_url)


class ComplaintRequest(BaseModel):
    result: AnalysisResult
    agency: str = "cchr"
    listing: Optional[ListingInfo] = None
    respondent: Optional[Respondent] = None
    reporter: Optional[Reporter] = None
    contact: Optional[Contact] = None
    tenant_language: Optional[str] = None


@app.post("/complaint", response_model=ComplaintDraft)
def complaint(req: ComplaintRequest):
    try:
        return draft_complaint(req.result, req.agency, req.listing, req.respondent, req.reporter, req.contact, req.tenant_language)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


class ApproveRequest(BaseModel):
    draft: ComplaintDraft
    reviewer: str


@app.post("/complaint/approve", response_model=ComplaintDraft)
def complaint_approve(req: ApproveRequest):
    """Records a human review. Sends nothing."""
    try:
        return approve_draft(req.draft, req.reviewer)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/complaint/html", response_class=HTMLResponse)
def complaint_html(draft: ComplaintDraft):
    return draft.html


# Old page addresses -> new ones.
for _old, _new in {"/camera": "/voucher-guard/scan/", "/camera-scan/": "/voucher-guard/scan/",
                   "/shelter-finder/": "/shelter-match/", "/vacancies-feed/": "/open-doors/"}.items():
    app.add_api_route(_old, (lambda n: lambda: RedirectResponse(n))(_new), include_in_schema=False)

# The web app (web/): Voucher Guard, Open Doors, Shelter Match. Mounted last so API routes win.
app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "web", html=True), name="web")
