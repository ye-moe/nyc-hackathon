"""Shelter Match deliverable: an Intake Ready Packet a caseworker can print or text to a client.

    from shelters.packet import build_intake_packet
    from shelters.match import Profile
    build_intake_packet(Profile(household="single", age=34, gender="woman"), client_language="es")

What it saves: looking up the right intake door, hours, and subway; assembling the document
list for this household type; picking a shortlist; explaining rights and what to do if denied;
and writing it all in the client's language. No client data is stored.
"""
from __future__ import annotations

import html as _html
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel

from core.gemini import gemini_translate
from shelters.access_points import INTAKE, INTAKE_CENTERS, WHAT_TO_BRING
from shelters.match import Profile, _household, doubt_note, match

SHORTLIST = 5
# Short "bring" line for the text-message version.
SMS_BRING = {
    "single": "any ID you have, a recent pay stub if you work, your medications",
    "family_with_children": "ID and birth certificates for everyone, Social Security or Medicaid cards, a recent pay stub",
    "adult_family": "your marriage or domestic-partnership certificate (or proof of relationship) and proof you lived together",
    "youth_alone": "any ID you have",
}
LEGAL_AID = "Legal Aid Society Homeless Rights Project: 800-649-9125 (Mon–Fri 10am–3pm)"
DV_HOTLINE = "NYC domestic violence hotline (Safe Horizon): 800-621-4673, 24/7. DV shelters are confidential and placed through this line."


class IntakePacket(BaseModel):
    id: str
    status: str = "ready_to_share"
    created_at: str
    first_step: str
    go_to: List[dict]              # intake door(s): name, address, hours, transit, phone
    bring: List[str]
    shortlist: List[dict]          # top matching shelters with address + how to get in
    rights: List[str]
    if_denied: List[str]
    urgent: List[str]
    sms_bring: str = ""
    text: str                      # SMS-length version
    html: str                      # printable one-pager
    translated: Optional[dict] = None


LANG_NAMES = {"es": "Español", "zh": "中文", "ru": "Русский", "bn": "বাংলা", "ht": "Kreyòl ayisyen", "ar": "العربية", "fr": "Français"}
HEADINGS = ["Your next step", "Where to go", "What to bring", "Shelters that fit you", "Your rights", "If you're denied"]


def _door_key(p: Profile, hh: str) -> Optional[str]:
    if hh == "single":
        return {"man": "single_man", "woman": "single_woman"}.get(p.gender)
    return hh if hh in INTAKE_CENTERS else None


def build_intake_packet(p: Profile, shelter_ids: Optional[List[str]] = None, client_language: Optional[str] = None) -> IntakePacket:
    hh = _household(p)
    m = match(p)
    # Intake door: one door for known gender/household; both men's and women's doors for nonbinary/unspecified
    # singles (they choose by gender identity); none for youth (youth shelters take people directly).
    key = _door_key(p, hh)
    if hh == "youth_alone" or p.in_dhs_shelter_last_12_months and hh in ("single", "adult_family"):
        go_to = []
    elif key:
        go_to = INTAKE_CENTERS[key]
    elif hh == "single":
        go_to = INTAKE_CENTERS["single_man"] + INTAKE_CENTERS["single_woman"]
    else:
        go_to = []

    pool = [s for s in m.shelters if not shelter_ids or s.id in shelter_ids]
    if hh == "single" and p.gender not in ("man", "woman"):
        # Choosing by gender identity: LGBTQ+-focused and mixed-gender shelters first.
        pool.sort(key=lambda s: (0 if "lgbtq" in s.populations else 1 if not s.serves.startswith(("Men (", "Women (")) else 2))
    picks = pool[:SHORTLIST]
    shortlist = [{"name": s.name, "address": s.address, "phone": s.phone, "serves": s.serves, "how": s.access,
                  "walk_in": s.walk_in, "confirm": s.details.get("confirm"), "caveat": doubt_note(s.details.get("caveats"))} for s in picks]

    bring = list(WHAT_TO_BRING.get(hh, []))
    if hh == "single":
        bring.append("Any medications and prescriptions")
    rights = [
        "Shelter is a right in New York City for people who are homeless.",
        "You can use single-sex shelter that matches your gender identity (NYC Human Rights Law).",
        "You can ask intake for a disability accommodation (accessible room, elevator, bathroom).",
    ]
    if_denied = ["Ask for the decision in writing.", LEGAL_AID, "Call 311 for shelter directions and street outreach, 24/7."]
    if hh == "family_with_children":
        if_denied.insert(1, "Families found ineligible have 60 days to request a Fair Hearing. DHS may place the family for up "
                            "to 10 days while it checks eligibility.")
    urgent = [DV_HOTLINE] if p.fleeing_violence else []

    first = m.how_to_get_in
    if p.fleeing_violence:   # the hotline is already the urgent line; don't say it twice
        first = first.replace(INTAKE["dv"], "").strip() or first
    pk = IntakePacket(id=str(uuid.uuid4()), created_at=datetime.now(timezone.utc).isoformat(), first_step=first,
                      go_to=go_to, bring=bring, shortlist=shortlist, rights=rights, if_denied=if_denied, urgent=urgent,
                      sms_bring=SMS_BRING.get(hh, "any ID you have"), text="", html="")

    if client_language and client_language != "en":
        items = [*HEADINGS, pk.first_step, *pk.bring, *pk.rights, *pk.if_denied]
        t = gemini_translate(items, client_language)
        if t:
            h = len(HEADINGS)
            n1, n2 = h + 1 + len(pk.bring), h + 1 + len(pk.bring) + len(pk.rights)
            pk.translated = {"language": client_language, "language_name": LANG_NAMES.get(client_language, client_language),
                             "headings": dict(zip(HEADINGS, t[:h])), "first_step": t[h],
                             "bring": t[h + 1:n1], "rights": t[n1:n2], "if_denied": t[n2:]}
    pk.text = _text(pk)
    pk.html = _page(pk)
    return pk


def _text(pk: IntakePacket) -> str:
    lines = [*pk.urgent, pk.first_step]
    for d in pk.go_to[:2]:
        lines.append(f"• {d['name']}: {d['address']} ({d['hours']})")
    lines.append("Bring: " + pk.sms_bring + ".")
    lines.append("Denied? Legal Aid 800-649-9125. Directions: 311.")
    return "\n".join(lines)


def _e(s) -> str:
    return _html.escape(str(s if s is not None else ""), quote=True)


def _li(xs) -> str:
    return "".join(f"<li>{_e(x)}</li>" for x in xs)


def _door(d: dict) -> str:
    extra = "".join(f"<br><span class=m>{_e(x)}</span>" for x in [d.get("hours"), ("Subway: " + d["transit"]) if d.get("transit") else None,
                                                                  ("Phone: " + d["phone"]) if d.get("phone") else None] if x)
    return f"<div class=door><b>{_e(d['name'])}</b><br>{_e(d['address'])}{extra}<br><span class=m>Source: {_e(d.get('source'))}</span></div>"


def _short(s: dict) -> str:
    tag = ("Walk-in / call" if s["walk_in"] else "Referral from street outreach (311)" if "outreach" in (s["how"] or "").lower()
           else "Assigned after intake")
    warn = "".join(f"<br><span class=m>{_e(x)}</span>" for x in (s.get("confirm"), s.get("caveat")) if x)
    phone = f" · {_e(s['phone'])}" if s.get("phone") else ""
    return f"<li><b>{_e(s['name'])}</b> · {_e(tag)}<br>{_e(s['address'])}{phone}<br><span class=m>{_e(s['serves'])}</span>{warn}</li>"


def _page(pk: IntakePacket) -> str:
    tr = pk.translated
    tr_block = ""
    if tr:
        hd = tr["headings"]
        denied_h = hd["If you're denied"]
        tr_block = (f"<section lang='{_e(tr['language'])}' class=tr><h2>{_e(tr['language_name'])}</h2>"
                    f"<h3>{_e(hd['Your next step'])}</h3><p><b>{_e(tr['first_step'])}</b></p>"
                    f"<h3>{_e(hd['What to bring'])}</h3><ul class=check>{_li(tr['bring'])}</ul>"
                    f"<h3>{_e(hd['Your rights'])}</h3><ul>{_li(tr['rights'])}</ul>"
                    f"<h3>{_e(denied_h)}</h3><ul>{_li(tr['if_denied'])}</ul></section>")
    urgent = "".join(f"<div class=urgent>{_e(u)}</div>" for u in pk.urgent)
    doors = "".join(_door(d) for d in pk.go_to) or "<p class=m>See the first step above.</p>"
    shortlist = "".join(_short(s) for s in pk.shortlist) or "<li class=m>No listed shelter fits; use the intake step.</li>"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Intake Ready Packet</title><style>
:root{{--fg:#141619;--m:#555a63;--line:#dcdad4;--bg:#fff}}
@media(prefers-color-scheme:dark){{:root{{--fg:#ededed;--m:#a3a7ad;--line:#2c3036;--bg:#111316}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15.5px/1.55 -apple-system,"Segoe UI",sans-serif}}
main{{max-width:760px;margin:0 auto;padding:26px 18px 48px}}h1{{font-size:26px;margin:0 0 6px}}
h2{{font-size:12.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--m);margin:26px 0 8px}}h3{{font-size:14px;margin:14px 0 4px}}
.m{{color:var(--m);font-size:13px}}.first{{border:2px solid var(--fg);border-radius:10px;padding:12px 14px;font-weight:600;font-size:16.5px}}
.urgent{{border:2px dashed var(--fg);border-radius:10px;padding:10px 14px;margin-bottom:10px;font-weight:600}}
.door{{border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:8px 0}}
ul.check{{list-style:none;padding:0}}ul.check li::before{{content:"☐  "}}li{{margin:5px 0}}
.tr{{border-top:1px solid var(--line);margin-top:28px;padding-top:6px}}
</style></head><body><main>
<p class=m>Homeward NYC · Intake Ready Packet · {_e(pk.created_at[:10])} · nothing you entered is saved</p>
<h1>Your next step</h1>{urgent}<div class=first>{_e(pk.first_step)}</div>
<h2>Where to go</h2>{doors}
<h2>What to bring</h2><ul class=check>{_li(pk.bring)}</ul>
<h2>Shelters that fit you</h2><ul>{shortlist}</ul>
<h2>Your rights</h2><ul>{_li(pk.rights)}</ul>
<h2>If you're denied</h2><ul>{_li(pk.if_denied)}</ul>
{tr_block}
</main></body></html>"""
