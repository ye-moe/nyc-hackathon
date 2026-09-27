"""Policy numbers the classifier reasons with.

These are approximations for the demo. Verify against current HRA / HUD
publications before quoting them to judges or putting them in a complaint.
"""

# Max monthly rent CityFHEPS will pay, by bedroom count. CityFHEPS has tracked
# the Section 8 payment standard since 2021; these are approx HUD FY2025 NYC FMRs.
CITYFHEPS_MAX_RENT = {
    0: 2387,
    1: 2440,
    2: 2748,
    3: 3433,
    4: 3698,
}

# Most generous annual income a CityFHEPS-eligible household can have
# (post-2023 expansion: 50% AMI; ~3-person household, approx 2025 AMI).
# We compare income requirements against the *most generous* ceiling so that
# "this requirement excludes every eligible family" is a conservative claim.
VOUCHER_INCOME_CEILING = 73000

# Flag thresholds. Precision matters more than recall: a false complaint
# against a lawful landlord costs the project its credibility with CHR.
FLAG_THRESHOLD = 0.80
REVIEW_THRESHOLD = 0.45

LEGAL_BASIS = (
    "NYC Admin. Code § 8-107(5)(a) — unlawful discrimination based on lawful "
    "source of income, including CityFHEPS, Section 8, and other rental assistance. "
    "NYC CHR guidance: income and credit requirements may be applied only to the "
    "portion of rent the tenant pays, not the portion covered by the subsidy."
)
