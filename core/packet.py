"""Evidence packet: what a tenant or caseworker takes away. Never auto-filed;
a person decides what to do with it."""
from __future__ import annotations

import html as _html
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from config import cityfheps as C
from core.gemini import gemini_translate
from core.schema import AnalysisResult, Flag

SUPPORTED_LANGUAGES = {"en": "English", "es": "Español", "bn": "বাংলা", "zh": "中文", "ru": "Русский"}

HEADLINE = {
    "violation": "This listing likely breaks NYC law by excluding voucher holders.",
    "needs_review": "This listing has terms that may exclude voucher holders. A person should take a closer look.",
    "no_issue_found": "We didn't find anything in this listing that excludes voucher holders.",
}


class Packet(BaseModel):
    summary_text: str   # iMessage-friendly
    html: str           # self-contained shareable page
    language: str       # second language used, "en" if none
    translated: bool


def esc(s: str) -> str:
    return _html.escape(s, quote=True)


def _problems(r: AnalysisResult) -> List[Flag]:
    return [f for f in r.flags if f.severity != "info"]


def build_packet(r: AnalysisResult, tenant_language: Optional[str] = None, packet_url: Optional[str] = None,
                 listing_url: Optional[str] = None) -> Packet:
    src = r.extraction.source_language
    lang = tenant_language or (src if src in SUPPORTED_LANGUAGES else "en")
    flags = _problems(r)
    calc = next((f.calculation for f in flags if f.calculation), None)

    # Everything a tenant needs to read, in order, so one translation call covers it.
    english = [HEADLINE[r.verdict], *[f.explanation for f in flags], *(calc.steps if calc else []),
               C.LEGAL_SUMMARY, C.INCOME_RULE, *C.NEXT_STEPS]
    translated = gemini_translate(english, lang) if lang != "en" else None
    return Packet(summary_text=_summary(r, packet_url), html=_html_page(r, english, translated, lang, listing_url),
                  language=lang if translated else "en", translated=bool(translated))


def _summary(r: AnalysisResult, packet_url: Optional[str]) -> str:
    lines = [HEADLINE[r.verdict]]
    for f in _problems(r)[:3]:
        lines.append(f'• "{f.evidence_text}": {f.explanation.split(". ")[0].rstrip(".")}.')
    calc = next((f.calculation for f in _problems(r) if f.calculation and f.calculation.required_annual_income), None)
    if calc:
        lines.append("")
        lines.append(f"The math: the listing asks for ${calc.required_annual_income:,.0f}/yr. "
                     + (f"Applied lawfully to the tenant's share, it's ${calc.lawful_annual_income:,.0f}/yr." if calc.lawful_annual_income else ""))
    if r.notes:
        lines += ["", *r.notes]
    if packet_url:
        lines += ["", f"Full evidence packet: {packet_url}"]
    if r.verdict != "no_issue_found":
        lines.append("This is information, not legal advice. You decide whether to report it.")
    return "\n".join(lines)


def highlight(text: str, flags: List[Flag]) -> str:
    spans = sorted({f.span for f in flags if f.span})
    out, i = "", 0
    for s, e in spans:
        if s < i:
            continue
        out += esc(text[i:s]) + f"<mark>{esc(text[s:e])}</mark>"
        i = e
    return out + esc(text[i:])


def et(iso: str) -> str:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York")).strftime("%b %d, %Y %I:%M %p")


def _html_page(r: AnalysisResult, en: List[str], tr: Optional[List[str]], lang: str, listing_url: Optional[str]) -> str:
    flags = _problems(r)
    calc_flag = next((f for f in flags if f.calculation), None)
    n_steps = len(calc_flag.calculation.steps) if calc_flag else 0
    # Index layout of en/tr: headline, flag explanations, calc steps, law summary, income rule, next steps.
    at_flags, at_steps, at_law = 1, 1 + len(flags), 1 + len(flags) + n_steps

    def column(t: List[str], code: str) -> str:
        h = (lambda s: s) if code == "en" else (lambda s: "&nbsp;")
        parts = [f'<section lang="{code}"><h2 class="headline {r.verdict}">{esc(t[0])}</h2>']
        if flags:
            items = "".join(f'<li><q>{esc(f.evidence_text)}</q><br>{esc(t[at_flags + i])} <span class="rule">{f.rule_id}</span></li>'
                            for i, f in enumerate(flags))
            parts.append(f"<h3>{h('What we found')}</h3><ul>{items}</ul>")
        if n_steps:
            parts.append(f"<h3>{h('The math')}</h3><ol>{''.join(f'<li>{esc(s)}</li>' for s in t[at_steps:at_steps + n_steps])}</ol>")
        parts.append(f"<h3>{h('The law')}</h3><p>{esc(t[at_law])} <cite>{esc(C.LEGAL_CITATION)}</cite></p><p>{esc(t[at_law + 1])}</p>")
        parts.append(f"<h3>{h('What you can do')}</h3><ol>{''.join(f'<li>{esc(s)}</li>' for s in t[at_law + 2:])}</ol></section>")
        return "".join(parts)

    notes = "<br>".join(esc(n) for n in r.notes)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Evidence packet</title>
<style>
:root{{--bg:#fff;--fg:#111;--muted:#555;--line:#ddd;--bad:#b3261e;--warn:#8a5a00;--ok:#1e6b34;--mark:#ffe08a}}
@media (prefers-color-scheme:dark){{:root{{--bg:#121212;--fg:#f2f2f2;--muted:#b5b5b5;--line:#333;--bad:#ff8a80;--warn:#ffcc66;--ok:#8fd19e;--mark:#6b5500}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:18px/1.55 system-ui,-apple-system,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:24px 16px 48px}}
.cols{{display:grid;gap:32px;grid-template-columns:1fr}}@media(min-width:860px){{.cols.two{{grid-template-columns:1fr 1fr}}}}
h1{{font-size:1.1rem;color:var(--muted);font-weight:600;margin:0 0 4px}}h2{{font-size:1.5rem;line-height:1.3}}h3{{margin:28px 0 8px;font-size:1.05rem}}
.violation{{color:var(--bad)}}.needs_review{{color:var(--warn)}}.no_issue_found{{color:var(--ok)}}
q{{font-weight:700}}.rule{{font-size:.8rem;color:var(--muted);border:1px solid var(--line);border-radius:4px;padding:0 4px}}
li{{margin:6px 0}}cite{{color:var(--muted);font-style:normal;font-size:.9rem}}
.snapshot{{white-space:pre-wrap;border:1px solid var(--line);border-radius:8px;padding:16px;font-size:.95rem}}
mark{{background:var(--mark);color:inherit;padding:0 2px}}footer{{margin-top:32px;color:var(--muted);font-size:.9rem}}
</style></head><body><main>
<h1>Source-of-income evidence packet</h1>
<div class="cols {'two' if tr else ''}">{column(en, 'en')}{column(tr, lang) if tr else ''}</div>
<h3>Listing as analyzed</h3>
<div class="snapshot">{highlight(r.analyzed_text, r.flags)}</div>
<footer>
  {f'Source: <a href="{esc(listing_url)}">{esc(listing_url)}</a><br>' if listing_url else ''}
  Analyzed {esc(et(r.analyzed_at))} ET · packet {esc(r.id)} · extractor: {r.extractor}
  {'<br>' + notes if notes else ''}
  <br>Automated analysis. Not legal advice. Nothing has been filed; a person decides what to do next.
</footer>
</main></body></html>"""
