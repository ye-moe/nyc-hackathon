"""python demo.py  ->  terminal walkthrough; writes a packet and a complaint draft to data/cache/"""
from pathlib import Path

from core import analyze, build_packet, draft_complaint

RED, YEL, GRN, DIM, B, X = "\033[91m", "\033[93m", "\033[92m", "\033[2m", "\033[1m", "\033[0m"
COLOR = {"violation": RED, "needs_review": YEL, "no_issue_found": GRN}
OUT = Path(__file__).resolve().parent / "data" / "cache"
OUT.mkdir(parents=True, exist_ok=True)

LISTINGS = [
    "Sunny 1BR in Crown Heights, $2,200/mo. Must earn 40x the rent. No pets.",
    "Section 8 welcome! Sorry, no CityFHEPS. 2BR $2,500.",
    "Apartamento de 2 cuartos en Washington Heights. No aceptamos programas. $2,400 al mes.",
    "Spacious 2BR in Astoria, $2,600. No broker fee! No pets. No smoking.",
    "3BR Canarsie $3,200. 40x rent income required. Vouchers accepted, income requirement applies to tenant portion only.",
    "Quiet building, working professionals only. 1BR $2,250.",
]

for text in LISTINGS:
    r = analyze({"text": text})
    print(f"\n{COLOR[r.verdict]}{B}{r.verdict.upper()}{X}  {DIM}({r.extractor}){X}\n  {text}")
    for f in (f for f in r.flags if f.severity != "info"):
        print(f'  {B}{f.rule_id}{X} "{f.evidence_text}": {DIM}{f.explanation}{X}')
        for i, s in enumerate(f.calculation.steps if f.calculation else [], 1):
            print(f"     {i}. {s}")

r = analyze({"text": LISTINGS[0] + " No programs."})
p = build_packet(r, tenant_language="es")
(OUT / "demo-packet.html").write_text(p.html)
print(f"\n{B}iMessage reply:{X}\n{p.summary_text}")
print(f"\npacket -> data/cache/demo-packet.html {'(EN + ES)' if p.translated else '(English only: Gemini key missing or out of quota)'}")

listing = "Sunny 1BR at 512 Halsey St, Brooklyn 11233. $2,200/mo. Must earn 40x the rent. No programs. Call Dave (718) 555-0142."
d = draft_complaint(analyze({"text": listing}), listing={"source": "Craigslist", "url": "https://newyork.craigslist.org/example",
                                                         "screenshot_saved": True},
                    reporter={"role": "caseworker"}, tenant_language="es")
(OUT / "demo-complaint.html").write_text(d.html)
(OUT / "demo-complaint.txt").write_text(d.text)
print("complaint draft -> data/cache/demo-complaint.html (+ .txt)  [draft for human review; nothing sent]")
