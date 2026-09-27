"""Shelter facts checked by hand. Checked 2026-09-26.

Sources:
  DHS  = nyc.gov/site/dhs (single-adults-applying, families-with-children-applying, adult-families pages)
  NCS  = Neighborhood Coalition for Shelter Street Sheets, April 2024 (ncsinc.org/get-info)
Where sources disagreed, the official DHS page wins (men's intake moved to 8 E. 3rd St;
NCS's April 2024 sheet still lists 30th St).
"""

# Shelters with published addresses, verified in sources above. Same shape as the
# research files in data/shelters/research/; merged by shelters/build_public.py.
SEED_SHELTERS = [
    {"name": "Franklin Shelter", "provider": "NYC Department of Homeless Services", "borough": "Bronx",
     "address": "1122 Franklin Avenue (near E. 166th St.), Bronx, NY", "phone": None,
     "facility_type": "Adult Shelter (women's intake)", "household": ["single"], "gender": ["woman"],
     "min_age": 18, "max_age": None, "populations": [],
     "access": "Walk in to apply, 24/7 (women's intake). DHS then assigns a shelter.",
     "dhs_directory_name": None, "source_url": "https://www.nyc.gov/site/dhs/shelter/singleadults/single-adults-applying.page",
     "source_type": "government", "quote": "Franklin Shelter, 1122 Franklin Avenue (near 166th Street) Bronx, NY"},
    {"name": "HELP Women's Center", "provider": "HELP USA", "borough": "Brooklyn",
     "address": "114 Snediker Avenue, Brooklyn, NY", "phone": None,
     "facility_type": "Adult Shelter (women's intake)", "household": ["single"], "gender": ["woman"],
     "min_age": 18, "max_age": None, "populations": [],
     "access": "Walk in to apply, 24/7 (women's intake). DHS then assigns a shelter.",
     "dhs_directory_name": "HELP Women's Center", "source_url": "https://www.nyc.gov/site/dhs/shelter/singleadults/single-adults-applying.page",
     "source_type": "government", "quote": "Help Women's Center, 114 Snediker Avenue Brooklyn, NY"},
    {"name": "Bowery Mission, Tribeca Campus", "provider": "The Bowery Mission", "borough": "Manhattan",
     "address": "90 Lafayette Street (btwn Walker & White Sts.), New York, NY", "phone": "212-226-6214",
     "facility_type": "Walk-in Shelter", "household": ["single"], "gender": ["man", "woman"],
     "min_age": 18, "max_age": None, "populations": ["mental_health", "substance_use"],
     "access": "Walk in or call. Intake daily: women 3–3:30pm, men 3:30–5pm, first come, first served. Up to 7 nights.",
     "dhs_directory_name": None, "source_url": "https://www.ncsinc.org/get-info (Downtown Street Sheet, April 2024)",
     "source_type": "operator", "quote": "Adult Men & Women: Bowery Mission Tribeca Campus 90 Lafayette St. (btwn Walker & White Sts.)"},
]

# How to get into a DHS shelter: apply at intake, then DHS assigns one.
INTAKE = {
    "single_man": "Apply at the Single Adult Intake Center, 8 E. 3rd Street, Manhattan. DHS then assigns you a shelter.",
    "single_woman": "Apply at Franklin Shelter, 1122 Franklin Ave., Bronx, or HELP Women's Center, 114 Snediker Ave., Brooklyn "
                    "(both 24/7). DHS then assigns you a shelter.",
    "single_any": "Apply at the intake center that matches your gender identity: men at 8 E. 3rd Street, Manhattan; women at "
                  "Franklin Shelter, 1122 Franklin Ave., Bronx, or HELP Women's Center, 114 Snediker Ave., Brooklyn. "
                  "DHS then assigns you a shelter.",
    "family_with_children": "Apply at PATH, 151 E. 151st Street, Bronx (open 24 hours; applications 9am–5pm), with ID for "
                            "everyone in your family. DHS then assigns your family a shelter.",
    "adult_family": "Apply together at Adult Family Intake, 400 E. 30th Street, Manhattan, with proof of your relationship "
                    "(e.g. original marriage or domestic-partnership certificate) and that you lived together 180 days in the "
                    "past year. DHS then assigns you a shelter.",
    "youth": "Youth shelters take young people directly; call ahead for a bed. City (DHS) shelters are for adults 18+ and families.",
    "returning": "You were in a DHS shelter in the last 12 months: go back to that same shelter.",
    "dv": "Domestic violence shelters are confidential and aren't listed here. They're reached only through the NYC "
          "domestic violence hotline: 800-621-4673.",
}


# What to bring and where to apply, by household type (DHS application pages, checked 2026-09-26).
DHS_PAGES = {
    "single": ("DHS: Single adults, applying for shelter", "https://www.nyc.gov/site/dhs/shelter/singleadults/single-adults-applying.page"),
    "family_with_children": ("DHS: Families with children, applying for shelter", "https://www.nyc.gov/site/dhs/shelter/families/families-with-children-applying.page"),
    "adult_family": ("DHS: Adult families, who qualifies", "https://www.nyc.gov/site/dhs/shelter/families/adult-families.page"),
}
WHAT_TO_BRING = {
    "single": ["ID helps but isn't required: driver's license, state ID, passport, Social Security card, or Medicaid card.",
               "Your most recent pay stub, if you work."],
    "family_with_children": ["ID for everyone in the household: photo ID with proof of age, birth certificates, Social Security cards, "
                             "Medicaid cards, or a Public Assistance ID card.",
                             "Your most recent pay stub, if you work."],
    "adult_family": ["Original marriage certificate or domestic-partnership certificate, or documents proving a family, caretaking, "
                     "or medical-dependence relationship.",
                     "Proof you lived together for 180 days in the year before applying."],
    "youth_alone": ["Call ahead for a bed. Bring any ID you have."],
}


# The doors into DHS shelter, by household. Sources: DHS applying pages (addresses, rules), NCS Street Sheets
# April 2024 (hours, subway). Checked 2026-09-26.
INTAKE_CENTERS = {
    "single_man": [{"name": "Single Adult Intake Center (men)", "address": "8 E. 3rd Street, New York, NY 10003",
                    "hours": "Call 311 to confirm hours", "transit": None, "phone": "311", "source": "DHS"}],
    "single_woman": [
        {"name": "Franklin Shelter (women's intake)", "address": "1122 Franklin Avenue (near E. 166th St.), Bronx, NY",
         "hours": "Open 24/7", "transit": "2, 4, 5 to 149th St., then #55 bus to 166th St. & 3rd Ave.", "phone": "311", "source": "DHS, NCS"},
        {"name": "HELP Women's Center (women's intake)", "address": "114 Snediker Avenue, Brooklyn, NY",
         "hours": "Open 24/7", "transit": "C to Liberty Ave.", "phone": "311", "source": "DHS, NCS"}],
    "family_with_children": [{"name": "PATH (Prevention Assistance and Temporary Housing)", "address": "151 E. 151st Street (at Walton Ave.), Bronx, NY",
                              "hours": "Open 24 hours; applications 9am–5pm", "transit": "2, 4, 5 to 149th St.", "phone": "718-503-6400",
                              "source": "DHS, NCS"}],
    "adult_family": [{"name": "Adult Family Intake (30th Street)", "address": "400 E. 30th Street (at 1st Ave.), Manhattan",
                      "hours": "Open 24/7 (confirm with 311)", "transit": "6 to 28th St.", "phone": "311", "source": "NCS; confirm with 311"}],
}
