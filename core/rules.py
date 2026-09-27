"""Deterministic rules engine. No LLM calls in this file: same input, same flags."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from config import cityfheps as C
from config import thresholds as T
from config.phrases import EXCLUSIONS, GOV_INCOME_BAND, INCOME_CARVE_OUT, WELCOME
from core.schema import Calculation, Extraction, Flag

I = re.IGNORECASE


def _any(patterns: List[str], text: str) -> bool:
    return any(re.search(p, text, I) for p in patterns)


def usd(n: float) -> str:
    return f"${round(n):,}"


def num(n: float) -> str:
    """40.0 -> '40', 2.5 -> '2.5'"""
    return str(int(n)) if float(n).is_integer() else f"{n:g}"


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def span_of(haystack: str, needle: str) -> Optional[Tuple[int, int]]:
    i = haystack.lower().find(needle.lower())
    return (i, i + len(needle)) if i >= 0 else None


# ---------- R1: explicit exclusions ----------
def r1(ex: Extraction, text: str) -> List[Flag]:
    flags: List[Flag] = []
    seen = set()
    for pid, _lang, label, pattern in EXCLUSIONS:
        for m in re.finditer(pattern, text, I):
            key = _norm(m.group(0))
            if key in seen:
                continue
            seen.add(key)
            flags.append(Flag(
                rule_id="R1", code=pid, severity="violation", evidence_text=m.group(0), span=m.span(),
                explanation=f"{label}. Refusing a tenant because rent is paid by a voucher is source-of-income discrimination."))
    # Exclusions the extractor found that the phrase list missed (paraphrases,
    # other languages, text inside images). Only counted if the quote is really
    # in the listing; otherwise the model may have invented it.
    for e in ex.explicit_exclusions:
        k = _norm(e.raw_text)
        if k in seen or any(k in s or s in k for s in seen):
            continue
        span = span_of(text, e.raw_text)
        if not span:
            continue
        seen.add(k)
        flags.append(Flag(
            rule_id="R1", code="extracted_exclusion", severity="review", evidence_text=e.raw_text, span=span,
            explanation=f'Possible refusal of voucher holders ("{e.phrase}"). Not in our phrase list, so a person should confirm.'))
    return flags


# ---------- R2: income requirement applied to full rent ----------
def annual_required(ex: Extraction, rent: Optional[float]) -> Optional[float]:
    ir = ex.income_requirement
    if not ir:
        return None
    if ir.type == "annual":
        return ir.value
    if not rent:
        return None
    if ir.type == "monthly":
        return ir.value * rent * 12
    return ir.value * 12 * rent if ir.value < T.MONTHLY_MULTIPLIER_MAX else ir.value * rent


def r2(ex: Extraction, text: str, within_range: Optional[bool]) -> List[Flag]:
    ir = ex.income_requirement
    if not ir:
        return []
    rent = ex.monthly_rent
    hh = C.EXAMPLE_HOUSEHOLD
    base = dict(rule_id="R2", evidence_text=ir.raw_text, span=span_of(text, ir.raw_text))

    if re.search(GOV_INCOME_BAND, text, I):
        return [Flag(**base, code="income_gov_band", severity="info",
                     explanation="Income limits look government-set (affordable housing lottery / AMI band). That is lawful.")]
    if _any(INCOME_CARVE_OUT, text) or _any(WELCOME, text):
        return [Flag(**base, code="income_carve_out", severity="info",
                     explanation="The listing accepts vouchers or applies the income requirement only to the tenant's share. That is lawful.")]

    required = annual_required(ex, rent)
    steps: List[str] = []

    if required is None:
        steps.append(f'The listing requires "{ir.raw_text}" but the rent isn\'t stated, so the dollar amount can\'t be computed.')
        calc = Calculation(steps=steps, example_household_income=hh["annual_income"])
        return [Flag(**base, code="income_rent_unknown", severity="review", calculation=calc,
                     explanation="Income requirement found, but without the rent we can't show it excludes voucher holders.")]

    # The multiplier in annual terms (40x rent -> 40; 3x monthly -> 36).
    annual_mult = required / rent if rent else None
    tenant_share = C.TENANT_SHARE_OF_INCOME * hh["annual_income"] / 12
    lawful = annual_mult * tenant_share if annual_mult else None
    pct = num(C.TENANT_SHARE_OF_INCOME * 100)

    if rent and annual_mult:
        steps.append(f"Rent is {usd(rent)}/month. The listing requires {num(annual_mult)}× rent: {num(annual_mult)} × {usd(rent)} = {usd(required)}/year.")
        steps.append(f"A CityFHEPS tenant pays {pct}% of income. Example household ({hh['size']} people, {usd(hh['annual_income'])}/year): "
                     f"{pct}% × {usd(hh['annual_income'])} ÷ 12 = {usd(tenant_share)}/month. The voucher pays the other {usd(rent - tenant_share)}.")
        steps.append(f"Applied lawfully to the tenant's share: {num(annual_mult)} × {usd(tenant_share)} = {usd(lawful)}/year. "
                     + ("The household qualifies." if hh["annual_income"] >= lawful else "The household would still fall short."))
        steps.append(f"Applied to the full rent: {usd(required)}/year required vs. {usd(hh['annual_income'])} earned. The household is rejected.")
    else:
        steps.append(f"The listing requires {usd(required)}/year in income.")
    excludes_all = required > C.INCOME_CEILING
    if excludes_all:
        steps.append(f"{usd(required)} is more than any CityFHEPS-eligible household can earn (about {usd(C.INCOME_CEILING)}/year), "
                     f"so this requirement excludes every voucher holder.")
    # Built after the steps: pydantic copies the list at construction time.
    calc = Calculation(steps=steps, example_household_income=hh["annual_income"], required_annual_income=round(required),
                       lawful_annual_income=round(lawful) if lawful else None, excludes_every_eligible_household=excludes_all)

    if within_range is False:
        return [Flag(**base, code="income_rent_above_standard", severity="review", calculation=calc,
                     explanation="Income requirement is applied to full rent, but the rent is above the CityFHEPS payment standard, "
                                 "so a voucher may not cover this unit anyway.")]
    if required <= hh["annual_income"]:
        return []
    return [Flag(**base, code="income_full_rent", severity="violation", calculation=calc,
                 explanation="The income requirement is applied to the full rent instead of the tenant's share, which screens out voucher holders.")]


# ---------- R3: other screening barriers ----------
def r3(ex: Extraction, text: str) -> List[Flag]:
    if _any(WELCOME, text):
        return []
    flags: List[Flag] = []
    if ex.employment_requirement:
        t = ex.employment_requirement.raw_text
        flags.append(Flag(rule_id="R3", code="employment_requirement", evidence_text=t, span=span_of(text, t),
                          severity="violation" if T.EMPLOYMENT_IS_VIOLATION else "review",
                          explanation="Requiring employment or wage income excludes voucher holders, whose rent is paid by a subsidy "
                                      "and who aren't required to work."))
    c = ex.credit_score_min
    if c and c.value >= T.CREDIT_SCORE_REVIEW_AT:
        flags.append(Flag(rule_id="R3", code="credit_minimum", evidence_text=c.raw_text, span=span_of(text, c.raw_text), severity="review",
                          explanation=f"A {num(c.value)}+ credit minimum can screen out voucher holders. CCHR guidance limits how credit may be used against them."))
    return flags


# ---------- R4: is the rent within CityFHEPS payment standards? ----------
def r4(ex: Extraction) -> Tuple[Optional[Flag], Optional[bool]]:
    rent, br = ex.monthly_rent, ex.bedrooms
    if rent is None or br is None:
        return None, None
    b = min(max(round(br), 0), 4)
    standard = C.PAYMENT_STANDARD[b]
    within = rent <= standard * C.PAYMENT_STANDARD_SLACK
    return Flag(
        rule_id="R4", code="within_voucher_range" if within else "above_voucher_range", severity="info",
        evidence_text=f"{usd(rent)}/month, {b}BR",
        explanation=(f"Rent is within the CityFHEPS payment standard for a {b}-bedroom ({usd(standard)}). A voucher holder could afford this unit."
                     if within else f"Rent is above the CityFHEPS payment standard for a {b}-bedroom ({usd(standard)}).")), within


def run_rules(ex: Extraction, text: str):
    """Returns (flags, verdict, within_voucher_range, notes)."""
    notes: List[str] = []
    r4flag, within = r4(ex)
    flags = r1(ex, text) + r2(ex, text, within) + r3(ex, text)
    if ex.confidence < T.MIN_EXTRACTION_CONFIDENCE and any(f.severity == "violation" for f in flags):
        flags = [f.model_copy(update={"severity": "review"}) if f.severity == "violation" else f for f in flags]
        notes.append("Extraction confidence is low, so violations were downgraded to review.")
    if r4flag:
        flags.append(r4flag)
    if any(f.severity == "violation" for f in flags):
        verdict = "violation"
    elif any(f.severity == "review" for f in flags):
        verdict = "needs_review"
    else:
        verdict = "no_issue_found"
    return flags, verdict, within, notes
