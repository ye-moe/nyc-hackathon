"""Data shapes shared by the engine, the API, and teammates' code."""
from __future__ import annotations

from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, Field


class IncomeRequirement(BaseModel):
    type: Literal["multiplier", "annual", "monthly"]
    value: float
    raw_text: str


class CreditMin(BaseModel):
    value: float
    raw_text: str


class RawText(BaseModel):
    raw_text: str


class Exclusion(BaseModel):
    phrase: str
    raw_text: str


class Extraction(BaseModel):
    """What Gemini (or the offline regex extractor) pulls out of a listing.
    Extraction only: nothing in here decides legality."""
    address: Optional[str] = None
    borough: Optional[str] = None
    zip: Optional[str] = None
    monthly_rent: Optional[float] = None
    bedrooms: Optional[float] = None
    income_requirement: Optional[IncomeRequirement] = None
    credit_score_min: Optional[CreditMin] = None
    employment_requirement: Optional[RawText] = None
    explicit_exclusions: List[Exclusion] = Field(default_factory=list)
    source_language: str = "en"
    broker_or_landlord_name: Optional[str] = None
    contact_phone: Optional[str] = None
    confidence: float = Field(0.7, ge=0, le=1)
    # The listing text as read from an image, and an English rendering.
    # The rules engine runs its phrase lists over both.
    transcribed_text: Optional[str] = None
    english_text: Optional[str] = None


Severity = Literal["violation", "review", "info"]
Verdict = Literal["violation", "needs_review", "no_issue_found"]
RuleId = Literal["R1", "R2", "R3", "R4"]


class Calculation(BaseModel):
    steps: List[str]                                   # one arithmetic step per line
    example_household_income: float
    required_annual_income: Optional[float] = None     # what the listing demands (full rent)
    lawful_annual_income: Optional[float] = None       # what it could demand (tenant share only)
    excludes_every_eligible_household: Optional[bool] = None


class Flag(BaseModel):
    rule_id: RuleId
    code: str                     # finer-grained id, e.g. "no_programs", "income_full_rent"
    severity: Severity
    evidence_text: str            # the clause, verbatim
    span: Optional[Tuple[int, int]] = None   # offsets into analyzed_text, when found
    explanation: str
    calculation: Optional[Calculation] = None


class ImageInput(BaseModel):
    base64: str
    mime_type: str = "image/jpeg"


class Hints(BaseModel):
    """Context from structured scrape fields or the conversation ("family of 3, 2BR")."""
    bedrooms: Optional[float] = None
    monthly_rent: Optional[float] = None
    household_size: Optional[int] = None


class ListingInput(BaseModel):
    id: Optional[str] = None
    text: Optional[str] = None
    url: Optional[str] = None
    image: Optional[ImageInput] = None
    hints: Optional[Hints] = None


class AnalysisResult(BaseModel):
    id: str
    verdict: Verdict
    flags: List[Flag]
    extraction: Extraction
    extractor: Literal["gemini", "regex"]
    analyzed_text: str
    within_voucher_range: Optional[bool] = None    # R4
    notes: List[str] = Field(default_factory=list)
    analyzed_at: str
