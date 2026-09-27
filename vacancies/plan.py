"""Open Doors deliverable: a Housing Plan a caseworker can hand to a client.

    from vacancies.plan import build_plan
    plan = build_plan(household_size=3, income=30000, has_voucher=True, voucher_type="CityFHEPS")

What it saves: checking every open lottery unit-by-unit against the household, tracking
deadlines, collecting documents, and writing to each voucher-friendly landlord.
Nothing is sent or submitted; letters have visible [placeholders] for a person to fill.
No client data is stored.
"""
from __future__ import annotations

import html as _html
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from pydantic import BaseModel

from config import cityfheps as C
from core.gemini import gemini_translate
from vacancies.feed import VOUCHER_INCOME_NOTE, FeedItem, build_feed

MAX_LOTTERIES = 8
MAX_LISTINGS = 6

# Commonly requested when applying for affordable housing and when leasing with a voucher.
# Each lottery and HRA confirm their own list; the plan says so.
CHECKLIST = [
    "Photo ID for every adult in the household",
    "Birth certificates or other proof of age for everyone in the household",
    "Social Security cards (or numbers) for everyone who has one",
    "Proof of all income: recent pay stubs, benefits award letters, child support, etc.",
    "Your voucher paperwork (e.g. CityFHEPS shopping letter or Section 8 voucher), if you have one",
    "Recent bank statements (lotteries have asset limits)",
    "A working phone number and email to receive notices",
]


class LotteryStep(BaseModel):
    id: str
    title: str
    address: Optional[str]
    borough: Optional[str]
    deadline: Optional[str]
    days_left: Optional[int]
    units: List[dict]                  # the units this household fits
    voucher_covers_some: bool
    apply_url: Optional[str]
    paper_application_address: Optional[str]
    checks: List[str]                  # why it fits


class ListingStep(BaseModel):
    id: str
    title: str
    rent: Optional[float]
    bedrooms: List[int]
    url: Optional[str]
    why: str
    letter: str                        # voucher introduction letter, for a person to review and send


class HousingPlan(BaseModel):
    id: str
    status: str = "draft_for_review"
    created_at: str
    household: dict
    headline: str
    lotteries: List[LotteryStep]
    listings: List[ListingStep]
    checklist: List[str]
    notes: List[str]
    calendar_ics: str                  # deadlines, importable into Google/Apple Calendar
    text: str                          # short version for a text message
    html: str                          # printable plan
    headline_translated: Optional[dict] = None


def usd(n) -> str:
    return f"${round(n):,}" if n is not None else "?"


def _bed(b) -> str:
    return "studio" if b == 0 else f"{b}-bedroom"


def _voucher_letter(item: FeedItem, voucher_type: str, household_size: Optional[int]) -> str:
    beds = item.bedrooms[0] if item.bedrooms else None
    limit = C.PAYMENT_STANDARD.get(min(beds, 4)) if beds is not None else None
    lines = [
        "[Date]",
        "",
        f"Re: {item.title}" + (f" ({item.url})" if item.url else ""),
        "",
        "Hello,",
        "",
        f"I'm writing about the apartment listed above. I'm helping a household"
        + (f" of {household_size}" if household_size else "")
        + f" that holds a {voucher_type} voucher and would like to see the apartment and apply.",
        "",
        "How the voucher works:",
        "- The rental assistance program pays its share of the rent directly to the landlord each month.",
        f"- The tenant pays their portion, generally about {round(C.TENANT_SHARE_OF_INCOME * 100)}% of household income.",
    ]
    if limit and item.rent and voucher_type.lower() == "cityfheps":
        lines.append(f"- For a {_bed(beds)}, CityFHEPS can cover rent up to about {usd(limit)} a month; "
                     f"this apartment is listed at {usd(item.rent)}.")
    lines += [
        "",
        "Could we schedule a viewing? I can answer questions about the voucher and the paperwork, which I'll help "
        "complete on the tenant's side.",
        "",
        "Thank you,",
        "[Your name], [Your organization]",
        "[Phone] · [Email]",
    ]
    return "\n".join(lines)


def _ics(lotteries: List[LotteryStep]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ev = []
    for l in lotteries:
        if not l.deadline:
            continue
        d = date.fromisoformat(l.deadline)
        esc = lambda s: re.sub(r"([,;\\])", r"\\\1", s)
        ev += ["BEGIN:VEVENT", f"UID:{l.id}@homeward-nyc", f"DTSTAMP:{stamp}",
               f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}",
               f"SUMMARY:{esc('Housing Connect deadline: ' + l.title)}",
               f"DESCRIPTION:{esc('Apply at ' + (l.apply_url or 'housingconnect.nyc.gov'))}",
               "BEGIN:VALARM", "TRIGGER:-P2D", "ACTION:DISPLAY", f"DESCRIPTION:{esc('2 days left: ' + l.title)}", "END:VALARM",
               "END:VEVENT"]
    return "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Homeward NYC//Housing Plan//EN", *ev, "END:VCALENDAR"]) + "\r\n"


def build_plan(household_size: Optional[int] = None, income: Optional[float] = None, has_voucher: bool = True,
               voucher_type: str = "CityFHEPS", bedrooms: Optional[int] = None, borough: Optional[str] = None,
               item_ids: Optional[List[str]] = None, client_language: Optional[str] = None) -> HousingPlan:
    feed = build_feed(borough=borough, bedrooms=bedrooms, household_size=household_size, income=income, has_voucher=has_voucher)
    items = feed.items
    if item_ids:
        wanted = set(item_ids)
        items = [i for i in items if i.id in wanted]

    lots: List[LotteryStep] = []
    for i in (x for x in items if x.kind == "lottery"):
        units = []
        for u in i.unit_offers:
            inc = u.get("income_by_household_size", {}).get(str(household_size)) if household_size else None
            units.append({"layout": u.get("layout"), "count": u.get("count"), "rent": u.get("rent") or None,
                          "income_range": inc, "voucher_covers_rent": u.get("rent_within_voucher_limit")})
        checks = []
        if household_size:
            checks.append(f"Household of {household_size} fits these unit sizes.")
        if income is not None:
            checks.append(f"Income of {usd(income)} is under the maximum" +
                          (" (minimum income may not apply with a voucher)." if has_voucher else " and above the minimum."))
        lots.append(LotteryStep(id=i.id, title=i.title, address=i.address, borough=i.borough, deadline=i.deadline,
                                days_left=i.days_left, units=units, voucher_covers_some=any(u["voucher_covers_rent"] for u in units),
                                apply_url=i.url, paper_application_address=i.paper_application_address, checks=checks))
    lots.sort(key=lambda l: l.deadline or "9999")
    lots = lots[:MAX_LOTTERIES]

    lists = [ListingStep(id=i.id, title=i.title, rent=i.rent, bedrooms=i.bedrooms, url=i.url, why=i.voucher_status,
                         letter=_voucher_letter(i, voucher_type, household_size))
             for i in items if i.kind == "listing"][:MAX_LISTINGS]

    first = lots[0] if lots else None
    headline = (f"Apply to {len(lots)} open lotter{'y' if len(lots) == 1 else 'ies'}"
                + (f" (first deadline {first.deadline}, {first.days_left} days)" if first and first.deadline else "")
                + (f" and contact {len(lists)} voucher-friendly landlord{'s' if len(lists) != 1 else ''}" if lists else "")
                + ".") if (lots or lists) else "No open lotteries or voucher-friendly listings fit this household right now."
    notes = [VOUCHER_INCOME_NOTE if has_voucher else "Lottery income limits are shown for this household size.",
             "Check each lottery's own requirements on Housing Connect before applying; the document list is a starting point.",
             "Letters are drafts: a person reviews, fills in the [placeholders], and sends them. Nothing is sent automatically."]

    translated = None
    if client_language and client_language != "en":
        t = gemini_translate([headline], client_language)
        if t:
            translated = {"language": client_language, "text": t[0]}

    plan = HousingPlan(id=str(uuid.uuid4()), created_at=datetime.now(timezone.utc).isoformat(),
                       household={"size": household_size, "income": income, "has_voucher": has_voucher,
                                  "voucher_type": voucher_type if has_voucher else None, "bedrooms": bedrooms, "borough": borough},
                       headline=headline, lotteries=lots, listings=lists, checklist=CHECKLIST, notes=notes,
                       calendar_ics=_ics(lots), text="", html="", headline_translated=translated)
    plan.text = _text(plan)
    plan.html = _page(plan)
    return plan


def _text(p: HousingPlan) -> str:
    lines = [p.headline]
    for l in p.lotteries[:5]:
        lines.append(f"• {l.title}: apply by {l.deadline} at {l.apply_url}")
    for s in p.listings[:3]:
        lines.append(f"• Listing: {s.title[:60]} {usd(s.rent) + '/mo' if s.rent else ''}".rstrip())
    lines.append("Bring: ID for everyone, proof of income, your voucher paperwork.")
    return "\n".join(lines)


def _esc(s) -> str:
    return _html.escape(str(s if s is not None else ""), quote=True)


def _unit_line(u: dict) -> str:
    rent = usd(u["rent"]) if u["rent"] else "rent set by income"
    s = f"{u['count']}× {u['layout']} · {rent}"
    return _esc(s + (" · voucher covers" if u["voucher_covers_rent"] else ""))


def _lottery_row(l: LotteryStep) -> str:
    where = _esc(l.address or "") + (" · " + _esc(l.borough) if l.borough else "")
    days = (_esc(l.days_left) + " days") if l.days_left is not None else ""
    paper = ("<br><span class=m>Paper: " + _esc(l.paper_application_address) + "</span>") if l.paper_application_address else ""
    return (f"<tr><td><b>{_esc(l.title)}</b><br><span class=m>{where}</span></td>"
            f"<td>{_esc(l.deadline or '—')}<br><span class=m>{days}</span></td>"
            f"<td>{'<br>'.join(_unit_line(u) for u in l.units)}</td>"
            f"<td><a href='{_esc(l.apply_url)}'>Apply</a>{paper}</td><td class=box>☐</td></tr>")


def _letter_block(s: ListingStep) -> str:
    meta = _esc(s.why) + (" · " + usd(s.rent) + "/mo" if s.rent else "")
    if s.url:
        meta += f" · <a href='{_esc(s.url)}'>listing</a>"
    body = re.sub(r"(\[[^\]]+\])", r"<span class=ph>\1</span>", _esc(s.letter))
    return f"<section class=letter><h3>{_esc(s.title)}</h3><p class=m>{meta}</p><pre>{body}</pre></section>"


def _page(p: HousingPlan) -> str:
    h = p.household
    who = ", ".join(x for x in [f"household of {h['size']}" if h["size"] else None,
                               f"income {usd(h['income'])}/yr" if h["income"] is not None else None,
                               f"{h['voucher_type']} voucher" if h["has_voucher"] else "no voucher"] if x)
    lot_rows = "".join(_lottery_row(l) for l in p.lotteries)
    letters = "".join(_letter_block(s) for s in p.listings)
    tr = p.headline_translated
    translated = f'<p class=m lang="{_esc(tr["language"])}">{_esc(tr["text"])}</p>' if tr else ""
    lot_table = ("<table><thead><tr><th>Lottery</th><th>Deadline</th><th>Units that fit</th><th>How</th><th>Done</th></tr></thead><tbody>"
                 + lot_rows + "</tbody></table>") if p.lotteries else "<p class=m>None right now.</p>"
    checklist = "".join(f"<li>{_esc(c)}</li>" for c in p.checklist)
    notes = "".join(f"<li>{_esc(n)}</li>" for n in p.notes)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Housing Plan</title><style>
:root{{--fg:#141619;--m:#555a63;--line:#dcdad4;--bg:#fff;--ph:#ececec}}
@media(prefers-color-scheme:dark){{:root{{--fg:#ededed;--m:#a3a7ad;--line:#2c3036;--bg:#111316;--ph:#2a2e33}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,"Segoe UI",sans-serif}}
main{{max-width:900px;margin:0 auto;padding:28px 18px 48px}}h1{{font-size:26px;margin:0 0 4px}}h2{{font-size:13px;letter-spacing:.14em;text-transform:uppercase;color:var(--m);margin:28px 0 8px}}
.m{{color:var(--m);font-size:13px}}.banner{{border:1px dashed var(--m);border-radius:10px;padding:12px 14px;margin:14px 0;font-weight:600}}
table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{text-align:left;vertical-align:top;padding:9px 6px;border-bottom:1px solid var(--line)}}th{{font-size:12px;color:var(--m);text-transform:uppercase;letter-spacing:.08em}}
.box{{font-size:18px;text-align:center}}ul.check{{list-style:none;padding:0}}ul.check li::before{{content:"☐  "}}
.letter{{border:1px solid var(--line);border-radius:10px;padding:14px;margin:12px 0}}.letter h3{{margin:0 0 4px;font-size:15px}}
pre{{white-space:pre-wrap;font:14px/1.55 -apple-system,"Segoe UI",sans-serif;margin:10px 0 0}}.ph{{background:var(--ph);border-radius:4px;padding:0 3px;font-weight:600}}
a{{color:inherit}}@media print{{a{{text-decoration:none}}}}
</style></head><body><main>
<p class=m>Homeward NYC · Housing Plan · draft for review · {_esc(p.created_at[:10])}</p>
<h1>Housing Plan</h1><p class=m>For a {_esc(who)}</p>
<div class=banner>{_esc(p.headline)}</div>
{translated}
<h2>Lotteries to apply to, soonest deadline first</h2>
{lot_table}
<h2>Documents to gather</h2><ul class=check>{checklist}</ul>
<h2>Voucher-friendly listings: letters ready to send</h2>{letters or "<p class=m>None right now.</p>"}
<h2>Notes</h2><ul>{notes}</ul>
</main></body></html>"""
