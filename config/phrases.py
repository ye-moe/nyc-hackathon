"""Phrase lists for the deterministic rules (regex sources, matched case-insensitively).
Non-English patterns are best-effort: have a native speaker check the
Bengali/Chinese/Russian ones before relying on them in the pitch."""

# Every name a voucher program goes by, including common misspellings.
PROGRAMS = (
    r"(?:programs?|progams?|programms?|vouchers?|vouchars?|voucers?|section[\s-]*8|secton[\s-]*8|sec\.?[\s-]*8|s8|"
    r"city[\s-]*fheps|cityfheps|citifheps|city[\s-]*feps|fheps|hra|dss|dhs|hasa|hcv|housing\s+choice\s+vouchers?|linc|sepp|"
    r"government\s+(?:assistance|programs?)|public\s+assistance|(?:rental\s+)?assistance\s+programs?|rental\s+assistance|welfare|subsid(?:y|ies|ized))"
)

# "no program fee", "no program needed to apply" are not refusals.
NOT_FEE = r"(?!\s*(?:fees?|charges?|needed|required|necessary)\b)"

# R1: explicit exclusions and coded equivalents. (id, lang, label, pattern)
EXCLUSIONS = [
    ("no_programs", "en", "Refuses vouchers/programs",
     r"\bno\s+(?:\w+\s+){0,2}?" + PROGRAMS + r"\b" + NOT_FEE),
    ("not_accepting", "en", "Says landlord does not accept vouchers/programs",
     r"\b(?:not?|don'?t|do\s+not|doesn'?t|does\s+not|won'?t|will\s+not|cannot|can'?t|unable\s+to)\s+(?:currently\s+)?"
     r"(?:accept(?:ing)?|take|taking|work(?:ing)?\s+with|allow(?:ing)?|consider(?:ing)?)\s+(?:any\s+)?" + PROGRAMS + r"\b"),
    ("programs_not_accepted", "en", "Says vouchers/programs are not accepted",
     r"\b" + PROGRAMS + r"\s+(?:are\s+|is\s+)?(?:not\s+(?:accepted|allowed|welcome|considered)|need\s+not\s+apply)"),
    ("private_pay_only", "en", "Private pay only",
     r"\b(?:private[\s-]*pay|self[\s-]*pay)\s+only\b|\brent\s+paid\s+by\s+tenant\s+only\b"),
    ("section8_only", "en", "Accepts only one voucher type (excludes CityFHEPS)",
     r"\bsection\s*8\s+only\b|\bonly\s+(?:accept|take)\s+section\s*8\b"),
    ("no_third_party", "en", "No third-party payments (subsidies are paid by a third party)",
     r"\bno\s+third[\s-]*party\s+(?:payments?|payers?|checks?)\b"),
    ("no_shelter", "en", "Refuses shelter/agency referrals",
     r"\bno\s+(?:shelter|agency|case\s*worker|caseworker)\s*(?:referrals?|clients?|placements?|tenants?|calls?)?\b"),
    ("no_handouts", "en", "Derogatory coded language",
     r"\bno\s+(?:handouts|freeloaders|government\s+cheese)\b"),
    ("es_no_programas", "es", "Refuses programs/vouchers (Spanish)",
     r"\bno\s+(?:se\s+)?(?:acepta(?:n|mos)?|recibimos|tomamos)\s+(?:\w+\s+)?(?:programas?|vouchers?|cupones|secci[oó]n\s*8|ayuda\s+del\s+gobierno|asistencia)"
     r"|\bno\s+(?:programas?|vouchers?|secci[oó]n\s*8)\b"),
    ("zh_no_programs", "zh", "Refuses government assistance (Chinese)",
     r"不(?:接受|收|要|租给)\s*(?:任何)?\s*(?:政府)?\s*(?:program|programs|補助|补助|福利|八號|八号|第八|section\s*8|voucher|住房券)"
     r"|(?:program|補助|补助|福利)\s*(?:勿扰|免问|不收|不要)"),
    ("ru_no_programs", "ru", "Refuses programs/vouchers (Russian)",
     r"без\s+(?:программ|ваучеров|субсидий|section\s*8)|(?:программ[ыу]?|ваучер[ыа]?|section\s*8)\s+не\s+(?:принимаем|берем|берём|рассматриваем)"),
    ("bn_no_programs", "bn", "Refuses programs/vouchers (Bengali)",
     r"(?:ভাউচার|প্রোগ্রাম|সরকারি\s*সাহায্য)\s*(?:নেওয়া\s*হয়\s*না|নেই|চলবে\s*না|গ্রহণযোগ্য\s*নয়)|কোন\s*(?:ভাউচার|প্রোগ্রাম)\s*না"),
]

# Welcoming language. Discounts R2/R3 (soft signals). Never cancels R1:
# "Section 8 welcome, no CityFHEPS" is still a violation.
WELCOME = [
    r"\b(?:all\s+)?" + PROGRAMS + r"\s+(?:tenants?\s+|holders?\s+|participants?\s+)?(?:are\s+|is\s+)?(?:welcome[d]?|accepted|ok(?:ay)?|considered|encouraged|fine)\b",
    r"\b(?:we\s+)?(?:gladly\s+)?(?:accept(?:s|ing)?|take[s]?|welcome[s]?|work\s+with)\s+(?:all\s+)?(?:\w+\s+){0,2}?" + PROGRAMS + r"\b",
    r"\bse\s+aceptan\s+(?:\w+\s+){0,2}?(?:programas|vouchers|secci[oó]n\s*8)|\bprogramas\s+bienvenidos",
    r"(?:接受|欢迎|歡迎)\s*(?:政府)?\s*(?:program|補助|补助|八号|八號|住房券)",
]

# R2 carve-outs: income rules applied only to the tenant share, or the subsidy
# counted as income. These make an income requirement lawful.
INCOME_CARVE_OUT = [
    r"\b(?:tenant'?s?|your)\s+(?:portion|share)\b",
    r"\bincome\s+(?:requirements?|restrictions?)\s+(?:is\s+|are\s+)?(?:waived|do(?:es)?\s+not\s+apply|adjusted)",
    r"\b(?:rental\s+assistance|vouchers?|subsid(?:y|ies))\s+counts?\s+(?:toward|towards|as)\s+income",
    r"\bor\s+(?:rental\s+assistance|a\s+voucher|vouchers?)\b",
]

# Government-set income bands (lotteries, Mitchell-Lama) are lawful.
GOV_INCOME_BAND = r"\b(?:housing\s+connect|hpd\s+lottery|affordable\s+housing\s+lottery|%\s*ami\b|ami\b|area\s+median\s+income|hdfc|lihtc|mitchell[\s-]*lama)"

# R3: other screening barriers.
EMPLOYMENT = [
    r"\b(?:working\s+professionals?|employed\s+(?:applicants?|tenants?|persons?)|w-?2\s+(?:employees?|income))\s+only\b",
    r"\bmust\s+(?:be\s+(?:currently\s+)?employed|have\s+(?:a\s+)?(?:full[\s-]*time\s+)?job)\b",
    r"\b(?:only|will\s+only)\s+(?:rents?\s+to\s+|consider\s+)?(?:working\s+professionals?|employed\s+applicants?|tenants?\s+with\s+jobs)\b",
    r"\bincome\s+must\s+(?:be|come)\s+from\s+(?:employment|a\s+job|wages)\b",
    r"\bproof\s+of\s+employment\s+income\b",
    r"\bpay\s*stubs?\s+(?:required|needed|a\s+must)\b|\bmust\s+(?:have|show)\s+pay\s*stubs?\b",
    r"\bs[oó]lo\s+(?:personas\s+)?(?:que\s+trabajen|trabajadores|con\s+empleo)\b",
]
