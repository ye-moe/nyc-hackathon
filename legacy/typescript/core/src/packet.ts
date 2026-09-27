// Evidence packet: what a tenant or caseworker takes away. Never auto-filed;
// a person decides what to do with it.

import { legal } from "../../config/cityfheps.ts";
import { geminiTranslate } from "./gemini.ts";
import type { AnalysisResult, Flag, Verdict } from "./schema.ts";

export const SUPPORTED_LANGUAGES: Record<string, string> = {
  en: "English", es: "Español", bn: "বাংলা", zh: "中文", ru: "Русский",
};

const HEADLINE: Record<Verdict, string> = {
  violation: "This listing likely breaks NYC law by excluding voucher holders.",
  needs_review: "This listing has terms that may exclude voucher holders. A person should take a closer look.",
  no_issue_found: "We didn't find anything in this listing that excludes voucher holders.",
};

export type Packet = {
  summaryText: string;         // iMessage-friendly
  html: string;                // self-contained shareable page
  language: string;            // second language used, "en" if none
  translated: boolean;
};

const problems = (r: AnalysisResult) => r.flags.filter((f) => f.severity !== "info");

export async function buildPacket(
  r: AnalysisResult,
  opts: { tenantLanguage?: string; packetUrl?: string; listingUrl?: string } = {},
): Promise<Packet> {
  const lang = opts.tenantLanguage ?? (r.extraction.source_language in SUPPORTED_LANGUAGES ? r.extraction.source_language : "en");
  const flags = problems(r);
  const calc = flags.find((f) => f.calculation)?.calculation;

  // Everything a tenant needs to read, in order, so one translation call covers it.
  const english = [
    HEADLINE[r.verdict],
    ...flags.map((f) => f.explanation),
    ...(calc?.steps ?? []),
    legal.summary,
    legal.incomeRule,
    ...legal.nextSteps,
  ];
  const translated = lang !== "en" ? await geminiTranslate(english, lang) : null;

  return {
    summaryText: summary(r, opts.packetUrl),
    html: html(r, english, translated, lang, opts.listingUrl),
    language: translated ? lang : "en",
    translated: Boolean(translated),
  };
}

function summary(r: AnalysisResult, packetUrl?: string): string {
  const lines = [HEADLINE[r.verdict]];
  for (const f of problems(r).slice(0, 3)) {
    lines.push(`• "${f.evidence_text}": ${f.explanation.split(". ")[0].replace(/\.$/, "")}.`);
  }
  const calc = problems(r).find((f) => f.calculation?.required_annual_income)?.calculation;
  if (calc) {
    lines.push("");
    lines.push(`The math: the listing asks for $${calc.required_annual_income!.toLocaleString()}/yr. ` +
      (calc.lawful_annual_income ? `Applied lawfully to the tenant's share, it's $${calc.lawful_annual_income.toLocaleString()}/yr.` : ""));
  }
  if (r.notes.length) lines.push("", ...r.notes);
  if (packetUrl) lines.push("", `Full evidence packet: ${packetUrl}`);
  if (r.verdict !== "no_issue_found") lines.push("This is information, not legal advice. You decide whether to report it.");
  return lines.join("\n");
}

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

function highlight(text: string, flags: Flag[]): string {
  const spans = flags.filter((f) => f.span).map((f) => f.span!).sort((a, b) => a[0] - b[0]);
  let out = "", i = 0;
  for (const [s, e] of spans) {
    if (s < i) continue;
    out += esc(text.slice(i, s)) + `<mark>${esc(text.slice(s, e))}</mark>`;
    i = e;
  }
  return out + esc(text.slice(i));
}

function html(r: AnalysisResult, en: string[], tr: string[] | null, lang: string, listingUrl?: string): string {
  const flags = problems(r);
  const calcFlag = flags.find((f) => f.calculation);
  const nSteps = calcFlag?.calculation?.steps.length ?? 0;
  // Index layout of `en` (and `tr`): headline, flag explanations, calc steps, law summary, income rule, next steps.
  const at = { head: 0, flags: 1, steps: 1 + flags.length, law: 1 + flags.length + nSteps };

  const column = (t: string[], code: string) => `
    <section lang="${code}">
      <h2 class="headline ${r.verdict}">${esc(t[at.head])}</h2>
      ${flags.length ? `<h3>${code === "en" ? "What we found" : "&nbsp;"}</h3><ul>${flags.map((f, i) =>
        `<li><q>${esc(f.evidence_text)}</q><br>${esc(t[at.flags + i])} <span class="rule">${f.rule_id}</span></li>`).join("")}</ul>` : ""}
      ${nSteps ? `<h3>${code === "en" ? "The math" : "&nbsp;"}</h3><ol>${t.slice(at.steps, at.steps + nSteps).map((s) => `<li>${esc(s)}</li>`).join("")}</ol>` : ""}
      <h3>${code === "en" ? "The law" : "&nbsp;"}</h3>
      <p>${esc(t[at.law])} <cite>${esc(legal.citation)}</cite></p>
      <p>${esc(t[at.law + 1])}</p>
      <h3>${code === "en" ? "What you can do" : "&nbsp;"}</h3>
      <ol>${t.slice(at.law + 2).map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
    </section>`;

  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Evidence packet</title>
<style>
:root{--bg:#fff;--fg:#111;--muted:#555;--line:#ddd;--bad:#b3261e;--warn:#8a5a00;--ok:#1e6b34;--mark:#ffe08a}
@media (prefers-color-scheme:dark){:root{--bg:#121212;--fg:#f2f2f2;--muted:#b5b5b5;--line:#333;--bad:#ff8a80;--warn:#ffcc66;--ok:#8fd19e;--mark:#6b5500}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:18px/1.55 system-ui,-apple-system,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 48px}
.cols{display:grid;gap:32px;grid-template-columns:1fr}@media(min-width:860px){.cols.two{grid-template-columns:1fr 1fr}}
h1{font-size:1.1rem;color:var(--muted);font-weight:600;margin:0 0 4px}h2{font-size:1.5rem;line-height:1.3}h3{margin:28px 0 8px;font-size:1.05rem}
.violation{color:var(--bad)}.needs_review{color:var(--warn)}.no_issue_found{color:var(--ok)}
q{font-weight:700}.rule{font-size:.8rem;color:var(--muted);border:1px solid var(--line);border-radius:4px;padding:0 4px}
li{margin:6px 0}cite{color:var(--muted);font-style:normal;font-size:.9rem}
.snapshot{white-space:pre-wrap;border:1px solid var(--line);border-radius:8px;padding:16px;font-size:.95rem}
mark{background:var(--mark);color:inherit;padding:0 2px}footer{margin-top:32px;color:var(--muted);font-size:.9rem}
</style></head><body><main>
<h1>Source-of-income evidence packet</h1>
<div class="cols ${tr ? "two" : ""}">${column(en, "en")}${tr ? column(tr, lang) : ""}</div>
<h3>Listing as analyzed</h3>
<div class="snapshot">${highlight(r.analyzed_text, r.flags)}</div>
<footer>
  ${listingUrl ? `Source: <a href="${esc(listingUrl)}">${esc(listingUrl)}</a><br>` : ""}
  Analyzed ${esc(new Date(r.analyzed_at).toLocaleString("en-US", { timeZone: "America/New_York" }))} ET · packet ${esc(r.id)} · extractor: ${r.extractor}
  ${r.notes.length ? `<br>${r.notes.map(esc).join("<br>")}` : ""}
  <br>Automated analysis. Not legal advice. Nothing has been filed; a person decides what to do next.
</footer>
</main></body></html>`;
}
