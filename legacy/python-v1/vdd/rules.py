"""Layer 1: deterministic rules. Fast, free, explainable, and runs offline.

Every hit carries a weight (how strongly it alone implies an unlawful listing)
and a character span, so the UI can highlight exactly what triggered the flag.
Suppressors ("vouchers welcome", "HPD lottery") pull the score back down; they
are the main defense against false positives.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from . import config
from .schema import Evidence

CATEGORIES = [
    "explicit_refusal",        # "no programs", "no Section 8"
    "program_specific",        # "Section 8 ok, no CityFHEPS"
    "income_requirement",      # "must earn 40x rent" (math-checked)
    "employment_requirement",  # "working professionals only", "W-2 only"
    "coded_language",          # "no shelter referrals", "no third-party payments"
    "credit_requirement",      # "700+ credit" (weak alone)
    "none",
]

# Program names voucher holders use. Kept as one alternation so every refusal
# pattern covers all of them.
PROGRAMS = (
    r"(?:programs?|vouchers?|section[\s-]*8|sec\.?\s*8|s8|city\s*fheps|cityfheps|fheps|"
    r"hra|dss|dhs|hasa|hcv|housing\s+choice\s+vouchers?|linc|sepp|"
    r"government\s+(?:assistance|programs?)|public\s+assistance|rental\s+assistance|"
    r"welfare|subsid(?:y|ies|ized))"
)
# "no programs" must not match "no program fee" or "no program needed to apply".
NOT_FEE = r"(?!\s*(?:fees?|charges?|needed|required|necessary)\b)"


@dataclass
class Rule:
    id: str
    category: str
    pattern: re.Pattern
    weight: float
    explanation: str
    lang: str = "en"


def _r(p: str) -> re.Pattern:
    return re.compile(p, re.IGNORECASE)


RULES: List[Rule] = [
    # ---- explicit refusals (English) ----
    Rule("no_programs", "explicit_refusal",
         _r(rf"\bno\s+(?:\w+\s+){{0,2}}?{PROGRAMS}\b{NOT_FEE}"), 0.95,
         "Listing explicitly refuses a lawful source of income."),
    Rule("not_accepting", "explicit_refusal",
         _r(rf"\b(?:not?|don'?t|do\s+not|doesn'?t|does\s+not|won'?t|will\s+not|cannot|can'?t|unable\s+to)\s+"
            rf"(?:accept(?:ing)?|take|taking|work(?:ing)?\s+with|allow(?:ing)?|consider(?:ing)?)\s+(?:any\s+)?{PROGRAMS}\b"), 0.95,
         "Listing states the landlord does not accept vouchers/programs."),
    Rule("programs_not_accepted", "explicit_refusal",
         _r(rf"\b{PROGRAMS}\s+(?:are\s+|is\s+)?(?:not\s+(?:accepted|allowed|welcome|considered)|need\s+not\s+apply)"), 0.95,
         "Listing states vouchers/programs are not accepted."),
    Rule("private_pay_only", "explicit_refusal",
         _r(r"\b(?:private[\s-]*pay|self[\s-]*pay)\s+only\b"), 0.85,
         "'Private pay only' excludes tenants whose rent is paid by a subsidy."),
    # ---- program-specific ----
    Rule("section8_only", "program_specific",
         _r(r"\bsection\s*8\s+only\b|\bonly\s+(?:accept|take)\s+section\s*8\b"), 0.85,
         "Accepting only one voucher type still refuses CityFHEPS holders."),
    # ---- coded language ----
    Rule("no_third_party", "coded_language",
         _r(r"\bno\s+third[\s-]*party\s+(?:payments?|payers?|checks?)\b"), 0.80,
         "'No third-party payments' excludes subsidies, which are paid to the landlord directly."),
    Rule("no_shelter", "coded_language",
         _r(r"\bno\s+(?:shelter|agency|case\s*worker|caseworker)\s*(?:referrals?|clients?|placements?|tenants?)?\b"), 0.85,
         "Refusing shelter/agency referrals is a proxy for refusing voucher holders."),
    Rule("no_handouts", "coded_language",
         _r(r"\bno\s+(?:handouts|freeloaders|government\s+cheese)\b"), 0.85,
         "Derogatory coded language targeting subsidy recipients."),
    # ---- employment ----
    Rule("employed_only", "employment_requirement",
         _r(r"\b(?:working\s+professionals?|employed\s+(?:applicants?|tenants?|persons?)|w-?2\s+(?:employees?|income))\s+only\b"
            r"|\bmust\s+(?:be\s+(?:currently\s+)?employed|have\s+(?:a\s+)?(?:full[\s-]*time\s+)?job)\b"
            r"|\bonly\s+(?:working\s+professionals?|employed\s+applicants?)\b"), 0.82,
         "Employment-only requirements exclude voucher holders, who are not required to work."),
    Rule("employment_income_only", "employment_requirement",
         _r(r"\bincome\s+must\s+(?:be|come)\s+from\s+(?:employment|a\s+job|wages)\b"), 0.80,
         "Requiring income to come from employment excludes subsidy income by definition."),
    # ---- credit ----
    Rule("credit_min", "credit_requirement",
         _r(r"\b(?:min(?:imum)?\.?\s+)?credit\s*(?:score)?\s*(?:of\s+)?(?:6[5-9]\d|7\d\d|8\d\d)\s*\+?|\b(?:6[5-9]\d|7\d\d)\+?\s*credit\b"), 0.30,
         "High credit minimums, applied to the full rent, can screen out voucher holders."),

    # ---- Spanish ----
    Rule("es_no_programas", "explicit_refusal",
         _r(r"\bno\s+(?:se\s+)?(?:acepta(?:n|mos)?|aceptamos|recibimos|tomamos)\s+(?:\w+\s+)?"
            r"(?:programas?|vouchers?|cupones|secci[oó]n\s*8|ayuda\s+del\s+gobierno|asistencia)"
            r"|\bno\s+(?:programas?|vouchers?|secci[oó]n\s*8)\b"), 0.95,
         "Explicit refusal of programs/vouchers (Spanish).", "es"),
    Rule("es_solo_trabajadores", "employment_requirement",
         _r(r"\bs[oó]lo\s+(?:personas\s+)?(?:que\s+trabajen|trabajadores|con\s+empleo)\b"), 0.55,
         "Employment-only requirement (Spanish).", "es"),
    # ---- Chinese ----
    Rule("zh_no_programs", "explicit_refusal",
         _r(r"不(?:接受|收|要|租给)\s*(?:任何)?\s*(?:政府)?\s*(?:program|programs|補助|补助|福利|八號|八号|第八|section\s*8|voucher|住房券)"
            r"|(?:program|補助|补助|福利)\s*(?:勿扰|免问|不收|不要)"), 0.95,
         "Explicit refusal of government housing assistance (Chinese).", "zh"),
    # ---- Russian ----
    Rule("ru_no_programs", "explicit_refusal",
         _r(r"без\s+(?:программ|ваучеров|сабсидий|субсидий|section\s*8)"
            r"|(?:программ[ыу]?|ваучер[ыа]?|section\s*8)\s+не\s+(?:принимаем|берем|берём|рассматриваем)"), 0.95,
         "Explicit refusal of programs/vouchers (Russian).", "ru"),
]

# Welcoming language. If present, it strongly suggests the listing is lawful,
# unless a refusal also appears ("Section 8 welcome, no CityFHEPS").
SUPPRESSORS: List[Tuple[str, re.Pattern]] = [
    ("welcome", _r(rf"\b(?:all\s+)?{PROGRAMS}\s+(?:are\s+|is\s+)?(?:welcome[d]?|accepted|ok(?:ay)?|considered|encouraged|fine)\b")),
    ("accept", _r(rf"\b(?:we\s+)?(?:accept(?:s|ing)?|take[s]?|welcome[s]?|work\s+with)\s+(?:all\s+)?(?:\w+\s+)?{PROGRAMS}\b")),
    ("waived", _r(rf"\bincome\s+(?:requirements?|restrictions?)\s+(?:is\s+|are\s+)?(?:waived|do(?:es)?\s+not\s+apply|adjusted)"
                  rf"|\b(?:tenant'?s?\s+(?:portion|share))\b")),
    ("es_welcome", _r(r"\bse\s+aceptan\s+(?:programas|vouchers|secci[oó]n\s*8)|\bprogramas\s+bienvenidos")),
    ("zh_welcome", _r(r"(?:接受|欢迎|歡迎)\s*(?:政府)?\s*(?:program|補助|补助|八号|八號|住房券)")),
]

# Government-set income bands (affordable housing lotteries, HDFC co-ops) are
# lawful; they are not a landlord choosing to exclude voucher holders.
GOV_INCOME_BAND = _r(r"\b(?:housing\s+connect|hpd\s+lottery|affordable\s+housing\s+lottery|% ?ami\b|area\s+median\s+income|hdfc|lihtc|mitchell[\s-]*lama)")

# ---- income requirement parsing ----

_MULT = _r(r"\b(\d{2,3}(?:\.\d)?)\s*(?:x|×|times)\s*(?:the\s+)?(?:monthly\s+)?(?:rent|rental|monthly)"
           r"|\b(?:earn|income\s+of|make|salary\s+of)\s+(?:at\s+least\s+)?(\d{2,3})\s*(?:x|×|times)")
_MONTHLY_MULT = _r(r"\b([2-4](?:\.\d)?)\s*(?:x|×|times)\s*(?:the\s+)?(?:monthly\s+)?rent\s+(?:per|a|each|every|in)\s+month|\bmonthly\s+income\s+(?:of\s+)?(?:at\s+least\s+)?([2-4](?:\.\d)?)\s*(?:x|×|times)")
_DOLLAR_INCOME = _r(r"(?:income|salary|earn(?:ings)?|make)\D{0,25}\$\s?(\d{2,3}(?:,\d{3})|\d{2,3}\s?k)\b")
_RENT_IN_TEXT = _r(r"\$\s?(\d{1,2},?\d{3})(?:\.\d{2})?\s*(?:/\s*mo(?:nth)?|per\s+month|a\s+month|monthly)?")


def _money(s: str) -> float:
    s = s.lower().replace(",", "").replace(" ", "")
    return float(s[:-1]) * 1000 if s.endswith("k") else float(s)


def income_analysis(text: str, rent: Optional[float], bedrooms: Optional[int]) -> Optional[dict]:
    """Turn 'must earn 40x rent' into dollars and compare to what voucher holders can earn."""
    if rent is None:
        m = _RENT_IN_TEXT.search(text)
        if m:
            rent = _money(m.group(1))

    required, span, basis = None, None, None
    m = _MONTHLY_MULT.search(text)
    if m:
        mult = float(m.group(1) or m.group(2))
        if rent:
            required = mult * rent * 12
        span, basis = m.span(), f"{mult:g}x monthly rent, per month"
    else:
        m = _MULT.search(text)
        if m:
            mult = float(m.group(1) or m.group(2))
            if mult < 10:           # "3x rent" conventionally means monthly income
                mult *= 12
            if rent:
                required = mult * rent
            span, basis = m.span(), f"{mult:g}x monthly rent, per year"
        else:
            m = _DOLLAR_INCOME.search(text)
            if m:
                required = _money(m.group(1))
                span, basis = m.span(), "stated dollar minimum"
    if span is None:
        return None

    cap = config.CITYFHEPS_MAX_RENT.get(min(bedrooms, 4)) if bedrooms is not None else None
    result = {
        "basis": basis,
        "rent": rent,
        "required_annual_income": round(required) if required else None,
        "voucher_income_ceiling": config.VOUCHER_INCOME_CEILING,
        "cityfheps_max_rent": cap,
        # 10% slack: payment standards move yearly and our table is approximate.
        "rent_within_voucher_limit": (rent <= cap * 1.1) if (rent and cap) else None,
        "excludes_all_voucher_holders": bool(required and required > config.VOUCHER_INCOME_CEILING),
        "span": span,
    }
    if required:
        result["summary"] = (
            f"Requires ~${required:,.0f}/yr ({basis}). CityFHEPS households earn at most "
            f"~${config.VOUCHER_INCOME_CEILING:,}/yr, so this requirement "
            + ("excludes every eligible voucher holder." if result["excludes_all_voucher_holders"]
               else "does not by itself exclude all voucher holders.")
        )
    else:
        result["summary"] = f"Income requirement found ({basis}) but rent is unknown; can't compute dollars."
    return result


@dataclass
class RuleResult:
    score: float
    category: str
    evidence: List[Evidence]
    reasons: List[str]
    suppressed_by: List[str]
    income: Optional[dict]
    language: str


def detect_language(text: str) -> str:
    if re.search(r"[一-鿿]", text):
        return "zh"
    if re.search(r"[Ѐ-ӿ]", text):
        return "ru"
    if re.search(r"[ঀ-৿]", text):
        return "bn"
    if re.search(r"[؀-ۿ]", text):
        return "ar"
    words = set(re.findall(r"[a-záéíóúñ]+", text.lower()))
    es = {"el", "la", "los", "las", "de", "apartamento", "cuarto", "habitación", "renta", "alquiler", "se", "con", "para", "no", "y"}
    en = {"the", "and", "with", "for", "apartment", "rent", "bedroom", "is", "to", "of"}
    return "es" if len(words & es) > len(words & en) + 1 else "en"


def noisy_or(weights: List[float]) -> float:
    p = 1.0
    for w in weights:
        p *= (1 - w)
    return 1 - p


def classify_rules(text: str, rent: Optional[float] = None, bedrooms: Optional[int] = None) -> RuleResult:
    evidence, reasons, weights, cats = [], [], [], []
    for rule in RULES:
        for m in rule.pattern.finditer(text):
            evidence.append(Evidence(quote=m.group(0), start=m.start(), end=m.end(), rule_id=rule.id))
            if rule.id not in {e.rule_id for e in evidence[:-1]}:
                reasons.append(rule.explanation)
                weights.append(rule.weight)
                cats.append((rule.weight, rule.category))

    # Income requirement: weight depends on the math, not just the phrase.
    inc = income_analysis(text, rent, bedrooms)
    gov_band = bool(GOV_INCOME_BAND.search(text))
    if inc and not gov_band:
        if inc["excludes_all_voucher_holders"]:
            w = 0.85 if inc["rent_within_voucher_limit"] is not False else 0.60
        elif inc["required_annual_income"] is None:
            w = 0.50        # "40x rent" with unknown rent: suspicious, not provable
        else:
            w = 0.35
        s, e = inc["span"]
        evidence.append(Evidence(quote=text[s:e], start=s, end=e, rule_id="income_requirement"))
        reasons.append(inc["summary"])
        weights.append(w)
        cats.append((w, "income_requirement"))

    suppressed = [name for name, p in SUPPRESSORS if p.search(text)]
    # Suppressor text often overlaps refusal text ("Section 8 accepted, no CityFHEPS"
    # vs "vouchers accepted"). Explicit refusals survive suppression; softer
    # signals (income, employment, credit) get discounted hard.
    if suppressed:
        hard = [w for w, c in cats if c in ("explicit_refusal", "program_specific")]
        soft = [w * 0.25 for w, c in cats if c not in ("explicit_refusal", "program_specific")]
        score = noisy_or(hard + soft)
        if not hard:
            reasons.append(f"Discounted: listing also contains welcoming language ({', '.join(suppressed)}).")
    elif gov_band and inc:
        score = noisy_or(weights)
        reasons.append("Income band appears government-set (lottery/AMI) — lawful; not counted.")
    else:
        score = noisy_or(weights)

    category = max(cats)[1] if cats else "none"
    return RuleResult(score=round(score, 3), category=category, evidence=evidence, reasons=reasons,
                      suppressed_by=suppressed, income=_strip_span(inc), language=detect_language(text))


def _strip_span(inc: Optional[dict]) -> Optional[dict]:
    if inc is None:
        return None
    return {k: v for k, v in inc.items() if k != "span"}
