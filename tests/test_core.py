"""python -m unittest discover tests   (offline; no API keys needed)"""
import unittest

from core import analyze, approve_draft, build_packet, draft_complaint


def run(text, hints=None):
    return analyze({"text": text, "hints": hints}, use_gemini=False)


class R1Exclusions(unittest.TestCase):
    def test_flags_no_programs_with_clause_as_evidence(self):
        r = run("Nice 1BR. NO VOUCHERS. Call now.")
        self.assertEqual(r.verdict, "violation")
        f = next(f for f in r.flags if f.rule_id == "R1")
        self.assertEqual(r.analyzed_text[f.span[0]:f.span[1]], "NO VOUCHERS")

    def test_lawful_no_phrases_are_not_refusals(self):
        for t in ["No broker fee! No pets. No smoking.", "No program fee for voucher holders.", "No program needed to apply."]:
            self.assertEqual(run(t).verdict, "no_issue_found", t)

    def test_welcoming_one_program_doesnt_excuse_refusing_another(self):
        self.assertEqual(run("Section 8 welcome! Sorry, no CityFHEPS.").verdict, "violation")

    def test_misspellings(self):
        self.assertEqual(run("no progams, no vouchars").verdict, "violation")

    def test_spanish_chinese_russian(self):
        for t in ["No aceptamos programas.", "不接受政府补助", "Без программ."]:
            self.assertEqual(run(t).verdict, "violation", t)


class R2Income(unittest.TestCase):
    def test_math_and_full_rent_flag(self):
        f = next(f for f in run("1BR $2,200/mo. Must earn 40x the rent.").flags if f.rule_id == "R2")
        self.assertEqual(f.severity, "violation")
        self.assertEqual(f.calculation.required_annual_income, 88000)
        self.assertEqual(f.calculation.lawful_annual_income, 24000)
        self.assertTrue(f.calculation.excludes_every_eligible_household)
        self.assertIn("40 × $2,200 = $88,000", " ".join(f.calculation.steps))

    def test_3x_monthly_converts_to_annual(self):
        f = next(f for f in run("Studio $2,000/month. Applicants need 3x rent in monthly income.").flags if f.rule_id == "R2")
        self.assertEqual(f.calculation.required_annual_income, 72000)

    def test_tenant_share_carve_out_is_lawful(self):
        r = run("40x rent. Vouchers accepted; income requirement applies to tenant portion only.", {"monthly_rent": 2300, "bedrooms": 1})
        self.assertEqual(r.verdict, "no_issue_found")

    def test_government_income_bands_are_lawful(self):
        r = run("Housing Connect lottery, 60% AMI, income between $45,000 and $78,000", {"monthly_rent": 1650, "bedrooms": 1})
        self.assertEqual(r.verdict, "no_issue_found")

    def test_rent_above_payment_standard_is_review(self):
        self.assertEqual(run("Luxury 2BR, $9,500/mo, 40x rent income required.").verdict, "needs_review")

    def test_unknown_rent_is_review(self):
        self.assertEqual(run("Must earn 40x the rent.").verdict, "needs_review")


class R3R4(unittest.TestCase):
    def test_employment_requirement_is_review_by_default(self):
        self.assertEqual(run("Working professionals only.").verdict, "needs_review")

    def test_r4_reports_voucher_range_without_flagging(self):
        r = run("Sunny 2BR, $2,500/mo. Contact for showing.")
        self.assertEqual(r.verdict, "no_issue_found")
        self.assertTrue(r.within_voucher_range)


class Graceful(unittest.TestCase):
    def test_unreadable_image_without_gemini(self):
        r = analyze({"image": {"base64": "AAAA", "mime_type": "image/png"}}, use_gemini=False)
        self.assertEqual(r.verdict, "needs_review")
        self.assertIn("Couldn't read the image", " ".join(r.notes))


class Packet(unittest.TestCase):
    def test_summary_and_html(self):
        p = build_packet(run("1BR $2,200/mo. Must earn 40x the rent. No programs."), packet_url="https://example.org/p/1")
        self.assertIn("No programs", p.summary_text)
        self.assertIn("$88,000", p.summary_text)
        self.assertIn("https://example.org/p/1", p.summary_text)
        self.assertIn("<mark>No programs</mark>", p.html)
        self.assertIn("8-107(5)(a)", p.html)
        self.assertIn("311", p.html)

    def test_html_escapes_listing_text(self):
        self.assertNotIn("<script>alert", build_packet(run("<script>alert(1)</script> no programs")).html)


LISTING = "Sunny 1BR at 512 Halsey St, Brooklyn 11233. $2,200/mo. Must earn 40x the rent. No programs. Call Dave (718) 555-0142."


class Complaint(unittest.TestCase):
    def test_refuses_clean_listing(self):
        with self.assertRaises(ValueError):
            draft_complaint(run("Nice 2BR, $2,500. No pets."))

    def test_fills_cchr_form_in_order(self):
        d = draft_complaint(run(LISTING), listing={"source": "Craigslist", "url": "https://example.org/l/1",
                                                   "seen_on": "2026-09-25T15:00:00Z", "screenshot_saved": True})
        get = lambda f: next(a for a in d.form if a.field.startswith(f))
        self.assertEqual(d.form[0].field, "Your Name")
        self.assertEqual(get("Category").answer, "Housing or Lending Practices")
        self.assertEqual(get("Name of the person").answer, "Dave")
        self.assertEqual(get("Phone number").answer, "(718) 555-0142")
        self.assertIn("512 Halsey St", get("Address or general").answer)
        self.assertEqual(get("Date of most recent").answer, "09/25/2026")
        self.assertIn('The listing states: "No programs." This refuses', get("Please explain").answer)
        self.assertIn("$88,000", get("Please explain").answer)
        self.assertEqual(get("How did you hear").answer, "Social services")

    def test_never_pre_answers_what_only_the_person_can(self):
        d = draft_complaint(run(LISTING))
        for f in ["Your Name", "Your Email", "Have you filed a complaint with us before?", "Acknowledgement"]:
            a = next(x for x in d.form if x.field.startswith(f))
            self.assertEqual(a.answer, "")
            self.assertEqual(a.source, "you")

    def test_draft_until_approved_and_approval_sends_nothing(self):
        d = draft_complaint(run(LISTING))
        self.assertEqual(d.status, "draft_needs_review")
        self.assertIn("Nothing has been sent", d.text)
        a = approve_draft(d, "Myra")
        self.assertEqual(a.status, "approved_by_human")
        self.assertIn("Not submitted", a.text)
        with self.assertRaises(ValueError):
            approve_draft(d, " ")

    def test_missing_facts_block_and_deadline_one_year(self):
        d = draft_complaint(run("No vouchers."), listing={"seen_on": "2026-09-25T15:00:00Z"})
        joined = " ".join(d.blocking)
        self.assertIn("landlord, broker, or management company name", joined)
        self.assertIn("screenshot", joined)
        self.assertEqual(d.deadline, "2027-09-25")

    def test_state_option_three_year_deadline(self):
        d = draft_complaint(run(LISTING), agency="nysdhr", listing={"seen_on": "2026-09-25T15:00:00Z"})
        self.assertEqual(d.deadline, "2029-09-25")
        self.assertEqual(d.agency["name"], "NYS Division of Human Rights")

    def test_html_escapes(self):
        self.assertNotIn("<img src=x", draft_complaint(run("<img src=x onerror=alert(1)> no programs")).html)


if __name__ == "__main__":
    unittest.main()
