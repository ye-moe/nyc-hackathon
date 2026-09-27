"""python -m unittest discover tests"""
import re
import unittest

from shelters.match import Profile, doubt_note, match, public_shelters


def names(r):
    return [s.name for s in r.shelters]


class PublicShelterData(unittest.TestCase):
    def test_every_shelter_has_street_address_and_source(self):
        for s in public_shelters():
            self.assertRegex(s["address"], r"\d", s["name"])
            self.assertTrue(s["source_url"], s["name"])

    def test_no_domestic_violence_shelters(self):
        for s in public_shelters():
            self.assertIsNone(re.search(r"domestic violence", " ".join(map(str, s.values())), re.I), s["name"])


class ShelterMatch(unittest.TestCase):
    def test_single_woman_gets_womens_shelters_not_mens(self):
        r = match(Profile(household="single", age=34, gender="woman"))
        self.assertIn("HELP Women's Center", names(r))
        self.assertFalse(any(s.serves.startswith("Men (") for s in r.shelters))

    def test_single_man_excludes_womens_shelters_with_reason(self):
        r = match(Profile(household="single", age=40, gender="man"))
        self.assertNotIn("HELP Women's Center", names(r))
        self.assertTrue(any(e.name == "HELP Women's Center" and e.reason == "Women only." for e in r.not_eligible))

    def test_nonbinary_sees_both(self):
        r = match(Profile(household="single", age=30, gender="nonbinary"))
        self.assertIn("HELP Women's Center", names(r))
        self.assertIn("gender identity", r.how_to_get_in)

    def test_minor_alone_only_gets_youth_shelters(self):
        r = match(Profile(household="single", age=17))
        self.assertTrue(any(n.startswith("Covenant House") for n in names(r)))
        self.assertTrue(all("young people" in s.serves.lower() for s in r.shelters))
        self.assertTrue(any(e.reason == "Adults 18+ only." for e in r.not_eligible))

    def test_youth_shelter_needs_age_for_families(self):
        r = match(Profile(household="family_with_children"))
        self.assertFalse(any(n.startswith("Covenant House") for n in names(r)))

    def test_families_are_told_to_go_to_path(self):
        self.assertIn("PATH", match(Profile(household="family_with_children", age=30)).how_to_get_in)

    def test_dv_is_routed_to_hotline(self):
        r = match(Profile(household="single", age=30, gender="woman", fleeing_violence=True))
        self.assertIn("800-621-4673", r.how_to_get_in)

    def test_returning_within_12_months(self):
        self.assertIn("same shelter", match(Profile(household="single", age=40, in_dhs_shelter_last_12_months=True)).how_to_get_in)

    def test_needs_rank_first(self):
        r = match(Profile(household="single", age=40, gender="woman", needs=["mental_health"]))
        sure = [s for s in r.shelters if not doubt_note(s.details.get("caveats"))]
        ranked = [("mental_health" in s.populations) for s in sure]
        self.assertEqual(ranked, sorted(ranked, reverse=True))

    def test_possibly_closed_sites_rank_last(self):
        r = match(Profile(household="single", age=40, gender="woman"))
        flags = [bool(doubt_note(s.details.get("caveats"))) for s in r.shelters]
        self.assertEqual(flags, sorted(flags))

    def test_veteran_only_shelters_excluded_for_non_veterans(self):
        for s in public_shelters():
            if "veterans" in s["populations"]:
                r = match(Profile(household=s["household"][0], age=40, gender="man"))
                self.assertNotIn(s["name"], names(r))


if __name__ == "__main__":
    unittest.main()
