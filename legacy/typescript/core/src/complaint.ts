// Draft a discrimination report from an analyzed listing, for a HUMAN to
// review, edit, and submit. This module never sends anything anywhere.
//
// The narrative is a fixed template filled from verified facts (the flagged
// clauses and the rules engine's math); no model writes it, so it can't
// invent facts. Anything we don't know becomes a visible [placeholder] and a
// checklist item. Tenant identity is never stored here: the reporter's name
// and contact info are placeholders the person fills in when submitting.

import { agencies, type Agency, type AgencyId } from "../../config/agencies.ts";
import { legal } from "../../config/cityfheps.ts";
import { geminiTranslate } from "./gemini.ts";
import type { AnalysisResult, Flag } from "./schema.ts";

export type ReporterRole = "tenant" | "caseworker" | "advocate";

export type ComplaintInput = {
  result: AnalysisResult;
  agency?: AgencyId;
  listing?: {
    url?: string;
    source?: string;        // "StreetEasy", "Craigslist", "Facebook Marketplace", ...
    seenOn?: string;        // ISO date the listing was seen/captured; defaults to analysis time
    screenshotSaved?: boolean;
    packetUrl?: string;
  };
  respondent?: { name?: string; company?: string; address?: string; phone?: string; email?: string };
  reporter?: { role: ReporterRole; organization?: string };
  // Optional: if someone contacted the landlord and was refused.
  contact?: { date?: string; how?: string; whatWasSaid?: string };
  tenantLanguage?: string;  // adds a translated copy of the description for the client
};

// One row per field on the agency's online form, in the form's order.
export type FormAnswer = {
  field: string;              // exact label on the form
  required: boolean;
  answer: string;             // what to type/select; "" when only the person can answer
  source: "auto" | "suggested" | "you";   // auto = from the listing; suggested = confirm it; you = only you can answer
  note?: string;
};

export type ComplaintDraft = {
  id: string;
  status: "draft_needs_review" | "approved_by_human";
  agency: Agency;
  fields: {
    category: string;
    basis: string;
    reporter: string;
    respondent: string;
    incidentDate: string;
    filedElsewhere: string;
    description: string;
  };
  form: FormAnswer[];         // answers for the agency's online form, field by field
  evidence: string[];
  blocking: string[];         // must be resolved before submitting
  warnings: string[];
  reviewChecklist: string[];
  deadline: string;           // ISO date
  text: string;               // full plain text, copy-paste ready
  html: string;
  descriptionTranslated?: { language: string; text: string };
  reviewedBy?: string;
  reviewedAt?: string;
  createdAt: string;
  sourceResultId: string;
};

const P = (label: string) => `[${label}]`;
const usd = (n: number) => "$" + Math.round(n).toLocaleString("en-US");
const day = (iso: string) => new Date(iso).toLocaleDateString("en-US", { timeZone: "America/New_York", year: "numeric", month: "long", day: "numeric" });

export async function draftComplaint(input: ComplaintInput): Promise<ComplaintDraft> {
  const r = input.result;
  if (r.verdict === "no_issue_found") {
    throw new Error("No issue was found in this listing, so there is nothing to report.");
  }
  const agency = agencies[input.agency ?? "cchr"];
  const ex = r.extraction;
  const L = input.listing ?? {};
  const seenOn = L.seenOn ?? r.analyzed_at;
  const problems = r.flags.filter((f) => f.severity !== "info");
  const violations = problems.filter((f) => f.severity === "violation");
  const blocking: string[] = [];
  const warnings: string[] = [];

  // ---- respondent ----
  const rs = { ...input.respondent, phone: input.respondent?.phone ?? ex.contact_phone };
  const respName = rs.name ?? ex.broker_or_landlord_name;
  const respAddress = rs.address ?? ex.address;
  const respondent = [
    respName ?? P("Landlord, broker, or management company name"),
    rs.company && rs.company !== respName ? rs.company : undefined,
    respAddress ? `Property: ${respAddress}${ex.borough ? `, ${ex.borough}` : ""}${ex.zip ? ` ${ex.zip}` : ""}` : P("Property address"),
    rs.phone ?? rs.email ?? P("Respondent phone or email, from the listing"),
  ].filter(Boolean).join("\n");
  if (!respName) blocking.push("Add the landlord, broker, or management company name (check the listing's contact section).");
  if (!rs.phone && !rs.email) blocking.push("Add the respondent's phone number or email from the listing.");
  if (!respAddress) warnings.push("The property address wasn't found. Add it if the listing shows it.");

  // ---- reporter (never stored; filled in by the person submitting) ----
  const role = input.reporter?.role ?? "caseworker";
  const reporter = [
    P("Your full name"),
    role === "tenant" ? "Prospective tenant (CityFHEPS voucher holder)" :
      `${role === "caseworker" ? "Caseworker" : "Advocate"}${input.reporter?.organization ? `, ${input.reporter.organization}` : ""}, reporting on behalf of a voucher holder`,
    P("Your phone and email"),
  ].join("\n");
  blocking.push("Fill in your name and contact information when you submit.");

  // ---- description: facts only, from flags + extraction ----
  const where = L.source ? `on ${L.source}` : "online";
  const unit = [
    ex.bedrooms === undefined ? "an apartment" : ex.bedrooms === 0 ? "a studio apartment" : `a ${ex.bedrooms}-bedroom apartment`,
    respAddress ? `at ${respAddress}` : undefined,
    ex.monthly_rent ? `for ${usd(ex.monthly_rent)} per month` : undefined,
  ].filter(Boolean).join(" ");
  const para: string[] = [];
  para.push(`On ${day(seenOn)}, a rental listing posted ${where}${L.url ? ` (${L.url})` : ""} advertised ${unit}.`);

  for (const f of problems) para.push(describe(f, sentenceAround(r.analyzed_text, f)));

  if (r.within_voucher_range) {
    para.push(`The advertised rent is within the CityFHEPS payment standard for this apartment size, so a voucher holder could otherwise have rented this unit.`);
  }
  if (input.contact?.whatWasSaid) {
    const c = input.contact;
    para.push(`On ${c.date ? day(c.date) : P("date of contact")}, the prospective tenant contacted the respondent${c.how ? ` by ${c.how}` : ""} and was told: "${c.whatWasSaid}"`);
  }
  para.push(violations.length
    ? `This language excludes applicants who pay rent with a CityFHEPS voucher or other rental assistance, which is discrimination based on lawful source of income under the ${agency.law}.`
    : `These terms may exclude applicants who pay rent with a CityFHEPS voucher or other rental assistance. I am asking the ${agency.name} to review whether they violate the ${agency.law}.`);
  para.push("This listing was first identified with an automated screening tool. I have reviewed the listing myself and confirm that the quoted text appears in it.");
  const description = para.join("\n\n");

  // ---- evidence ----
  const evidence = [
    L.url ? `Listing link: ${L.url}` : "Listing link: none (listing received as text or image)",
    L.screenshotSaved ? `Screenshot of the listing, captured ${day(seenOn)}` : P("Screenshot of the listing, attach it"),
    ...(L.packetUrl ? [`Evidence packet with highlighted clauses and calculations: ${L.packetUrl}`] : []),
  ];
  if (!L.screenshotSaved) blocking.push("Save a screenshot of the listing now. Listings get edited or deleted.");

  // ---- dates ----
  const deadlineDate = new Date(seenOn);
  deadlineDate.setFullYear(deadlineDate.getFullYear() + agency.deadlineYears);
  const deadline = deadlineDate.toISOString().slice(0, 10);
  if (!L.seenOn) warnings.push(`Incident date is set to the date we analyzed the listing (${day(seenOn)}). Change it if the listing was seen earlier.`);
  if (r.verdict === "needs_review") warnings.push("This listing was marked 'needs review', not a clear violation. Confirm the problem before submitting.");
  if (r.extractor !== "gemini" && r.analyzed_text.length < 20) warnings.push("Very little listing text was available. Check the original listing.");
  if (!L.url && !L.screenshotSaved) warnings.push("Without a link or screenshot, the agency may not be able to verify the listing.");

  const fields = {
    category: agency.formCategory,
    basis: "Lawful source of income (CityFHEPS / housing voucher / rental assistance)",
    reporter,
    respondent,
    incidentDate: day(seenOn),
    filedElsewhere: P("Has this been reported to any other agency or court? Yes / No"),
    description,
  };
  const form = input.agency === "nysdhr"
    ? dhrForm({ respName, respAddress, rs, seenOn, description, role })
    : cchrForm({ respName, respAddress, ex, rs, seenOn, description, role });

  blocking.push(`Answer whether this was already filed elsewhere. The ${agency.name} can't take a complaint already filed with another agency on the same facts.`);

  const reviewChecklist = [
    "Open the original listing and confirm every quoted phrase is still accurate.",
    "Check the respondent's name and contact details.",
    "Confirm the incident date.",
    "Read the description out loud. Remove anything you can't back up.",
    "Get the voucher holder's consent before reporting on their behalf.",
    `Submit by ${new Date(deadline + "T12:00:00").toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })} (${agency.deadlineNote}).`,
  ];

  let descriptionTranslated: ComplaintDraft["descriptionTranslated"];
  if (input.tenantLanguage && input.tenantLanguage !== "en") {
    const t = await geminiTranslate([description], input.tenantLanguage);
    if (t) descriptionTranslated = { language: input.tenantLanguage, text: t[0] };
    else warnings.push("Translation unavailable; the draft is English only.");
  }

  const draft: ComplaintDraft = {
    id: crypto.randomUUID(),
    status: "draft_needs_review",
    agency, fields, form, evidence, blocking, warnings, reviewChecklist, deadline,
    text: "", html: "",
    descriptionTranslated,
    createdAt: new Date().toISOString(),
    sourceResultId: r.id,
  };
  draft.text = renderText(draft);
  draft.html = renderHtml(draft);
  return draft;
}

const HEARD_ABOUT: Record<ReporterRole, string> = {
  caseworker: "Social services",
  advocate: "Community organization",
  tenant: "",
};

const ATTACHMENTS = [
  "Screenshot of the listing (shows the quoted text and the date)",
  "Evidence packet (open the packet link, then Print → Save as PDF)",
  "Any texts or emails with the landlord or broker, if you have them",
];

type FormCtx = {
  respName?: string; respAddress?: string; ex?: AnalysisResult["extraction"];
  rs: NonNullable<ComplaintInput["respondent"]>; seenOn: string; description: string; role: ReporterRole;
};

// Fields and order match nyc.gov/site/cchr/about/report-discrimination.page (checked 2026-09-26).
function cchrForm(c: FormCtx): FormAnswer[] {
  const location = c.respAddress
    ? [c.respAddress, c.ex?.borough, c.ex?.zip].filter(Boolean).join(", ")
    : c.ex?.borough ? `${c.ex.borough}, New York (exact address not listed)` : "";
  const you = (field: string, note: string): FormAnswer => ({ field, required: false, answer: "", source: "you", note });
  return [
    you("Your Name", "Optional on the form. We never store it."),
    you("Pronouns", "Optional."),
    you("Your Address", "Optional."),
    you("Your Email", "Optional, but the Commission needs a way to reach you."),
    you("Your Phone", "Optional, but the Commission needs a way to reach you."),
    { field: "Category of Discrimination", required: true, answer: "Housing or Lending Practices", source: "auto" },
    { field: "Name of the person(s) and/or business who discriminated against you or someone else", required: true,
      answer: c.respName ?? "", source: c.respName ? "auto" : "you",
      note: c.respName ? "From the listing. Check it matches the contact name." : "Required. Use the broker, landlord, or management company named on the listing." },
    { field: "Address or general location of the person(s) and/or business", required: true,
      answer: location, source: location ? "auto" : "you",
      note: location ? "The property's location, from the listing." : "Required. The property address or neighborhood from the listing." },
    { field: "Phone number of the person(s) and/or business", required: false,
      answer: c.rs.phone ?? "", source: c.rs.phone ? "auto" : "you", note: c.rs.phone ? undefined : "Copy it from the listing's contact section." },
    { field: "Date of most recent incident", required: true,
      answer: new Date(c.seenOn).toLocaleDateString("en-US", { timeZone: "America/New_York", month: "2-digit", day: "2-digit", year: "numeric" }),
      source: "suggested", note: "The date the listing was seen. Use a later date if the listing was still up or you were refused later." },
    { field: "Have you filed a complaint with us before?", required: true, answer: "", source: "you",
      note: "Yes or No: whether you have filed with the NYC Commission before. Only you know this." },
    { field: "Please explain the issue or problem", required: true, answer: c.description, source: "suggested",
      note: "Drafted from the listing. Read it, edit anything that isn't accurate, then paste it." },
    ...ATTACHMENTS.map((a, i) => ({ field: `Upload attachment ${i + 1}`, required: false, answer: a, source: "suggested" as const })),
    { field: "How did you hear about the Commission?", required: true,
      answer: HEARD_ABOUT[c.role], source: HEARD_ABOUT[c.role] ? "suggested" : "you",
      note: "Pick whichever is true for you." },
    { field: "Acknowledgement (form is not an official complaint)", required: true, answer: "", source: "you",
      note: "You must check this yourself. It says this report is not an official complaint, and that the one-year deadline only stops " +
        "once a verified complaint is signed, notarized, and delivered to the Commission's Law Enforcement Bureau." },
  ];
}

// NYS DHR asks for incident date(s), respondent's legal name + contact, and your legal name + contact (dhr.ny.gov/report).
function dhrForm(c: FormCtx): FormAnswer[] {
  return [
    { field: "Your legal name and contact information", required: true, answer: "", source: "you", note: "We never store it." },
    { field: "Type of discrimination", required: true, answer: "Housing: lawful source of income (CityFHEPS / housing voucher)", source: "auto" },
    { field: "Respondent's legal name", required: true, answer: c.respName ?? "", source: c.respName ? "auto" : "you",
      note: c.respName ? "From the listing." : "Required. Broker, landlord, or management company from the listing." },
    { field: "Respondent's contact information", required: true,
      answer: [c.respAddress, c.rs.phone, c.rs.email].filter(Boolean).join(" · "), source: c.rs.phone || c.rs.email ? "auto" : "you" },
    { field: "Date(s) of incident", required: true,
      answer: new Date(c.seenOn).toLocaleDateString("en-US", { timeZone: "America/New_York", month: "2-digit", day: "2-digit", year: "numeric" }), source: "suggested" },
    { field: "Description", required: true, answer: c.description, source: "suggested", note: "Read and edit before pasting." },
  ];
}

/** Record that a person reviewed the draft. Still doesn't send anything: the
 *  person submits it themselves through the agency's form, phone, or office. */
export function approveDraft(draft: ComplaintDraft, reviewer: string): ComplaintDraft {
  if (!reviewer.trim()) throw new Error("A reviewer name is required.");
  const approved: ComplaintDraft = { ...draft, status: "approved_by_human", reviewedBy: reviewer.trim(), reviewedAt: new Date().toISOString() };
  approved.text = renderText(approved);
  approved.html = renderHtml(approved);
  return approved;
}

// Quote the whole sentence a clause sits in: "Must earn 40x the rent." reads as
// evidence; "earn 40x" doesn't.
function sentenceAround(text: string, f: Flag): string {
  if (!f.span) return f.evidence_text;
  const [s, e] = f.span;
  const start = Math.max(text.lastIndexOf(". ", s - 1), text.lastIndexOf("\n", s - 1), text.lastIndexOf("! ", s - 1), text.lastIndexOf("。", s - 1));
  const ends = [". ", "! ", "\n", "。"].map((d) => text.indexOf(d, e)).filter((i) => i >= 0);
  const end = ends.length ? Math.min(...ends) + 1 : text.length;
  const out = text.slice(start < 0 ? 0 : start + 1, end).trim();
  return out.length <= 240 ? out : f.evidence_text;
}

function describe(f: Flag, sentence: string): string {
  // Quote ends with its own punctuation, so the sentence reads: The listing states: "No programs." This ...
  const quote = `"${sentence}${/[.!?。]$/.test(sentence) ? "" : "."}"`;
  switch (f.rule_id) {
    case "R1":
      return f.severity === "violation"
        ? `The listing states: ${quote} This refuses applicants who pay rent with a housing voucher or rental assistance.`
        : `The listing states: ${quote} This appears to discourage applicants who use rental assistance.`;
    case "R2": {
      const c = f.calculation;
      if (!c?.required_annual_income) return `The listing states: ${quote} This is an income requirement applied to the full rent.`;
      const lines = [`The listing states: ${quote} This requires an annual income of about ${usd(c.required_annual_income)}, applied to the full rent.`];
      lines.push(`${legal.incomeRule}`);
      if (c.lawful_annual_income) {
        lines.push(`Applied only to the tenant's share of the rent, the same requirement would be about ${usd(c.lawful_annual_income)} a year` +
          (c.example_household_income >= c.lawful_annual_income ? `, which an example CityFHEPS household earning ${usd(c.example_household_income)} would meet.` : `.`));
      }
      if (c.excludes_every_eligible_household) lines.push(`${usd(c.required_annual_income)} is more than any CityFHEPS-eligible household can earn, so the requirement excludes every voucher holder.`);
      return lines.join(" ");
    }
    case "R3":
      return `The listing states: ${quote} ${f.explanation}`;
    default:
      return `The listing states: ${quote}`;
  }
}

function renderText(d: ComplaintDraft): string {
  const hr = "—".repeat(40);
  const f = d.fields;
  return [
    d.status === "approved_by_human"
      ? `REVIEWED DRAFT: reviewed by ${d.reviewedBy} on ${day(d.reviewedAt!)}. Not submitted. Submit it yourself using the options below.`
      : "DRAFT: must be reviewed by a person before it is submitted. Nothing has been sent.",
    "",
    `REPORT OF HOUSING DISCRIMINATION: ${d.agency.name}`,
    hr,
    `ONLINE FORM ANSWERS: ${d.agency.filing[0].detail.split(" ")[0]}`,
    "Key: [auto] from the listing · [check] suggested, confirm it · [you] only you can answer",
    ...d.form.flatMap((a) => [
      `${a.field}${a.required ? " *" : ""}  [${a.source === "auto" ? "auto" : a.source === "suggested" ? "check" : "you"}]`,
      `   ${a.answer ? a.answer.replace(/\n/g, "\n   ") : "(leave for you)"}`,
      ...(a.note ? [`   Note: ${a.note}`] : []),
    ]),
    hr,
    `Category: ${f.category}`,
    `Basis: ${f.basis}`,
    "",
    "PERSON REPORTING", f.reporter, "",
    "RESPONDENT", f.respondent, "",
    `DATE OF INCIDENT: ${f.incidentDate}`,
    `FILED ELSEWHERE: ${f.filedElsewhere}`,
    "",
    "WHAT HAPPENED", f.description, "",
    "EVIDENCE", ...d.evidence.map((e) => `• ${e}`), "",
    hr,
    "HOW TO SUBMIT (free, no lawyer needed)",
    ...d.agency.filing.map((m) => `• ${m.method}: ${m.detail}`),
    ...d.agency.notes.map((n) => `  ${n}`),
    `Deadline: ${d.deadline} (${d.agency.deadlineNote})`,
    "",
    "BEFORE SUBMITTING",
    ...d.blocking.map((b) => `☐ ${b}`),
    ...d.reviewChecklist.map((c) => `☐ ${c}`),
    ...(d.warnings.length ? ["", "NOTES", ...d.warnings.map((w) => `! ${w}`)] : []),
    ...(d.descriptionTranslated ? ["", `WHAT HAPPENED (${d.descriptionTranslated.language}, for the client; submit the English version)`, d.descriptionTranslated.text] : []),
  ].join("\n");
}

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
// Show [placeholders] as fill-in fields so they can't be missed.
const fill = (s: string) => esc(s).replace(/\[([^\]]+)\]/g, '<span class="ph">[$1]</span>').replace(/\n/g, "<br>");

function renderHtml(d: ComplaintDraft): string {
  const f = d.fields;
  const approved = d.status === "approved_by_human";
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Complaint draft</title>
<style>
:root{--bg:#fff;--fg:#111;--muted:#555;--line:#ddd;--banner:#fff4d6;--bannerfg:#6b4a00;--ok:#e6f4ea;--okfg:#1e6b34;--ph:#fde2e1;--phfg:#8c1d18}
@media(prefers-color-scheme:dark){:root{--bg:#121212;--fg:#f2f2f2;--muted:#b5b5b5;--line:#333;--banner:#3a2e00;--bannerfg:#ffd97a;--ok:#12301c;--okfg:#8fd19e;--ph:#4a1512;--phfg:#ffb4ab}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:17px/1.6 system-ui,sans-serif}
main{max-width:760px;margin:0 auto;padding:24px 16px 48px}
.banner{background:var(--banner);color:var(--bannerfg);padding:12px 16px;border-radius:8px;font-weight:600}
.banner.ok{background:var(--ok);color:var(--okfg)}
h1{font-size:1.4rem;margin:20px 0 4px}h2{font-size:1rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin:24px 0 6px}
dl{display:grid;grid-template-columns:max-content 1fr;gap:4px 16px;margin:0}dt{color:var(--muted)}
.box{border:1px solid var(--line);border-radius:8px;padding:12px 16px}
.ph{background:var(--ph);color:var(--phfg);border-radius:4px;padding:0 4px;font-weight:600}
ul.check{list-style:none;padding:0}
ol.form{padding-left:20px}ol.form li{margin:0 0 16px}.fl{font-weight:600}.req{color:var(--phfg)}
.ans{border:1px solid var(--line);border-radius:6px;padding:8px 10px;margin:4px 0;white-space:normal}.ans.empty{color:var(--muted);font-style:italic}
.note{color:var(--muted);font-size:.9rem}.tag{font-size:.75rem;border-radius:10px;padding:1px 8px;border:1px solid var(--line);font-weight:600}
.tag.auto{color:var(--okfg)}.tag.suggested{color:var(--bannerfg)}.tag.you{color:var(--phfg)}
button{font:inherit;font-size:.85rem;padding:4px 12px;border-radius:6px;border:1px solid var(--line);background:transparent;color:var(--fg);cursor:pointer}ul.check li::before{content:"☐ ";}
@media print{.banner{border:2px solid #000}}
</style></head><body><main>
<div class="banner ${approved ? "ok" : ""}">${approved
    ? `Reviewed by ${esc(d.reviewedBy!)} on ${esc(day(d.reviewedAt!))}. Not submitted. Submit it yourself using the options below.`
    : "DRAFT: a person must review this before it is submitted. Nothing has been sent."}</div>
<h1>Report of housing discrimination</h1>
<div style="color:var(--muted)">${esc(d.agency.name)}</div>
<h2>Online form answers</h2>
<p style="color:var(--muted);margin:0 0 8px">Field by field, in the order the form asks. <span class="tag auto">auto</span> from the listing · <span class="tag suggested">check</span> suggested, confirm it · <span class="tag you">you</span> only you can answer</p>
<ol class="form">${d.form.map((a, i) => `<li><div class="fl">${esc(a.field)}${a.required ? ' <span class="req">*</span>' : ""} <span class="tag ${a.source}">${a.source === "suggested" ? "check" : a.source}</span></div>
${a.answer ? `<div class="ans" id="a${i}">${esc(a.answer).replace(/\n/g, "<br>")}</div><button type="button" onclick="navigator.clipboard.writeText(document.getElementById('a${i}').innerText).then(()=>{this.textContent='Copied'})">Copy</button>` : `<div class="ans empty">You fill this in</div>`}
${a.note ? `<div class="note">${esc(a.note)}</div>` : ""}</li>`).join("")}</ol>
<h2>Report details</h2>
<dl><dt>Category</dt><dd>${esc(f.category)}</dd><dt>Basis</dt><dd>${esc(f.basis)}</dd>
<dt>Date of incident</dt><dd>${esc(f.incidentDate)}</dd><dt>Filed elsewhere?</dt><dd>${fill(f.filedElsewhere)}</dd></dl>
<h2>Person reporting</h2><div class="box">${fill(f.reporter)}</div>
<h2>Respondent</h2><div class="box">${fill(f.respondent)}</div>
<h2>What happened</h2><div class="box">${fill(f.description)}</div>
${d.descriptionTranslated ? `<h2>What happened (${esc(d.descriptionTranslated.language)}, for the client)</h2><div class="box" lang="${esc(d.descriptionTranslated.language)}">${fill(d.descriptionTranslated.text)}</div>` : ""}
<h2>Evidence</h2><ul>${d.evidence.map((e) => `<li>${fill(e)}</li>`).join("")}</ul>
<h2>Before submitting</h2><ul class="check">${[...d.blocking, ...d.reviewChecklist].map((c) => `<li>${esc(c)}</li>`).join("")}</ul>
${d.warnings.length ? `<h2>Notes</h2><ul>${d.warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
<h2>How to submit (free, no lawyer needed)</h2>
<ul>${d.agency.filing.map((m) => `<li><b>${esc(m.method)}:</b> ${esc(m.detail)}</li>`).join("")}</ul>
<p>${d.agency.notes.map(esc).join("<br>")}</p>
<p><b>Deadline:</b> ${esc(d.deadline)} (${esc(d.agency.deadlineNote)})</p>
</main></body></html>`;
}
