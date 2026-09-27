"""Run: python -m unittest discover tests"""
import json
import unittest
from pathlib import Path

from vdd.buildings import make_mock, score
from vdd.classifier import classify
from vdd.rules import classify_rules, income_analysis
from vdd.schema import Listing


def label(text, rent=None, bedrooms=None):
    return classify(Listing(id="t", text=text, rent=rent, bedrooms=bedrooms), use_llm=False).label


class TestRules(unittest.TestCase):
    def test_explicit_refusal(self):
        self.assertEqual(label("Nice 1BR. No programs."), "discriminatory")

    def test_no_fee_is_not_refusal(self):
        self.assertEqual(label("No broker fee, no pets."), "clean")
        self.assertEqual(label("No program fee for voucher holders."), "clean")

    def test_partial_acceptance_still_flags(self):
        self.assertEqual(label("Section 8 welcome! Sorry, no CityFHEPS."), "discriminatory")

    def test_income_math(self):
        inc = income_analysis("Must earn 40x the rent", 2200, 1)
        self.assertEqual(inc["required_annual_income"], 88000)
        self.assertTrue(inc["excludes_all_voucher_holders"])
        self.assertTrue(inc["rent_within_voucher_limit"])

    def test_three_x_monthly(self):
        inc = income_analysis("3x rent in monthly income", 2000, 0)
        self.assertEqual(inc["required_annual_income"], 72000)

    def test_income_carve_out_is_lawful(self):
        self.assertEqual(label("40x rent. Vouchers accepted; income requirement applies to tenant portion only.", 2300, 1), "clean")

    def test_government_band_is_lawful(self):
        self.assertEqual(label("Housing Connect lottery, 60% AMI, income between $45,000 and $78,000", 1650, 1), "clean")

    def test_evidence_span_points_at_text(self):
        text = "Great place. NO VOUCHERS. Call now."
        r = classify_rules(text)
        e = r.evidence[0]
        self.assertEqual(text[e.start:e.end].lower(), "no vouchers")

    def test_multilingual(self):
        self.assertEqual(label("No aceptamos programas."), "discriminatory")
        self.assertEqual(label("不接受政府补助"), "discriminatory")
        self.assertEqual(label("Без программ."), "discriminatory")

    def test_dev_set_precision_floor(self):
        rows = [json.loads(l) for l in (Path(__file__).parent.parent / "data/labeled_edge_cases.jsonl").read_text().splitlines()]
        fp = sum(1 for r in rows if r["label"] == 0 and label(r["text"], r["rent"], r["bedrooms"]) == "discriminatory")
        self.assertEqual(fp, 0, "a lawful listing in the dev set is being auto-flagged")


class TestBuildings(unittest.TestCase):
    def test_hostile_owners_rank_low(self):
        out = score(make_mock())
        hostile = out[out.owner.str.startswith("Parkline")].friendliness.mean()
        friendly = out[out.owner.str.startswith("Community")].friendliness.mean()
        self.assertLess(hostile, 0.4)
        self.assertGreater(friendly, 0.7)


if __name__ == "__main__":
    unittest.main()
