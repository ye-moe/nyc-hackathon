// Precision / recall / confusion matrix, overall and per rule.
//
//   bun run eval/run.ts                    # dev set, offline regex extractor
//   bun run eval/run.ts --holdout          # held-out set: the number for the pitch
//   bun run eval/run.ts --gemini           # use Gemini extraction (needs GEMINI_API_KEY)
//   bun run eval/run.ts --file data/labeled/real.jsonl -v
//
// Labeled rows: {id, text, label: violation|needs_review|no_issue_found, hints?, verified_by}

import { analyze } from "../core/src/analyze.ts";
import type { RuleId, Verdict } from "../core/src/schema.ts";

const args = process.argv.slice(2);
const flag = (n: string) => args.includes(n);
const fileArg = args.indexOf("--file");
const path = fileArg >= 0 ? args[fileArg + 1] : `data/labeled/${flag("--holdout") ? "holdout" : "dev"}.jsonl`;
const verbose = flag("-v");
const useGemini = flag("--gemini");

type Row = { id: string; text: string; label: Verdict; hints?: any; verified_by?: string | null };
const rows: Row[] = (await Bun.file(path).text()).trim().split("\n").filter(Boolean).map((l) => JSON.parse(l));

const LABELS: Verdict[] = ["violation", "needs_review", "no_issue_found"];
const matrix: Record<string, Record<string, number>> = Object.fromEntries(LABELS.map((g) => [g, Object.fromEntries(LABELS.map((p) => [p, 0]))]));
const perRule: Record<RuleId, { tp: number; fp: number }> = { R1: { tp: 0, fp: 0 }, R2: { tp: 0, fp: 0 }, R3: { tp: 0, fp: 0 }, R4: { tp: 0, fp: 0 } };
const misses: string[] = [];

for (const row of rows) {
  const r = await analyze({ id: row.id, text: row.text, hints: row.hints }, { useGemini });
  matrix[row.label][r.verdict]++;
  // A rule "fires" when it raised a review or violation. It's correct if the gold label isn't no_issue_found.
  const fired = new Set(r.flags.filter((f) => f.severity !== "info").map((f) => f.rule_id));
  for (const id of fired) perRule[id][row.label === "no_issue_found" ? "fp" : "tp"]++;
  if (r.verdict !== row.label) {
    misses.push(`  ${row.id}  gold=${row.label.padEnd(14)} got=${r.verdict.padEnd(14)} ${row.text.slice(0, 70)}`);
    if (verbose) r.flags.forEach((f) => misses.push(`        ${f.rule_id} ${f.code} (${f.severity}): "${f.evidence_text}"`));
  }
}

const g = (gold: Verdict, pred: Verdict) => matrix[gold][pred];
const pct = (n: number, d: number) => (d ? ((100 * n) / d).toFixed(1) + "%" : "n/a");
// Headline: a "violation" verdict is what produces an evidence packet, so its precision is the number we protect.
const vTP = g("violation", "violation");
const vPred = LABELS.reduce((s, l) => s + g(l, "violation"), 0);
const vGold = LABELS.reduce((s, l) => s + g("violation", l), 0);
const flaggedAny = (l: Verdict) => g(l, "violation") + g(l, "needs_review");
const cleanGold = LABELS.reduce((s, l) => s + g("no_issue_found", l), 0);
const unverified = rows.filter((r) => !r.verified_by).length;

console.log(`\n${path}  n=${rows.length}  extractor=${useGemini ? "gemini" : "regex (offline)"}`);
console.log("─".repeat(64));
console.log(`violation precision   ${pct(vTP, vPred).padStart(7)}   (${vTP}/${vPred})  <- protect this`);
console.log(`violation recall      ${pct(vTP, vGold).padStart(7)}   (${vTP}/${vGold})`);
console.log(`caught (viol+review)  ${pct(flaggedAny("violation"), vGold).padStart(7)}   unlawful listings that reach a human`);
console.log(`false alarms          ${pct(flaggedAny("no_issue_found"), cleanGold).padStart(7)}   lawful listings flagged at all`);
console.log(`exact-label accuracy  ${pct(LABELS.reduce((s, l) => s + g(l, l), 0), rows.length).padStart(7)}`);

console.log(`\nconfusion matrix (rows = gold, cols = predicted)`);
console.log("".padEnd(16) + LABELS.map((l) => l.padStart(16)).join(""));
for (const gl of LABELS) console.log(gl.padEnd(16) + LABELS.map((p) => String(g(gl, p)).padStart(16)).join(""));

console.log(`\nper rule (fired = raised review or violation)`);
for (const [id, c] of Object.entries(perRule)) {
  if (id === "R4") continue; // informational only
  console.log(`  ${id}  fired ${String(c.tp + c.fp).padStart(3)}   precision ${pct(c.tp, c.tp + c.fp).padStart(7)}   (${c.fp} on lawful listings)`);
}
if (misses.length) console.log(`\nmismatches\n${misses.join("\n")}`);
if (unverified) console.log(`\n⚠ ${unverified}/${rows.length} labels have no verified_by. Have a person check each one before quoting these numbers.`);
