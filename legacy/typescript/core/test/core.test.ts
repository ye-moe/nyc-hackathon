import { describe, expect, test } from "bun:test";
import { analyze } from "../src/analyze.ts";
import { buildPacket } from "../src/packet.ts";

const run = (text: string, hints?: any) => analyze({ text, hints }, { useGemini: false });

describe("R1 explicit exclusions", () => {
  test("flags no programs, with the clause as evidence", async () => {
    const r = await run("Nice 1BR. NO VOUCHERS. Call now.");
    expect(r.verdict).toBe("violation");
    const f = r.flags.find((f) => f.rule_id === "R1")!;
    expect(r.analyzed_text.slice(...f.span!)).toBe("NO VOUCHERS");
  });
  test("lawful 'no' phrases are not refusals", async () => {
    expect((await run("No broker fee! No pets. No smoking.")).verdict).toBe("no_issue_found");
    expect((await run("No program fee for voucher holders.")).verdict).toBe("no_issue_found");
    expect((await run("No program needed to apply.")).verdict).toBe("no_issue_found");
  });
  test("welcoming one program doesn't excuse refusing another", async () => {
    expect((await run("Section 8 welcome! Sorry, no CityFHEPS.")).verdict).toBe("violation");
  });
  test("misspellings", async () => {
    expect((await run("no progams, no vouchars")).verdict).toBe("violation");
  });
  test("Spanish, Chinese, Russian", async () => {
    for (const t of ["No aceptamos programas.", "不接受政府补助", "Без программ."]) {
      expect((await run(t)).verdict).toBe("violation");
    }
  });
});

describe("R2 income requirement", () => {
  test("shows the math and flags full-rent application", async () => {
    const r = await run("1BR $2,200/mo. Must earn 40x the rent.");
    const f = r.flags.find((f) => f.rule_id === "R2")!;
    expect(f.severity).toBe("violation");
    expect(f.calculation!.required_annual_income).toBe(88000);
    expect(f.calculation!.lawful_annual_income).toBe(24000);
    expect(f.calculation!.excludes_every_eligible_household).toBe(true);
    expect(f.calculation!.steps.join(" ")).toContain("40 × $2,200 = $88,000");
  });
  test("3x monthly converts to annual", async () => {
    const r = await run("Studio $2,000/month. Applicants need 3x rent in monthly income.");
    expect(r.flags.find((f) => f.rule_id === "R2")!.calculation!.required_annual_income).toBe(72000);
  });
  test("tenant-share carve-out is lawful", async () => {
    expect((await run("40x rent. Vouchers accepted; income requirement applies to tenant portion only.", { monthly_rent: 2300, bedrooms: 1 })).verdict).toBe("no_issue_found");
  });
  test("government income bands are lawful", async () => {
    expect((await run("Housing Connect lottery, 60% AMI, income between $45,000 and $78,000", { monthly_rent: 1650, bedrooms: 1 })).verdict).toBe("no_issue_found");
  });
  test("rent above payment standard -> review, not violation", async () => {
    expect((await run("Luxury 2BR, $9,500/mo, 40x rent income required.")).verdict).toBe("needs_review");
  });
  test("unknown rent -> review", async () => {
    expect((await run("Must earn 40x the rent.")).verdict).toBe("needs_review");
  });
});

describe("R3 / R4", () => {
  test("employment requirement is review by default", async () => {
    expect((await run("Working professionals only.")).verdict).toBe("needs_review");
  });
  test("R4 reports voucher range without flagging", async () => {
    const r = await run("Sunny 2BR, $2,500/mo. Contact for showing.");
    expect(r.verdict).toBe("no_issue_found");
    expect(r.within_voucher_range).toBe(true);
  });
});

describe("graceful handling", () => {
  test("unreadable image without Gemini -> needs_review with a retry note", async () => {
    const r = await analyze({ image: { base64: "AAAA", mimeType: "image/png" } }, { useGemini: false });
    expect(r.verdict).toBe("needs_review");
    expect(r.notes.join(" ")).toContain("Couldn't read the image");
  });
});

describe("packet", () => {
  test("summary and html carry clause, math, law, next steps", async () => {
    const r = await run("1BR $2,200/mo. Must earn 40x the rent. No programs.");
    const p = await buildPacket(r, { packetUrl: "https://example.org/p/1" });
    expect(p.summaryText).toContain("No programs");
    expect(p.summaryText).toContain("$88,000");
    expect(p.summaryText).toContain("https://example.org/p/1");
    expect(p.html).toContain("<mark>No programs</mark>");
    expect(p.html).toContain("8-107(5)(a)");
    expect(p.html).toContain("311");
  });
  test("html escapes listing text", async () => {
    const p = await buildPacket(await run("<script>alert(1)</script> no programs"));
    expect(p.html).not.toContain("<script>alert");
  });
});
