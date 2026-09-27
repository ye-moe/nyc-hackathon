"""Offline extractor. Fills the same Extraction schema as Gemini using regexes,
so the rules engine, eval, and demo all work with no network or API key.
Also the fallback when Gemini fails."""
from __future__ import annotations

import re

from config.phrases import EMPLOYMENT, EXCLUSIONS
from core.schema import CreditMin, Exclusion, Extraction, IncomeRequirement, RawText

MONEY = r"\$\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?\s?k|\d{3,6})"


def money(s: str) -> float:
    t = re.sub(r"[,\s$]", "", s.lower())
    return float(t[:-1]) * 1000 if t.endswith("k") else float(t)


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
    es = {"el", "la", "los", "las", "de", "apartamento", "cuarto", "habitación", "renta", "alquiler", "se", "con", "para", "y", "al", "mes"}
    en = {"the", "and", "with", "for", "apartment", "rent", "bedroom", "is", "to", "of", "in"}
    return "es" if len(words & es) > len(words & en) + 1 else "en"


def regex_extract(text: str) -> Extraction:
    ex = Extraction(explicit_exclusions=[], source_language=detect_language(text), confidence=0.7)
    I = re.IGNORECASE

    # Rent: "$2,200/mo", "$2,200 per month", "月租2600", "rent: $2,300", or a bare "$2,300." in a short listing.
    rent = (re.search(MONEY + r"\s*(?:/\s*mo(?:nth)?|per\s+month|a\s+month|monthly|al\s+mes)", text, I)
            or re.search(r"月租\s*\$?(\d{3,5})", text)
            or re.search(r"(?:rent|renta)\s*:?\s*" + MONEY, text, I)
            or re.search(r"(?:^|[\s,(])" + MONEY + r"(?=[\s.,)]|$)", text, I))
    if rent:
        v = money(rent.group(1))
        if 400 <= v <= 30000:
            ex.monthly_rent = v

    br = (re.search(r"\b(\d)\s*(?:br|bd|bed(?:room)?s?|-bed|\s+bed)\b", text, I)
          or re.search(r"(\d)\s*(?:cuartos?|habitaciones?|комнатн|室|房)", text, I))
    if br:
        ex.bedrooms = float(br.group(1))
    elif re.search(r"\bstudio\b|estudio|单间|一房", text, I):
        ex.bedrooms = 1.0 if "一房" in text else 0.0
    elif re.search(r"\bone[\s-]bed(?:room)?\b", text, I):
        ex.bedrooms = 1.0
    elif re.search(r"\btwo[\s-]bed(?:room)?\b", text, I):
        ex.bedrooms = 2.0

    addr = re.search(r"\b\d{1,5}\s+(?:(?:[NSEW]\.?|North|South|East|West)\s+)?(?:\d{1,3}(?:st|nd|rd|th)|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+"
                     r"(?:St|Street|Ave|Avenue|Blvd|Boulevard|Rd|Road|Pl|Place|Pkwy|Parkway|Dr|Drive|Ct|Court|Ln|Lane|Ter|Terrace)\b\.?", text)
    if addr:
        ex.address = addr.group(0).rstrip(".")
    boro = re.search(r"\b(Bronx|Brooklyn|Manhattan|Queens|Staten Island)\b", text, I)
    if boro:
        ex.borough = boro.group(1)
    zp = re.search(r"\b(1[01]\d{3})\b", text)
    if zp:
        ex.zip = zp.group(1)

    phone = re.search(r"(?:\+?1[\s.-]?)?\(?\b(\d{3})\)?[\s.-]?(\d{3})[\s.-]?(\d{4})\b", text)
    if phone:
        ex.contact_phone = f"({phone.group(1)}) {phone.group(2)}-{phone.group(3)}"
    else:  # flyers often give a 7-digit number: "Call 555-0134"
        local = re.search(r"\b(?:call|text|phone|tel)\.?:?\s+(\d{3})[\s.-](\d{4})\b", text, I)
        if local:
            ex.contact_phone = f"{local.group(1)}-{local.group(2)}"
    name = re.search(r"\b(?:[Cc]all|[Tt]ext|[Cc]ontact|[Aa]sk\s+for)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)(?=[\s,.!:]|$)", text)
    if name:
        ex.broker_or_landlord_name = name.group(1)

    # Income requirement. Order matters: "3x rent in monthly income" before "40x rent".
    monthly_mult = re.search(
        r"\b([2-4](?:\.\d)?)\s*(?:x|×|times)\s*(?:the\s+)?(?:monthly\s+)?rent\s+(?:per|a|each|every|in)\s+(?:month|monthly)"
        r"|\bmonthly\s+income\s+(?:of\s+)?(?:at\s+least\s+)?([2-4](?:\.\d)?)\s*(?:x|×|times)", text, I)
    mult = re.search(
        r"\b(\d{1,3}(?:\.\d)?)\s*(?:x|×|times)\s*(?:the\s+)?(?:monthly\s+|annual\s+)?(?:rent|rental)\b"
        r"|\b(?:earn|income\s+of|make|salary\s+of)\s+(?:at\s+least\s+)?(\d{1,3})\s*(?:x|×|times)", text, I)
    annual = re.search(r"(?:income|salary|earn(?:ings)?|make)[^$\n]{0,30}" + MONEY, text, I)
    if monthly_mult:
        ex.income_requirement = IncomeRequirement(type="monthly", value=float(monthly_mult.group(1) or monthly_mult.group(2)), raw_text=monthly_mult.group(0))
    elif mult:
        ex.income_requirement = IncomeRequirement(type="multiplier", value=float(mult.group(1) or mult.group(2)), raw_text=mult.group(0))
    elif annual:
        v = money(annual.group(1))
        if v >= 10000:
            ex.income_requirement = IncomeRequirement(type="annual", value=v, raw_text=annual.group(0))

    credit = re.search(r"\b(?:min(?:imum)?\.?\s+)?credit\s*(?:score)?\s*(?:of\s+)?(\d{3})\s*\+?|\b(\d{3})\+?\s*credit\b", text, I)
    if credit:
        v = float(credit.group(1) or credit.group(2))
        if 300 <= v <= 850:
            ex.credit_score_min = CreditMin(value=v, raw_text=credit.group(0))

    for p in EMPLOYMENT:
        m = re.search(p, text, I)
        if m:
            ex.employment_requirement = RawText(raw_text=m.group(0))
            break

    for _id, _lang, label, pattern in EXCLUSIONS:
        for m in re.finditer(pattern, text, I):
            ex.explicit_exclusions.append(Exclusion(phrase=label, raw_text=m.group(0)))
    return ex
