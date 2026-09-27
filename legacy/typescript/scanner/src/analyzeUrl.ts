// URL -> verdict in one call, for the iMessage agent ("here's a link, is this legal?").
import { analyze } from "../../core/src/analyze.ts";
import type { AnalysisResult } from "../../core/src/schema.ts";
import { fetchListing, type FetchedListing } from "./fetchListing.ts";

export async function analyzeUrl(url: string, hints?: { bedrooms?: number; monthly_rent?: number }): Promise<{ result: AnalysisResult; fetched: FetchedListing }> {
  const fetched = await fetchListing(url);
  const result = await analyze({
    text: fetched.text,
    url: fetched.url,
    // The screenshot lets Gemini read listing text that lives inside images (flyers, photo captions).
    image: fetched.screenshotB64 ? { base64: fetched.screenshotB64, mimeType: fetched.screenshotMediaType ?? "image/jpeg" } : undefined,
    hints,
  });
  result.notes.push(fetched.via === "jev"
    ? `Page read by jev browser agent in ${fetched.elapsedMs} ms (${fetched.steps?.length ?? 0} actions${fetched.stopped?.startsWith("guardrail") ? `; stopped by ${fetched.stopped}` : ""}).`
    : `Page read with a plain HTTP fetch${fetched.jevError ? ` (jev unavailable: ${fetched.jevError})` : ""}. Content loaded by JavaScript may be missing.`);
  return { result, fetched };
}
