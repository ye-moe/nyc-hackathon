// Offline extractor. Fills the same Extraction schema as Gemini using regexes,
// so the rules engine, eval, and demo all work with no network or API key.
// Also the fallback when Gemini times out.

import { EXCLUSIONS, EMPLOYMENT } from "../../config/phrases.ts";
import type { Extraction } from "./schema.ts";

const re = (s: string, f = "i") => new RegExp(s, f);

const MONEY = String.raw`\$\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?\s?k|\d{3,6})`;

export function money(s: string): number {
  const t = s.toLowerCase().replace(/[,\s$]/g, "");
  return t.endsWith("k") ? parseFloat(t) * 1000 : parseFloat(t);
}

export function detectLanguage(text: string): string {
  if (/[一-鿿]/.test(text)) return "zh";
  if (/[Ѐ-ӿ]/.test(text)) return "ru";
  if (/[ঀ-৿]/.test(text)) return "bn";
  if (/[؀-ۿ]/.test(text)) return "ar";
  const words = new Set(text.toLowerCase().match(/[a-záéíóúñ]+/g) ?? []);
  const es = ["el", "la", "los", "las", "de", "apartamento", "cuarto", "habitación", "renta", "alquiler", "se", "con", "para", "y", "al", "mes"];
  const en = ["the", "and", "with", "for", "apartment", "rent", "bedroom", "is", "to", "of", "in"];
  const n = (ws: string[]) => ws.filter((w) => words.has(w)).length;
  return n(es) > n(en) + 1 ? "es" : "en";
}

export function regexExtract(text: string): Extraction {
  const ex: Extraction = {
    explicit_exclusions: [],
    source_language: detectLanguage(text),
    confidence: 0.7,
  };

  // Rent: "$2,200/mo", "$2,200 per month", "月租2600", or a bare "$2,300." in a short listing.
  const rent =
    text.match(re(MONEY + String.raw`\s*(?:/\s*mo(?:nth)?|per\s+month|a\s+month|monthly|al\s+mes)`)) ??
    text.match(/月租\s*\$?(\d{3,5})/) ??
    text.match(re(String.raw`(?:rent|renta)\s*:?\s*` + MONEY)) ??
    text.match(re(String.raw`(?:^|[\s,(])` + MONEY + String.raw`(?=[\s.,)]|$)`));
  if (rent) {
    const v = money(rent[1]);
    if (v >= 400 && v <= 30000) ex.monthly_rent = v;
  }

  const br = text.match(/\b(\d)\s*(?:br|bd|bed(?:room)?s?|-bed|\s+bed)\b/i) ??
    text.match(/(\d)\s*(?:cuartos?|habitaciones?|комнатн|室|房)/i);
  if (br) ex.bedrooms = Number(br[1]);
  else if (/\bstudio\b|estudio|单间|一房/i.test(text)) ex.bedrooms = /一房/.test(text) ? 1 : 0;
  else if (/\bone[\s-]bed(?:room)?\b/i.test(text)) ex.bedrooms = 1;
  else if (/\btwo[\s-]bed(?:room)?\b/i.test(text)) ex.bedrooms = 2;

  const addr = text.match(/\b\d{1,5}\s+(?:(?:[NSEW]\.?|North|South|East|West)\s+)?(?:\d{1,3}(?:st|nd|rd|th)|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:St|Street|Ave|Avenue|Blvd|Boulevard|Rd|Road|Pl|Place|Pkwy|Parkway|Dr|Drive|Ct|Court|Ln|Lane|Ter|Terrace)\b\.?/);
  if (addr) ex.address = addr[0].replace(/\.$/, "");

  const boro = text.match(/\b(Bronx|Brooklyn|Manhattan|Queens|Staten Island)\b/i);
  if (boro) ex.borough = boro[1];
  const zip = text.match(/\b(1[01]\d{3})\b/);
  if (zip) ex.zip = zip[1];

  // Income requirement. Order matters: "3x rent in monthly income" before "40x rent".
  const monthlyMult = text.match(
    /\b([2-4](?:\.\d)?)\s*(?:x|×|times)\s*(?:the\s+)?(?:monthly\s+)?rent\s+(?:per|a|each|every|in)\s+(?:month|monthly)|\bmonthly\s+income\s+(?:of\s+)?(?:at\s+least\s+)?([2-4](?:\.\d)?)\s*(?:x|×|times)/i,
  );
  const mult = text.match(
    /\b(\d{1,3}(?:\.\d)?)\s*(?:x|×|times)\s*(?:the\s+)?(?:monthly\s+|annual\s+)?(?:rent|rental)\b|\b(?:earn|income\s+of|make|salary\s+of)\s+(?:at\s+least\s+)?(\d{1,3})\s*(?:x|×|times)/i,
  );
  const annual = text.match(re(String.raw`(?:income|salary|earn(?:ings)?|make)[^$\n]{0,30}` + MONEY));
  if (monthlyMult) {
    ex.income_requirement = { type: "monthly", value: Number(monthlyMult[1] ?? monthlyMult[2]), raw_text: monthlyMult[0] };
  } else if (mult) {
    ex.income_requirement = { type: "multiplier", value: Number(mult[1] ?? mult[2]), raw_text: mult[0] };
  } else if (annual) {
    const v = money(annual[1]);
    if (v >= 10000) ex.income_requirement = { type: "annual", value: v, raw_text: annual[0] };
  }

  const phone = text.match(/(?:\+?1[\s.-]?)?\(?\b(\d{3})\)?[\s.-]?(\d{3})[\s.-]?(\d{4})\b/);
  if (phone) ex.contact_phone = `(${phone[1]}) ${phone[2]}-${phone[3]}`;
  const name = text.match(/\b(?:[Cc]all|[Tt]ext|[Cc]ontact|[Aa]sk\s+for)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)(?=[\s,.!:]|$)/);
  if (name) ex.broker_or_landlord_name = name[1];

  const credit = text.match(/\b(?:min(?:imum)?\.?\s+)?credit\s*(?:score)?\s*(?:of\s+)?(\d{3})\s*\+?|\b(\d{3})\+?\s*credit\b/i);
  if (credit) {
    const v = Number(credit[1] ?? credit[2]);
    if (v >= 300 && v <= 850) ex.credit_score_min = { value: v, raw_text: credit[0] };
  }

  for (const p of EMPLOYMENT) {
    const m = text.match(re(p));
    if (m) { ex.employment_requirement = { raw_text: m[0] }; break; }
  }

  for (const p of EXCLUSIONS) {
    for (const m of text.matchAll(re(p.pattern, "gi"))) {
      ex.explicit_exclusions.push({ phrase: p.label, raw_text: m[0] });
    }
  }
  return ex;
}
