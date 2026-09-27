"""Draft a discrimination report from an analyzed listing, for a HUMAN to
review, edit, and submit. This module never sends anything anywhere.

The narrative is a fixed template filled from verified facts (the flagged
clauses and the rules engine's math); no model writes it, so it can't invent
facts. Anything we don't know becomes a visible [placeholder] and a checklist
item. Tenant identity is never stored here: the reporter's name and contact
info are placeholders the person fills in when submitting."""
from __future__ import annotations

import html as _html
import re
import uuid
from datetime import datetime, timezone
from typing import List, Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from config import cityfheps as C
from config.agencies import AGENCIES
from core.gemini import gemini_translate
from core.rules import num, usd
from core.schema import AnalysisResult, Flag

NY = ZoneInfo("America/New_York")
ReporterRole = Literal["tenant", "caseworker", "advocate"]


class ListingInfo(BaseModel):
    url: Optional[str] = None
    source: Optional[str] = None           # "StreetEasy", "Craigslist", "Facebook Marketplace", ...
    seen_on: Optional[str] = None          # ISO date the listing was seen; defaults to analysis time
    screenshot_saved: bool = False
    packet_url: Optional[str] = None


class Respondent(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class Reporter(BaseModel):
    role: ReporterRole = "caseworker"
    organization: Optional[str] = None


class Contact(BaseModel):
    """Optional: if someone contacted the landlord and was refused."""
    date: Optional[str] = None
    how: Optional[str] = None
    what_was_said: Optional[str] = None


class FormAnswer(BaseModel):
    """One row per field on the agency's online form, in the form's order."""
    field: str                                          # exact label on the form
    required: bool
    answer: str                                         # "" when only the person can answer
    source: Literal["auto", "suggested", "you"]         # auto = from listing; suggested = confirm; you = only you know
    note: Optional[str] = None


class ComplaintDraft(BaseModel):
    id: str
    status: Literal["draft_needs_review", "approved_by_human"]
    agency: dict
    fields: dict
    form: List[FormAnswer]          # answers for the agency's online form, field by field
    evidence: List[str]
    blocking: List[str]             # must be resolved before submitting
    warnings: List[str]
    review_checklist: List[str]
    deadline: str                   # ISO date
    text: str = ""                  # full plain text, copy-paste ready
    html: str = ""
    description_translated: Optional[dict] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_result_id: str


def P(label: str) -> str:
    return f"[{label}]"


def _dt(iso: str) -> datetime:
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(NY)


def day(iso: str) -> str:
    d = _dt(iso)
    return f"{d:%B} {d.day}, {d.year}"


def draft_complaint(
    result: AnalysisResult,
    agency: str = "cchr",
    listing: Optional[ListingInfo | dict] = None,
    respondent: Optional[Respondent | dict] = None,
    reporter: Optional[Reporter | dict] = None,
    contact: Optional[Contact | dict] = None,
    tenant_language: Optional[str] = None,
) -> ComplaintDraft:
    r = result
    if r.verdict == "no_issue_found":
        raise ValueError("No issue was found in this listing, so there is nothing to report.")
    ag = AGENCIES[agency]
    ex = r.extraction
    L = ListingInfo.model_validate(listing or {})
    rs = Respondent.model_validate(respondent or {})
    rep = Reporter.model_validate(reporter or {})
    ct = Contact.model_validate(contact or {})
    seen_on = L.seen_on or r.analyzed_at
    problems = [f for f in r.flags if f.severity != "info"]
    violations = [f for f in problems if f.severity == "violation"]
    blocking: List[str] = []
    warnings: List[str] = []

    # ---- respondent ----
    phone = rs.phone or ex.contact_phone
    resp_name = rs.name or ex.broker_or_landlord_name
    resp_address = rs.address or ex.address
    location = ", ".join(x for x in [resp_address, ex.borough, ex.zip] if x)
    respondent_block = "\n".join(x for x in [
        resp_name or P("Landlord, broker, or management company name"),
        rs.company if rs.company and rs.company != resp_name else None,
        f"Property: {location}" if resp_address else P("Property address"),
        phone or rs.email or P("Respondent phone or email, from the listing"),
    ] if x)
    if not resp_name:
        blocking.append("Add the landlord, broker, or management company name (check the listing's contact section).")
    if not phone and not rs.email:
        blocking.append("Add the respondent's phone number or email from the listing.")
    if not resp_address:
        warnings.append("The property address wasn't found. Add it if the listing shows it.")

    # ---- reporter (never stored; filled in by the person submitting) ----
    role_line = ("Prospective tenant (CityFHEPS voucher holder)" if rep.role == "tenant" else
                 f"{'Caseworker' if rep.role == 'caseworker' else 'Advocate'}{', ' + rep.organization if rep.organization else ''}, "
                 "reporting on behalf of a voucher holder")
    reporter_block = "\n".join([P("Your full name"), role_line, P("Your phone and email")])
    blocking.append("Fill in your name and contact information when you submit.")

    # ---- description: facts only, from flags + extraction ----
    where = f"on {L.source}" if L.source else "online"
    if ex.bedrooms is None:
        unit = "an apartment"
    elif ex.bedrooms == 0:
        unit = "a studio apartment"
    else:
        unit = f"a {num(ex.bedrooms)}-bedroom apartment"
    unit = " ".join(x for x in [unit, f"at {resp_address}" if resp_address else None,
                                f"for {usd(ex.monthly_rent)} per month" if ex.monthly_rent else None] if x)
    para = [f"On {day(seen_on)}, a rental listing posted {where}{f' ({L.url})' if L.url else ''} advertised {unit}."]
    para += [_describe(f, _sentence_around(r.analyzed_text, f)) for f in problems]
    if r.within_voucher_range:
        para.append("The advertised rent is within the CityFHEPS payment standard for this apartment size, "
                    "so a voucher holder could otherwise have rented this unit.")
    if ct.what_was_said:
        para.append(f"On {day(ct.date) if ct.date else P('date of contact')}, the prospective tenant contacted the respondent"
                    f"{' by ' + ct.how if ct.how else ''} and was told: \"{ct.what_was_said}\"")
    para.append(
        f"This language excludes applicants who pay rent with a CityFHEPS voucher or other rental assistance, which is "
        f"discrimination based on lawful source of income under the {ag['law']}." if violations else
        f"These terms may exclude applicants who pay rent with a CityFHEPS voucher or other rental assistance. I am asking the "
        f"{ag['name']} to review whether they violate the {ag['law']}.")
    para.append("This listing was first identified with an automated screening tool. "
                "I have reviewed the listing myself and confirm that the quoted text appears in it.")
    description = "\n\n".join(para)

    # ---- evidence ----
    evidence = [
        f"Listing link: {L.url}" if L.url else "Listing link: none (listing received as text or image)",
        f"Screenshot of the listing, captured {day(seen_on)}" if L.screenshot_saved else P("Screenshot of the listing, attach it"),
        *([f"Evidence packet with highlighted clauses and calculations: {L.packet_url}"] if L.packet_url else []),
    ]
    if not L.screenshot_saved:
        blocking.append("Save a screenshot of the listing now. Listings get edited or deleted.")

    # ---- dates ----
    seen = _dt(seen_on)
    try:
        deadline_d = seen.replace(year=seen.year + ag["deadline_years"])
    except ValueError:  # Feb 29
        deadline_d = seen.replace(year=seen.year + ag["deadline_years"], day=28)
    deadline = deadline_d.date().isoformat()
    if not L.seen_on:
        warnings.append(f"Incident date is set to the date we analyzed the listing ({day(seen_on)}). Change it if the listing was seen earlier.")
    if r.verdict == "needs_review":
        warnings.append("This listing was marked 'needs review', not a clear violation. Confirm the problem before submitting.")
    if r.extractor != "gemini" and len(r.analyzed_text) < 20:
        warnings.append("Very little listing text was available. Check the original listing.")
    if not L.url and not L.screenshot_saved:
        warnings.append("Without a link or screenshot, the agency may not be able to verify the listing.")

    fields = {
        "category": ag["form_category"],
        "basis": "Lawful source of income (CityFHEPS / housing voucher / rental assistance)",
        "reporter": reporter_block,
        "respondent": respondent_block,
        "incident_date": day(seen_on),
        "filed_elsewhere": P("Has this been reported to any other agency or court? Yes / No"),
        "description": description,
    }
    date_mdy = f"{seen:%m/%d/%Y}"
    form = (_dhr_form(resp_name, resp_address, phone, rs.email, date_mdy, description) if agency == "nysdhr"
            else _cchr_form(resp_name, location, ex.borough, phone, date_mdy, description, rep.role))
    blocking.append(f"Answer whether this was already filed elsewhere. The {ag['name']} can't take a complaint "
                    "already filed with another agency on the same facts.")

    review_checklist = [
        "Open the original listing and confirm every quoted phrase is still accurate.",
        "Check the respondent's name and contact details.",
        "Confirm the incident date.",
        "Read the description out loud. Remove anything you can't back up.",
        "Get the voucher holder's consent before reporting on their behalf.",
        f"Submit by {deadline_d:%B} {deadline_d.day}, {deadline_d.year} ({ag['deadline_note']}).",
    ]

    translated = None
    if tenant_language and tenant_language != "en":
        t = gemini_translate([description], tenant_language)
        if t:
            translated = {"language": tenant_language, "text": t[0]}
        else:
            warnings.append("Translation unavailable; the draft is English only.")

    d = ComplaintDraft(
        id=str(uuid.uuid4()), status="draft_needs_review", agency=ag, fields=fields, form=form, evidence=evidence,
        blocking=blocking, warnings=warnings, review_checklist=review_checklist, deadline=deadline,
        description_translated=translated, source_result_id=r.id)
    d.text, d.html = render_text(d), render_html(d)
    return d


def approve_draft(draft: ComplaintDraft, reviewer: str) -> ComplaintDraft:
    """Record that a person reviewed the draft. Still doesn't send anything: the
    person submits it themselves through the agency's form, phone, or office."""
    if not reviewer.strip():
        raise ValueError("A reviewer name is required.")
    a = draft.model_copy(update={"status": "approved_by_human", "reviewed_by": reviewer.strip(),
                                 "reviewed_at": datetime.now(timezone.utc).isoformat()})
    a.text, a.html = render_text(a), render_html(a)
    return a


# ---------- form answers ----------
HEARD_ABOUT = {"caseworker": "Social services", "advocate": "Community organization", "tenant": ""}
ATTACHMENTS = [
    "Screenshot of the listing (shows the quoted text and the date)",
    "Evidence packet (open the packet link, then Print → Save as PDF)",
    "Any texts or emails with the landlord or broker, if you have them",
]


def _cchr_form(name, location, borough, phone, date_mdy, description, role) -> List[FormAnswer]:
    """Fields and order match nyc.gov/site/cchr/about/report-discrimination.page (checked 2026-09-26)."""
    loc = location or (f"{borough}, New York (exact address not listed)" if borough else "")
    you = lambda field, note: FormAnswer(field=field, required=False, answer="", source="you", note=note)
    return [
        you("Your Name", "Optional on the form. We never store it."),
        you("Pronouns", "Optional."),
        you("Your Address", "Optional."),
        you("Your Email", "Optional, but the Commission needs a way to reach you."),
        you("Your Phone", "Optional, but the Commission needs a way to reach you."),
        FormAnswer(field="Category of Discrimination", required=True, answer="Housing or Lending Practices", source="auto"),
        FormAnswer(field="Name of the person(s) and/or business who discriminated against you or someone else", required=True,
                   answer=name or "", source="auto" if name else "you",
                   note="From the listing. Check it matches the contact name." if name
                   else "Required. Use the broker, landlord, or management company named on the listing."),
        FormAnswer(field="Address or general location of the person(s) and/or business", required=True,
                   answer=loc, source="auto" if loc else "you",
                   note="The property's location, from the listing." if loc else "Required. The property address or neighborhood from the listing."),
        FormAnswer(field="Phone number of the person(s) and/or business", required=False, answer=phone or "",
                   source="auto" if phone else "you", note=None if phone else "Copy it from the listing's contact section."),
        FormAnswer(field="Date of most recent incident", required=True, answer=date_mdy, source="suggested",
                   note="The date the listing was seen. Use a later date if the listing was still up or you were refused later."),
        FormAnswer(field="Have you filed a complaint with us before?", required=True, answer="", source="you",
                   note="Yes or No: whether you have filed with the NYC Commission before. Only you know this."),
        FormAnswer(field="Please explain the issue or problem", required=True, answer=description, source="suggested",
                   note="Drafted from the listing. Read it, edit anything that isn't accurate, then paste it."),
        *[FormAnswer(field=f"Upload attachment {i + 1}", required=False, answer=a, source="suggested") for i, a in enumerate(ATTACHMENTS)],
        FormAnswer(field="How did you hear about the Commission?", required=True, answer=HEARD_ABOUT[role],
                   source="suggested" if HEARD_ABOUT[role] else "you", note="Pick whichever is true for you."),
        FormAnswer(field="Acknowledgement (form is not an official complaint)", required=True, answer="", source="you",
                   note="You must check this yourself. It says this report is not an official complaint, and that the one-year deadline "
                        "only stops once a verified complaint is signed, notarized, and delivered to the Commission's Law Enforcement Bureau."),
    ]


def _dhr_form(name, address, phone, email, date_mdy, description) -> List[FormAnswer]:
    """NYS DHR asks for incident date(s), respondent's legal name + contact, and your legal name + contact (dhr.ny.gov/report)."""
    contact = " · ".join(x for x in [address, phone, email] if x)
    return [
        FormAnswer(field="Your legal name and contact information", required=True, answer="", source="you", note="We never store it."),
        FormAnswer(field="Type of discrimination", required=True, answer="Housing: lawful source of income (CityFHEPS / housing voucher)", source="auto"),
        FormAnswer(field="Respondent's legal name", required=True, answer=name or "", source="auto" if name else "you",
                   note="From the listing." if name else "Required. Broker, landlord, or management company from the listing."),
        FormAnswer(field="Respondent's contact information", required=True, answer=contact, source="auto" if (phone or email) else "you"),
        FormAnswer(field="Date(s) of incident", required=True, answer=date_mdy, source="suggested"),
        FormAnswer(field="Description", required=True, answer=description, source="suggested", note="Read and edit before pasting."),
    ]


# ---------- narrative helpers ----------
def _sentence_around(text: str, f: Flag) -> str:
    """Quote the whole sentence a clause sits in: "Must earn 40x the rent." reads
    as evidence; "earn 40x" doesn't."""
    if not f.span:
        return f.evidence_text
    s, e = f.span
    start = max(text.rfind(". ", 0, s), text.rfind("\n", 0, s), text.rfind("! ", 0, s), text.rfind("。", 0, s))
    ends = [i for i in (text.find(d, e) for d in (". ", "! ", "\n", "。")) if i >= 0]
    end = min(ends) + 1 if ends else len(text)
    out = text[(0 if start < 0 else start + 1):end].strip()
    return out if len(out) <= 240 else f.evidence_text


def _describe(f: Flag, sentence: str) -> str:
    # Quote ends with its own punctuation: The listing states: "No programs." This ...
    quote = f'"{sentence}{"" if re.search(r"[.!?。]$", sentence) else "."}"'
    if f.rule_id == "R1":
        return (f"The listing states: {quote} This refuses applicants who pay rent with a housing voucher or rental assistance."
                if f.severity == "violation" else
                f"The listing states: {quote} This appears to discourage applicants who use rental assistance.")
    if f.rule_id == "R2":
        c = f.calculation
        if not c or not c.required_annual_income:
            return f"The listing states: {quote} This is an income requirement applied to the full rent."
        lines = [f"The listing states: {quote} This requires an annual income of about {usd(c.required_annual_income)}, applied to the full rent.",
                 C.INCOME_RULE]
        if c.lawful_annual_income:
            lines.append(f"Applied only to the tenant's share of the rent, the same requirement would be about {usd(c.lawful_annual_income)} a year"
                         + (f", which an example CityFHEPS household earning {usd(c.example_household_income)} would meet."
                            if c.example_household_income >= c.lawful_annual_income else "."))
        if c.excludes_every_eligible_household:
            lines.append(f"{usd(c.required_annual_income)} is more than any CityFHEPS-eligible household can earn, so the requirement excludes every voucher holder.")
        return " ".join(lines)
    if f.rule_id == "R3":
        return f"The listing states: {quote} {f.explanation}"
    return f"The listing states: {quote}"


# ---------- rendering ----------
def render_text(d: ComplaintDraft) -> str:
    hr = "—" * 40
    f = d.fields
    tag = {"auto": "auto", "suggested": "check", "you": "you"}
    out = [
        f"REVIEWED DRAFT: reviewed by {d.reviewed_by} on {day(d.reviewed_at)}. Not submitted. Submit it yourself using the options below."
        if d.status == "approved_by_human" else "DRAFT: must be reviewed by a person before it is submitted. Nothing has been sent.",
        "", f"REPORT OF HOUSING DISCRIMINATION: {d.agency['name']}", hr,
        f"ONLINE FORM ANSWERS: {d.agency['form_url']}",
        "Key: [auto] from the listing · [check] suggested, confirm it · [you] only you can answer",
    ]
    for a in d.form:
        out.append(f"{a.field}{' *' if a.required else ''}  [{tag[a.source]}]")
        out.append("   " + (a.answer.replace("\n", "\n   ") if a.answer else "(leave for you)"))
        if a.note:
            out.append(f"   Note: {a.note}")
    out += [hr, f"Category: {f['category']}", f"Basis: {f['basis']}", "",
            "PERSON REPORTING", f["reporter"], "", "RESPONDENT", f["respondent"], "",
            f"DATE OF INCIDENT: {f['incident_date']}", f"FILED ELSEWHERE: {f['filed_elsewhere']}", "",
            "WHAT HAPPENED", f["description"], "", "EVIDENCE", *[f"• {e}" for e in d.evidence], "", hr,
            "HOW TO SUBMIT (free, no lawyer needed)", *[f"• {m['method']}: {m['detail']}" for m in d.agency["filing"]],
            *[f"  {n}" for n in d.agency["notes"]], f"Deadline: {d.deadline} ({d.agency['deadline_note']})", "",
            "BEFORE SUBMITTING", *[f"☐ {b}" for b in d.blocking], *[f"☐ {c}" for c in d.review_checklist]]
    if d.warnings:
        out += ["", "NOTES", *[f"! {w}" for w in d.warnings]]
    if d.description_translated:
        out += ["", f"WHAT HAPPENED ({d.description_translated['language']}, for the client; submit the English version)",
                d.description_translated["text"]]
    return "\n".join(out)


def _esc(s: str) -> str:
    return _html.escape(s, quote=True)


def _fill(s: str) -> str:
    """Show [placeholders] as fill-in fields so they can't be missed."""
    return re.sub(r"\[([^\]]+)\]", r'<span class="ph">[\1]</span>', _esc(s)).replace("\n", "<br>")


def render_html(d: ComplaintDraft) -> str:
    f = d.fields
    approved = d.status == "approved_by_human"
    banner = (f"Reviewed by {_esc(d.reviewed_by)} on {_esc(day(d.reviewed_at))}. Not submitted. Submit it yourself using the options below."
              if approved else "DRAFT: a person must review this before it is submitted. Nothing has been sent.")
    rows = []
    for i, a in enumerate(d.form):
        label = "check" if a.source == "suggested" else a.source
        ans = (f'<div class="ans" id="a{i}">{_esc(a.answer).replace(chr(10), "<br>")}</div>'
               f'<button type="button" onclick="navigator.clipboard.writeText(document.getElementById(\'a{i}\').innerText).then(()=>{{this.textContent=\'Copied\'}})">Copy</button>'
               if a.answer else '<div class="ans empty">You fill this in</div>')
        rows.append(f'<li><div class="fl">{_esc(a.field)}{" <span class=req>*</span>" if a.required else ""} <span class="tag {a.source}">{label}</span></div>'
                    f'{ans}{f"<div class=note>{_esc(a.note)}</div>" if a.note else ""}</li>')
    tr = d.description_translated
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Complaint draft</title>
<style>
:root{{--bg:#fff;--fg:#111;--muted:#555;--line:#ddd;--banner:#fff4d6;--bannerfg:#6b4a00;--ok:#e6f4ea;--okfg:#1e6b34;--ph:#fde2e1;--phfg:#8c1d18}}
@media(prefers-color-scheme:dark){{:root{{--bg:#121212;--fg:#f2f2f2;--muted:#b5b5b5;--line:#333;--banner:#3a2e00;--bannerfg:#ffd97a;--ok:#12301c;--okfg:#8fd19e;--ph:#4a1512;--phfg:#ffb4ab}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:17px/1.6 system-ui,sans-serif}}
main{{max-width:760px;margin:0 auto;padding:24px 16px 48px}}
.banner{{background:var(--banner);color:var(--bannerfg);padding:12px 16px;border-radius:8px;font-weight:600}}.banner.ok{{background:var(--ok);color:var(--okfg)}}
h1{{font-size:1.4rem;margin:20px 0 4px}}h2{{font-size:1rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin:24px 0 6px}}
dl{{display:grid;grid-template-columns:max-content 1fr;gap:4px 16px;margin:0}}dt{{color:var(--muted)}}
.box{{border:1px solid var(--line);border-radius:8px;padding:12px 16px}}
.ph{{background:var(--ph);color:var(--phfg);border-radius:4px;padding:0 4px;font-weight:600}}
ul.check{{list-style:none;padding:0}}ul.check li::before{{content:"☐ ";}}
ol.form{{padding-left:20px}}ol.form li{{margin:0 0 16px}}.fl{{font-weight:600}}.req{{color:var(--phfg)}}
.ans{{border:1px solid var(--line);border-radius:6px;padding:8px 10px;margin:4px 0}}.ans.empty{{color:var(--muted);font-style:italic}}
.note{{color:var(--muted);font-size:.9rem}}.tag{{font-size:.75rem;border-radius:10px;padding:1px 8px;border:1px solid var(--line);font-weight:600}}
.tag.auto{{color:var(--okfg)}}.tag.suggested{{color:var(--bannerfg)}}.tag.you{{color:var(--phfg)}}
button{{font:inherit;font-size:.85rem;padding:4px 12px;border-radius:6px;border:1px solid var(--line);background:transparent;color:var(--fg);cursor:pointer}}
@media print{{.banner{{border:2px solid #000}}button{{display:none}}}}
</style></head><body><main>
<div class="banner {'ok' if approved else ''}">{banner}</div>
<h1>Report of housing discrimination</h1>
<div style="color:var(--muted)">{_esc(d.agency['name'])}</div>
<h2>Online form answers</h2>
<p style="color:var(--muted);margin:0 0 8px">Field by field, in the order the form asks. <span class="tag auto">auto</span> from the listing ·
<span class="tag suggested">check</span> suggested, confirm it · <span class="tag you">you</span> only you can answer</p>
<ol class="form">{''.join(rows)}</ol>
<h2>Report details</h2>
<dl><dt>Category</dt><dd>{_esc(f['category'])}</dd><dt>Basis</dt><dd>{_esc(f['basis'])}</dd>
<dt>Date of incident</dt><dd>{_esc(f['incident_date'])}</dd><dt>Filed elsewhere?</dt><dd>{_fill(f['filed_elsewhere'])}</dd></dl>
<h2>Person reporting</h2><div class="box">{_fill(f['reporter'])}</div>
<h2>Respondent</h2><div class="box">{_fill(f['respondent'])}</div>
<h2>What happened</h2><div class="box">{_fill(f['description'])}</div>
{f'<h2>What happened ({_esc(tr["language"])}, for the client)</h2><div class="box" lang="{_esc(tr["language"])}">{_fill(tr["text"])}</div>' if tr else ''}
<h2>Evidence</h2><ul>{''.join(f'<li>{_fill(e)}</li>' for e in d.evidence)}</ul>
<h2>Before submitting</h2><ul class="check">{''.join(f'<li>{_esc(c)}</li>' for c in d.blocking + d.review_checklist)}</ul>
{'<h2>Notes</h2><ul>' + ''.join(f'<li>{_esc(w)}</li>' for w in d.warnings) + '</ul>' if d.warnings else ''}
<h2>How to submit (free, no lawyer needed)</h2>
<ul>{''.join(f"<li><b>{_esc(m['method'])}:</b> {_esc(m['detail'])}</li>" for m in d.agency['filing'])}</ul>
<p>{'<br>'.join(_esc(n) for n in d.agency['notes'])}</p>
<p><b>Deadline:</b> {_esc(d.deadline)} ({_esc(d.agency['deadline_note'])})</p>
</main></body></html>"""
