// Phrase lists for the deterministic rules. Regex sources (case-insensitive).
// Non-English patterns are best-effort: have a native speaker check the
// Bengali/Chinese/Russian ones before relying on them in the pitch.

// Every name a voucher program goes by, including common misspellings.
export const PROGRAMS = String.raw`(?:programs?|progams?|programms?|vouchers?|vouchars?|voucers?|section[\s-]*8|secton[\s-]*8|sec\.?[\s-]*8|s8|` +
  String.raw`city[\s-]*fheps|cityfheps|citifheps|city[\s-]*feps|fheps|hra|dss|dhs|hasa|hcv|housing\s+choice\s+vouchers?|linc|sepp|` +
  String.raw`government\s+(?:assistance|programs?)|public\s+assistance|(?:rental\s+)?assistance\s+programs?|rental\s+assistance|welfare|subsid(?:y|ies|ized))`;

// "no program fee", "no program needed to apply" are not refusals.
const NOT_FEE = String.raw`(?!\s*(?:fees?|charges?|needed|required|necessary)\b)`;

export type Phrase = { id: string; pattern: string; label: string; lang: string };

// R1: explicit exclusions and coded equivalents.
export const EXCLUSIONS: Phrase[] = [
  { id: "no_programs", lang: "en", label: "Refuses vouchers/programs",
    pattern: String.raw`\bno\s+(?:\w+\s+){0,2}?${PROGRAMS}\b${NOT_FEE}` },
  { id: "not_accepting", lang: "en", label: "Says landlord does not accept vouchers/programs",
    pattern: String.raw`\b(?:not?|don'?t|do\s+not|doesn'?t|does\s+not|won'?t|will\s+not|cannot|can'?t|unable\s+to)\s+(?:currently\s+)?` +
      String.raw`(?:accept(?:ing)?|take|taking|work(?:ing)?\s+with|allow(?:ing)?|consider(?:ing)?)\s+(?:any\s+)?${PROGRAMS}\b` },
  { id: "programs_not_accepted", lang: "en", label: "Says vouchers/programs are not accepted",
    pattern: String.raw`\b${PROGRAMS}\s+(?:are\s+|is\s+)?(?:not\s+(?:accepted|allowed|welcome|considered)|need\s+not\s+apply)` },
  { id: "private_pay_only", lang: "en", label: "Private pay only",
    pattern: String.raw`\b(?:private[\s-]*pay|self[\s-]*pay)\s+only\b|\brent\s+paid\s+by\s+tenant\s+only\b` },
  { id: "section8_only", lang: "en", label: "Accepts only one voucher type (excludes CityFHEPS)",
    pattern: String.raw`\bsection\s*8\s+only\b|\bonly\s+(?:accept|take)\s+section\s*8\b` },
  { id: "no_third_party", lang: "en", label: "No third-party payments (subsidies are paid by a third party)",
    pattern: String.raw`\bno\s+third[\s-]*party\s+(?:payments?|payers?|checks?)\b` },
  { id: "no_shelter", lang: "en", label: "Refuses shelter/agency referrals",
    pattern: String.raw`\bno\s+(?:shelter|agency|case\s*worker|caseworker)\s*(?:referrals?|clients?|placements?|tenants?|calls?)?\b` },
  { id: "no_handouts", lang: "en", label: "Derogatory coded language",
    pattern: String.raw`\bno\s+(?:handouts|freeloaders|government\s+cheese)\b` },
  // Spanish
  { id: "es_no_programas", lang: "es", label: "Refuses programs/vouchers (Spanish)",
    pattern: String.raw`\bno\s+(?:se\s+)?(?:acepta(?:n|mos)?|recibimos|tomamos)\s+(?:\w+\s+)?(?:programas?|vouchers?|cupones|secci[oó]n\s*8|ayuda\s+del\s+gobierno|asistencia)` +
      String.raw`|\bno\s+(?:programas?|vouchers?|secci[oó]n\s*8)\b` },
  // Chinese
  { id: "zh_no_programs", lang: "zh", label: "Refuses government assistance (Chinese)",
    pattern: String.raw`不(?:接受|收|要|租给)\s*(?:任何)?\s*(?:政府)?\s*(?:program|programs|補助|补助|福利|八號|八号|第八|section\s*8|voucher|住房券)` +
      String.raw`|(?:program|補助|补助|福利)\s*(?:勿扰|免问|不收|不要)` },
  // Russian
  { id: "ru_no_programs", lang: "ru", label: "Refuses programs/vouchers (Russian)",
    pattern: String.raw`без\s+(?:программ|ваучеров|субсидий|section\s*8)|(?:программ[ыу]?|ваучер[ыа]?|section\s*8)\s+не\s+(?:принимаем|берем|берём|рассматриваем)` },
  // Bengali
  { id: "bn_no_programs", lang: "bn", label: "Refuses programs/vouchers (Bengali)",
    pattern: String.raw`(?:ভাউচার|প্রোগ্রাম|সরকারি\s*সাহায্য)\s*(?:নেওয়া\s*হয়\s*না|নেই|চলবে\s*না|গ্রহণযোগ্য\s*নয়)|কোন\s*(?:ভাউচার|প্রোগ্রাম)\s*না` },
];

// Welcoming language. Discounts R2/R3 (soft signals). Never cancels R1:
// "Section 8 welcome, no CityFHEPS" is still a violation.
export const WELCOME = [
  String.raw`\b(?:all\s+)?${PROGRAMS}\s+(?:tenants?\s+|holders?\s+|participants?\s+)?(?:are\s+|is\s+)?(?:welcome[d]?|accepted|ok(?:ay)?|considered|encouraged|fine)\b`,
  String.raw`\b(?:we\s+)?(?:gladly\s+)?(?:accept(?:s|ing)?|take[s]?|welcome[s]?|work\s+with)\s+(?:all\s+)?(?:\w+\s+){0,2}?${PROGRAMS}\b`,
  String.raw`\bse\s+aceptan\s+(?:\w+\s+){0,2}?(?:programas|vouchers|secci[oó]n\s*8)|\bprogramas\s+bienvenidos`,
  String.raw`(?:接受|欢迎|歡迎)\s*(?:政府)?\s*(?:program|補助|补助|八号|八號|住房券)`,
];

// R2 carve-outs: the listing applies income rules only to the tenant share,
// or counts the subsidy as income. These make an income requirement lawful.
export const INCOME_CARVE_OUT = [
  String.raw`\b(?:tenant'?s?|your)\s+(?:portion|share)\b`,
  String.raw`\bincome\s+(?:requirements?|restrictions?)\s+(?:is\s+|are\s+)?(?:waived|do(?:es)?\s+not\s+apply|adjusted)`,
  String.raw`\b(?:rental\s+assistance|vouchers?|subsid(?:y|ies))\s+counts?\s+(?:toward|towards|as)\s+income`,
  String.raw`\bor\s+(?:rental\s+assistance|a\s+voucher|vouchers?)\b`,
];

// Government-set income bands (lotteries, Mitchell-Lama) are lawful.
export const GOV_INCOME_BAND = String.raw`\b(?:housing\s+connect|hpd\s+lottery|affordable\s+housing\s+lottery|%\s*ami\b|ami\b|area\s+median\s+income|hdfc|lihtc|mitchell[\s-]*lama)`;

// R3: other screening barriers.
export const EMPLOYMENT = [
  String.raw`\b(?:working\s+professionals?|employed\s+(?:applicants?|tenants?|persons?)|w-?2\s+(?:employees?|income))\s+only\b`,
  String.raw`\bmust\s+(?:be\s+(?:currently\s+)?employed|have\s+(?:a\s+)?(?:full[\s-]*time\s+)?job)\b`,
  String.raw`\b(?:only|will\s+only)\s+(?:rents?\s+to\s+|consider\s+)?(?:working\s+professionals?|employed\s+applicants?|tenants?\s+with\s+jobs)\b`,
  String.raw`\bincome\s+must\s+(?:be|come)\s+from\s+(?:employment|a\s+job|wages)\b`,
  String.raw`\bproof\s+of\s+employment\s+income\b`,
  String.raw`\bpay\s*stubs?\s+(?:required|needed|a\s+must)\b|\bmust\s+(?:have|show)\s+pay\s*stubs?\b`,
  String.raw`\bs[oó]lo\s+(?:personas\s+)?(?:que\s+trabajen|trabajadores|con\s+empleo)\b`,
];
