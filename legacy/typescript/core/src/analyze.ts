// The pipeline every caller uses: agent, scanner, web, eval.
//   input -> extraction (Gemini, or offline regex fallback) -> rules -> result

import { geminiAvailable, geminiExtract } from "./gemini.ts";
import { regexExtract } from "./regexExtract.ts";
import { runRules } from "./rules.ts";
import type { AnalysisResult, Extraction, ListingInput } from "./schema.ts";

export async function analyze(input: ListingInput, opts: { useGemini?: boolean } = {}): Promise<AnalysisResult> {
  const useGemini = (opts.useGemini ?? true) && geminiAvailable();
  const notes: string[] = [];
  let text = input.text ?? "";
  let extraction: Extraction;
  let extractor: AnalysisResult["extractor"] = "regex";

  if (useGemini) {
    try {
      const g = await geminiExtract({ text: input.text, image: input.image });
      // Phrase lists run over everything we can read: typed text, text read
      // from the image, and the English translation.
      text = [input.text, g.transcribed_text, g.english_text].filter(Boolean).join("\n");
      extraction = mergeWithRegex(g, regexExtract(text));
      extractor = "gemini";
    } catch (e) {
      notes.push(`Gemini unavailable (${(e as Error).message}); used the offline extractor.`);
      extraction = regexExtract(text);
    }
  } else {
    extraction = regexExtract(text);
  }

  if (input.image && extractor !== "gemini" && !input.text) {
    notes.push("Couldn't read the image. Try again, or paste the listing text.");
    extraction.confidence = 0;
  }
  const h = input.hints ?? {};
  extraction.bedrooms ??= h.bedrooms;
  extraction.monthly_rent ??= h.monthly_rent;

  const { flags, verdict, within, notes: ruleNotes } = runRules(extraction, text);
  return {
    id: input.id ?? crypto.randomUUID(),
    verdict: extraction.confidence === 0 ? "needs_review" : verdict,
    flags,
    extraction,
    extractor,
    analyzed_text: text,
    within_voucher_range: within,
    notes: [...notes, ...ruleNotes],
    analyzed_at: new Date().toISOString(),
  };
}

// Gemini wins on everything it found; regex fills gaps (Gemini sometimes skips
// a rent that's only in the title, for example).
function mergeWithRegex(g: Extraction, r: Extraction): Extraction {
  return {
    ...r,
    ...Object.fromEntries(Object.entries(g).filter(([, v]) => v !== undefined && v !== null)),
    explicit_exclusions: g.explicit_exclusions,
  } as Extraction;
}
