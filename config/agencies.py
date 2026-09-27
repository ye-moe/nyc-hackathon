"""Where a reviewed complaint can go. Sourced 2026-09-26 from:
  https://www.nyc.gov/site/cchr/enforcement/complaint-process.page
  https://www.nyc.gov/site/cchr/about/report-discrimination.page
  https://dhr.ny.gov/report
Re-check before the demo."""

AGENCIES = {
    "cchr": {
        "id": "cchr",
        "name": "NYC Commission on Human Rights",
        "law": "NYC Human Rights Law, NYC Admin. Code § 8-107(5) (lawful source of income)",
        "deadline_years": 1,
        "deadline_note": "within one year of the last alleged act of discrimination",
        "form_url": "nyc.gov/site/cchr/about/report-discrimination.page",
        "filing": [
            {"method": "Online report", "detail": "nyc.gov/site/cchr/about/report-discrimination.page (category: Housing or Lending Practices)"},
            {"method": "Phone", "detail": "311, or (212) 416-0197"},
            {"method": "In person", "detail": "22 Reade Street, Manhattan (bring photo ID)"},
        ],
        "form_category": "Housing or Lending Practices",
        "notes": [
            "The online form is a report, not yet an official complaint. The Commission's Law Enforcement Bureau follows up.",
            "Free. No lawyer needed.",
            "The Commission can't take a complaint already filed with another court or agency on the same facts.",
        ],
    },
    "nysdhr": {
        "id": "nysdhr",
        "name": "NYS Division of Human Rights",
        "law": "NYS Human Rights Law, Executive Law § 296(5) (lawful source of income)",
        "deadline_years": 3,
        "deadline_note": "within three years of the most recent incident (for incidents on or after Feb 15, 2024)",
        "form_url": "webapps.dhr.ny.gov/discrimination-report",
        "filing": [
            {"method": "Online report", "detail": "webapps.dhr.ny.gov/discrimination-report"},
            {"method": "Phone", "detail": "(844) 697-3471"},
        ],
        "form_category": "Housing",
        "notes": [
            "The online report is not yet an official complaint. The Division reviews it, then helps file one.",
            "Free. No lawyer needed.",
            "Use this if the one-year NYC deadline has passed. Don't file the same facts with both agencies.",
        ],
    },
}
