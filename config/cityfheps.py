"""CityFHEPS / legal parameters. EVERY number here is an approximation for the
demo. Verify against current HRA payment standards and CCHR guidance before
the pitch, and update VERIFIED_ON when you do."""

VERIFIED_ON = None  # e.g. "2026-09-26"

# Max monthly rent CityFHEPS pays, by bedroom count (tracks the Section 8
# payment standard; approx HUD FY2025 NYC FMR).
PAYMENT_STANDARD = {0: 2387, 1: 2440, 2: 2748, 3: 3433, 4: 3698}
# Payment standards shift yearly and the table is approximate; rents up to
# this factor above the standard still count as "in voucher range".
PAYMENT_STANDARD_SLACK = 1.1

# Share of household income a CityFHEPS tenant pays toward rent.
TENANT_SHARE_OF_INCOME = 0.3

# Illustrative household used to show the R2 math (family of 3, one part-time
# earner). Not a real person; label it as illustrative in the UI.
EXAMPLE_HOUSEHOLD = {"size": 3, "annual_income": 24000}

# Most generous income a CityFHEPS-eligible household can have (post-2023
# expansion, ~50% AMI for 3 people). Exceeding it excludes every eligible household.
INCOME_CEILING = 73000

LEGAL_CITATION = "NYC Admin. Code § 8-107(5)(a)"
LEGAL_SUMMARY = (
    "The NYC Human Rights Law makes it illegal for landlords, brokers, and agents to refuse "
    "a tenant because of their lawful source of income, including CityFHEPS, Section 8, and other rental assistance."
)
INCOME_RULE = (
    "Per NYC Commission on Human Rights guidance, income and credit requirements may only be applied "
    "to the portion of rent the tenant pays, not the portion the voucher covers."
)
NEXT_STEPS = [
    "Save this packet and a screenshot of the original listing.",
    "Report it to the NYC Commission on Human Rights: call 311 or (212) 416-0197, or go to nyc.gov/cchr.",
    "If you have a caseworker, share this packet with them.",
    "This packet is information, not legal advice. A person decides whether to file.",
]
