import { z } from "zod";

// What Gemini (or the offline regex extractor) pulls out of a listing.
// Extraction only: nothing in here decides legality.
export const Extraction = z.object({
  address: z.string().optional(),
  borough: z.string().optional(),
  zip: z.string().optional(),
  monthly_rent: z.number().optional(),
  bedrooms: z.number().optional(),
  income_requirement: z
    .object({
      type: z.enum(["multiplier", "annual", "monthly"]),
      value: z.number(),
      raw_text: z.string(),
    })
    .optional(),
  credit_score_min: z.object({ value: z.number(), raw_text: z.string() }).optional(),
  employment_requirement: z.object({ raw_text: z.string() }).optional(),
  explicit_exclusions: z.array(z.object({ phrase: z.string(), raw_text: z.string() })),
  source_language: z.string(),
  broker_or_landlord_name: z.string().optional(),
  contact_phone: z.string().optional(),
  confidence: z.number().min(0).max(1),
  // Not in the original spec: the listing text as read from an image, and an
  // English rendering. The rules engine runs its phrase lists over both.
  transcribed_text: z.string().optional(),
  english_text: z.string().optional(),
});
export type Extraction = z.infer<typeof Extraction>;

export type Severity = "violation" | "review" | "info";
export type Verdict = "violation" | "needs_review" | "no_issue_found";
export type RuleId = "R1" | "R2" | "R3" | "R4";

export type Calculation = {
  steps: string[];                 // human-readable, one arithmetic step per line
  required_annual_income?: number; // what the listing demands (full rent)
  lawful_annual_income?: number;   // what it could demand (tenant share only)
  example_household_income: number;
  excludes_every_eligible_household?: boolean;
};

export type Flag = {
  rule_id: RuleId;
  code: string;                    // finer-grained id, e.g. "no_programs", "income_full_rent"
  severity: Severity;
  evidence_text: string;           // the clause, verbatim
  span?: [number, number];         // offsets into the analyzed text, when found
  explanation: string;
  calculation?: Calculation;
};

export type ListingInput = {
  id?: string;
  text?: string;
  url?: string;
  image?: { base64: string; mimeType: string };
  // Context from the conversation (e.g. a caseworker said "family of 3, 2BR").
  hints?: { bedrooms?: number; monthly_rent?: number; household_size?: number };
};

export type AnalysisResult = {
  id: string;
  verdict: Verdict;
  flags: Flag[];
  extraction: Extraction;
  extractor: "gemini" | "regex";
  analyzed_text: string;
  within_voucher_range?: boolean;  // R4
  notes: string[];                 // e.g. "Gemini unavailable; used offline extractor"
  analyzed_at: string;
};
