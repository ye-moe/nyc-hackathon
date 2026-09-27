import { describe, expect, test } from "bun:test";
import { analyze } from "../src/analyze.ts";
import { approveDraft, draftComplaint } from "../src/complaint.ts";

const listing = "Sunny 1BR at 512 Halsey St, Brooklyn 11233. $2,200/mo. Must earn 40x the rent. No programs. Call Dave (718) 555-0142.";
const analyzed = () => analyze({ text: listing }, { useGemini: false });

describe("complaint draft", () => {
  test("refuses to draft for a clean listing", async () => {
    const r = await analyze({ text: "Nice 2BR, $2,500. No pets." }, { useGemini: false });
    await expect(draftComplaint({ result: r })).rejects.toThrow();
  });

  test("fills the CCHR form in the form's order", async () => {
    const d = await draftComplaint({ result: await analyzed(), listing: { source: "Craigslist", url: "https://example.org/l/1", seenOn: "2026-09-25T15:00:00Z", screenshotSaved: true } });
    const get = (f: string) => d.form.find((a) => a.field.startsWith(f))!;
    expect(d.form[0].field).toBe("Your Name");
    expect(get("Category").answer).toBe("Housing or Lending Practices");
    expect(get("Name of the person").answer).toBe("Dave");
    expect(get("Phone number").answer).toBe("(718) 555-0142");
    expect(get("Address or general").answer).toContain("512 Halsey St");
    expect(get("Date of most recent").answer).toBe("09/25/2026");
    expect(get("Please explain").answer).toContain('The listing states: "No programs." This refuses');
    expect(get("Please explain").answer).toContain("$88,000");
    expect(get("How did you hear").answer).toBe("Social services");
  });

  test("never pre-answers what only the person can answer", async () => {
    const d = await draftComplaint({ result: await analyzed() });
    for (const f of ["Your Name", "Your Email", "Have you filed a complaint with us before?", "Acknowledgement"]) {
      const a = d.form.find((x) => x.field.startsWith(f))!;
      expect(a.answer).toBe("");
      expect(a.source).toBe("you");
    }
  });

  test("is a draft until a person approves it, and approval sends nothing", async () => {
    const d = await draftComplaint({ result: await analyzed() });
    expect(d.status).toBe("draft_needs_review");
    expect(d.text).toContain("Nothing has been sent");
    const a = approveDraft(d, "Myra");
    expect(a.status).toBe("approved_by_human");
    expect(a.text).toContain("Not submitted");
    expect(() => approveDraft(d, " ")).toThrow();
  });

  test("missing facts become blocking items, deadline is one year out", async () => {
    const r = await analyze({ text: "No vouchers." }, { useGemini: false });
    const d = await draftComplaint({ result: r, listing: { seenOn: "2026-09-25T15:00:00Z" } });
    expect(d.blocking.join(" ")).toContain("landlord, broker, or management company name");
    expect(d.blocking.join(" ")).toContain("screenshot");
    expect(d.deadline).toBe("2027-09-25");
  });

  test("state option uses the 3-year deadline", async () => {
    const d = await draftComplaint({ result: await analyzed(), agency: "nysdhr", listing: { seenOn: "2026-09-25T15:00:00Z" } });
    expect(d.deadline).toBe("2029-09-25");
    expect(d.agency.name).toBe("NYS Division of Human Rights");
  });

  test("html escapes listing text", async () => {
    const r = await analyze({ text: "<img src=x onerror=alert(1)> no programs" }, { useGemini: false });
    const d = await draftComplaint({ result: r });
    expect(d.html).not.toContain("<img src=x");
  });
});
