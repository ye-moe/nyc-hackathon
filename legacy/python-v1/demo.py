"""Terminal demo: python demo.py   (add --llm to include Claude)"""
import sys

from vdd.classifier import classify
from vdd.schema import Listing

RED, YEL, GRN, DIM, BOLD, END = "\033[91m", "\033[93m", "\033[92m", "\033[2m", "\033[1m", "\033[0m"

EXAMPLES = [
    Listing("1", "Sunny 1BR in Crown Heights, $2,200/mo. Must earn 40x the rent. No pets.", "streeteasy", rent=2200, bedrooms=1),
    Listing("2", "Section 8 welcome! Sorry, no CityFHEPS.", "craigslist", rent=2500, bedrooms=2),
    Listing("3", "Apartamento de 2 cuartos en Washington Heights. No aceptamos programas.", "facebook", rent=2400, bedrooms=2),
    Listing("4", "Spacious 2BR in Astoria. No broker fee! No pets. No smoking.", "streeteasy", rent=2600, bedrooms=2),
    Listing("5", "3BR Canarsie. 40x rent income required. Vouchers accepted, income requirement applies to tenant portion only.", "streeteasy", rent=3200, bedrooms=3),
    Listing("6", "Quiet building, working professionals only.", "craigslist", rent=2250, bedrooms=1),
]


def highlight(text, evidence):
    spans = sorted({(e.start, e.end) for e in evidence if e.start >= 0}, reverse=True)
    for s, e in spans:
        text = text[:s] + BOLD + RED + text[s:e] + END + text[e:]
    return text


if __name__ == "__main__":
    use_llm = "--llm" in sys.argv
    for l in EXAMPLES:
        c = classify(l, use_llm=use_llm)
        color = {"discriminatory": RED, "needs_review": YEL, "clean": GRN}[c.label]
        print(f"\n{color}{BOLD}{c.label.upper():15s}{END} conf={c.confidence:.2f}  [{l.source}]  {DIM}{c.category}{END}")
        print("  " + highlight(l.text, c.evidence))
        for r in c.reasons:
            print(f"  {DIM}- {r}{END}")
