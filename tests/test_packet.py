"""python -m unittest discover tests   (offline; uses the local shelter list)"""
import unittest

from shelters.match import Profile
from shelters.packet import build_intake_packet


class IntakePacket(unittest.TestCase):
    def test_woman_gets_womens_intake_doors(self):
        k = build_intake_packet(Profile(household="single", age=34, gender="woman"))
        self.assertEqual({d["name"].split(" (")[0] for d in k.go_to}, {"Franklin Shelter", "HELP Women's Center"})
        self.assertTrue(k.shortlist)
        self.assertIn("800-649-9125", k.text)

    def test_family_goes_to_path_with_fair_hearing_rights(self):
        k = build_intake_packet(Profile(household="family_with_children", age=30))
        self.assertTrue(k.go_to[0]["name"].startswith("PATH"))
        self.assertTrue(any("Fair Hearing" in x for x in k.if_denied))
        self.assertIn("birth certificates", k.text)

    def test_dv_hotline_is_first_and_not_repeated(self):
        k = build_intake_packet(Profile(household="single", age=30, gender="woman", fleeing_violence=True))
        self.assertTrue(k.text.startswith("NYC domestic violence hotline"))
        self.assertEqual(k.text.count("800-621-4673"), 1)

    def test_youth_has_no_adult_intake_door(self):
        k = build_intake_packet(Profile(household="single", age=17))
        self.assertEqual(k.go_to, [])
        self.assertTrue(all("young people" in s["serves"].lower() for s in k.shortlist))

    def test_nonbinary_sees_both_doors_and_no_gendered_first_pick(self):
        k = build_intake_packet(Profile(household="single", age=30, gender="nonbinary"))
        self.assertEqual(len(k.go_to), 3)
        self.assertFalse(k.shortlist[0]["serves"].startswith(("Men (", "Women (")))

    def test_html_escapes(self):
        k = build_intake_packet(Profile(household="single", age=30, gender="man"))
        self.assertNotIn("<script", k.html)


if __name__ == "__main__":
    unittest.main()
