// bun run demo            -> terminal walkthrough, writes one packet to data/cache/demo-packet.html
import { analyze } from "./src/analyze.ts";
import { buildPacket } from "./src/packet.ts";

const C = { red: "\x1b[91m", yel: "\x1b[93m", grn: "\x1b[92m", dim: "\x1b[2m", b: "\x1b[1m", x: "\x1b[0m" };
const color = { violation: C.red, needs_review: C.yel, no_issue_found: C.grn };

const listings = [
  "Sunny 1BR in Crown Heights, $2,200/mo. Must earn 40x the rent. No pets.",
  "Section 8 welcome! Sorry, no CityFHEPS. 2BR $2,500.",
  "Apartamento de 2 cuartos en Washington Heights. No aceptamos programas. $2,400 al mes.",
  "Spacious 2BR in Astoria, $2,600. No broker fee! No pets. No smoking.",
  "3BR Canarsie $3,200. 40x rent income required. Vouchers accepted, income requirement applies to tenant portion only.",
  "Quiet building, working professionals only. 1BR $2,250.",
];

for (const text of listings) {
  const r = await analyze({ text });
  console.log(`\n${color[r.verdict]}${C.b}${r.verdict.toUpperCase()}${C.x}  ${C.dim}(${r.extractor})${C.x}\n  ${text}`);
  for (const f of r.flags.filter((f) => f.severity !== "info")) {
    console.log(`  ${C.b}${f.rule_id}${C.x} "${f.evidence_text}": ${C.dim}${f.explanation}${C.x}`);
    f.calculation?.steps.forEach((s, i) => console.log(`     ${i + 1}. ${s}`));
  }
}

const r = await analyze({ text: listings[0] + " No programs." });
const p = await buildPacket(r, { tenantLanguage: "es" });
await Bun.write("data/cache/demo-packet.html", p.html);
console.log(`\n${C.b}iMessage reply:${C.x}\n${p.summaryText}`);
console.log(`\npacket -> data/cache/demo-packet.html ${p.translated ? "(EN + ES)" : "(English only; set GEMINI_API_KEY for translation)"}`);

// ---- complaint draft (for a person to review; nothing is sent) ----
import { draftComplaint } from "./src/complaint.ts";
const listing = "Sunny 1BR at 512 Halsey St, Brooklyn 11233. $2,200/mo. Must earn 40x the rent. No programs. Call Dave (718) 555-0142.";
const draft = await draftComplaint({
  result: await analyze({ text: listing }),
  listing: { source: "Craigslist", url: "https://newyork.craigslist.org/example", screenshotSaved: true },
  reporter: { role: "caseworker" },
  tenantLanguage: "es",
});
await Bun.write("data/cache/demo-complaint.html", draft.html);
await Bun.write("data/cache/demo-complaint.txt", draft.text);
console.log(`\ncomplaint draft -> data/cache/demo-complaint.html (+ .txt)`);
