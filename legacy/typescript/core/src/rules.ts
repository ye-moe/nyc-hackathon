// Deterministic rules engine. No LLM calls in this file: same input, same flags.

import { cityfheps } from "../../config/cityfheps.ts";
import { EXCLUSIONS, GOV_INCOME_BAND, INCOME_CARVE_OUT, WELCOME } from "../../config/phrases.ts";
import { thresholds } from "../../config/thresholds.ts";
import type { Calculation, Extraction, Flag, Verdict } from "./schema.ts";

const any = (patterns: string[], text: string) => patterns.some((p) => new RegExp(p, "i").test(text));
const usd = (n: number) => "$" + Math.round(n).toLocaleString("en-US");
const norm = (s: string) => s.toLowerCase().replace(/\s+/g, " ").trim();

function spanOf(haystack: string, needle: string): [number, number] | undefined {
  const i = haystack.toLowerCase().indexOf(needle.toLowerCase());
  return i >= 0 ? [i, i + needle.length] : undefined;
}

// ---------- R1: explicit exclusions ----------
export function r1(ex: Extraction, text: string): Flag[] {
  const flags: Flag[] = [];
  const seen = new Set<string>();
  for (const p of EXCLUSIONS) {
    for (const m of text.matchAll(new RegExp(p.pattern, "gi"))) {
      if (seen.has(norm(m[0]))) continue;
      seen.add(norm(m[0]));
      flags.push({
        rule_id: "R1", code: p.id, severity: "violation", evidence_text: m[0],
        span: [m.index!, m.index! + m[0].length],
        explanation: `${p.label}. Refusing a tenant because rent is paid by a voucher is source-of-income discrimination.`,
      });
    }
  }
  // Exclusions the extractor found that our phrase list missed (paraphrases,
  // other languages, text inside images). Only counted if the quote is really
  // in the listing; otherwise the model may have invented it.
  for (const e of ex.explicit_exclusions) {
    if (seen.has(norm(e.raw_text)) || [...seen].some((s) => norm(e.raw_text).includes(s) || s.includes(norm(e.raw_text)))) continue;
    const span = spanOf(text, e.raw_text);
    if (!span) continue;
    seen.add(norm(e.raw_text));
    flags.push({
      rule_id: "R1", code: "extracted_exclusion", severity: "review", evidence_text: e.raw_text, span,
      explanation: `Possible refusal of voucher holders ("${e.phrase}"). Not in our phrase list, so a person should confirm.`,
    });
  }
  return flags;
}

// ---------- R2: income requirement applied to full rent ----------
export function annualRequired(ex: Extraction, rent?: number): number | undefined {
  const ir = ex.income_requirement;
  if (!ir) return undefined;
  if (ir.type === "annual") return ir.value;
  if (!rent) return undefined;
  if (ir.type === "monthly") return ir.value * rent * 12;
  return ir.value < thresholds.monthlyMultiplierMax ? ir.value * 12 * rent : ir.value * rent;
}

export function r2(ex: Extraction, text: string, withinRange?: boolean): Flag[] {
  const ir = ex.income_requirement;
  if (!ir) return [];
  const rent = ex.monthly_rent;
  const hh = cityfheps.exampleHousehold;
  const span = spanOf(text, ir.raw_text);
  const base = { rule_id: "R2" as const, evidence_text: ir.raw_text, span };

  if (new RegExp(GOV_INCOME_BAND, "i").test(text)) {
    return [{ ...base, code: "income_gov_band", severity: "info",
      explanation: "Income limits look government-set (affordable housing lottery / AMI band). That is lawful." }];
  }
  if (any(INCOME_CARVE_OUT, text) || any(WELCOME, text)) {
    return [{ ...base, code: "income_carve_out", severity: "info",
      explanation: "The listing accepts vouchers or applies the income requirement only to the tenant's share. That is lawful." }];
  }

  const required = annualRequired(ex, rent);
  const steps: string[] = [];
  const calc: Calculation = { steps, example_household_income: hh.annualIncome };

  if (required === undefined) {
    steps.push(`The listing requires "${ir.raw_text}" but the rent isn't stated, so the dollar amount can't be computed.`);
    return [{ ...base, code: "income_rent_unknown", severity: "review", calculation: calc,
      explanation: "Income requirement found, but without the rent we can't show it excludes voucher holders." }];
  }

  // The multiplier in annual terms (40x rent -> 40; 3x monthly -> 36).
  const annualMult = rent ? required / rent : undefined;
  const tenantShare = (cityfheps.tenantShareOfIncome * hh.annualIncome) / 12;
  const lawful = annualMult ? annualMult * tenantShare : undefined;

  if (rent && annualMult) {
    steps.push(`Rent is ${usd(rent)}/month. The listing requires ${annualMult}× rent: ${annualMult} × ${usd(rent)} = ${usd(required)}/year.`);
    steps.push(`A CityFHEPS tenant pays ${cityfheps.tenantShareOfIncome * 100}% of income. Example household (${hh.size} people, ${usd(hh.annualIncome)}/year): ` +
      `${cityfheps.tenantShareOfIncome * 100}% × ${usd(hh.annualIncome)} ÷ 12 = ${usd(tenantShare)}/month. The voucher pays the other ${usd(rent - tenantShare)}.`);
    steps.push(`Applied lawfully to the tenant's share: ${annualMult} × ${usd(tenantShare)} = ${usd(lawful!)}/year. ` +
      (hh.annualIncome >= lawful! ? "The household qualifies." : "The household would still fall short."));
    steps.push(`Applied to the full rent: ${usd(required)}/year required vs. ${usd(hh.annualIncome)} earned. The household is rejected.`);
  } else {
    steps.push(`The listing requires ${usd(required)}/year in income.`);
  }
  const excludesAll = required > cityfheps.incomeCeiling;
  if (excludesAll) {
    steps.push(`${usd(required)} is more than any CityFHEPS-eligible household can earn (about ${usd(cityfheps.incomeCeiling)}/year), ` +
      `so this requirement excludes every voucher holder.`);
  }
  Object.assign(calc, { required_annual_income: Math.round(required), lawful_annual_income: lawful && Math.round(lawful), excludes_every_eligible_household: excludesAll });

  if (withinRange === false) {
    return [{ ...base, code: "income_rent_above_standard", severity: "review", calculation: calc,
      explanation: "Income requirement is applied to full rent, but the rent is above the CityFHEPS payment standard, so a voucher may not cover this unit anyway." }];
  }
  if (required <= hh.annualIncome) return [];
  return [{ ...base, code: "income_full_rent", severity: "violation", calculation: calc,
    explanation: "The income requirement is applied to the full rent instead of the tenant's share, which screens out voucher holders." }];
}

// ---------- R3: other screening barriers ----------
export function r3(ex: Extraction, text: string): Flag[] {
  if (any(WELCOME, text)) return [];
  const flags: Flag[] = [];
  if (ex.employment_requirement) {
    const t = ex.employment_requirement.raw_text;
    flags.push({ rule_id: "R3", code: "employment_requirement", evidence_text: t, span: spanOf(text, t),
      severity: thresholds.employmentIsViolation ? "violation" : "review",
      explanation: "Requiring employment or wage income excludes voucher holders, whose rent is paid by a subsidy and who aren't required to work." });
  }
  const c = ex.credit_score_min;
  if (c && c.value >= thresholds.creditScoreReviewAt) {
    flags.push({ rule_id: "R3", code: "credit_minimum", evidence_text: c.raw_text, span: spanOf(text, c.raw_text), severity: "review",
      explanation: `A ${c.value}+ credit minimum can screen out voucher holders. CCHR guidance limits how credit may be used against them.` });
  }
  return flags;
}

// ---------- R4: is the rent within CityFHEPS payment standards? ----------
export function r4(ex: Extraction): { flag?: Flag; within?: boolean } {
  const rent = ex.monthly_rent, br = ex.bedrooms;
  if (rent === undefined || br === undefined) return {};
  const standard = cityfheps.paymentStandard[Math.min(Math.max(Math.round(br), 0), 4)];
  const within = rent <= standard * cityfheps.paymentStandardSlack;
  return {
    within,
    flag: { rule_id: "R4", code: within ? "within_voucher_range" : "above_voucher_range", severity: "info", evidence_text: `${usd(rent)}/month, ${br}BR`,
      explanation: within
        ? `Rent is within the CityFHEPS payment standard for a ${br}-bedroom (${usd(standard)}). A voucher holder could afford this unit.`
        : `Rent is above the CityFHEPS payment standard for a ${br}-bedroom (${usd(standard)}).` },
  };
}

export function runRules(ex: Extraction, text: string): { flags: Flag[]; verdict: Verdict; within?: boolean; notes: string[] } {
  const notes: string[] = [];
  const { flag: r4flag, within } = r4(ex);
  let flags = [...r1(ex, text), ...r2(ex, text, within), ...r3(ex, text)];
  if (ex.confidence < thresholds.minExtractionConfidence && flags.some((f) => f.severity === "violation")) {
    flags = flags.map((f) => (f.severity === "violation" ? { ...f, severity: "review" } : f));
    notes.push("Extraction confidence is low, so violations were downgraded to review.");
  }
  if (r4flag) flags.push(r4flag);
  const verdict: Verdict = flags.some((f) => f.severity === "violation") ? "violation"
    : flags.some((f) => f.severity === "review") ? "needs_review" : "no_issue_found";
  return { flags, verdict, within, notes };
}
