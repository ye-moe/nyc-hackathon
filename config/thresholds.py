# Extraction confidence below this means we don't trust the facts enough to
# call a violation; the verdict is downgraded to needs_review.
MIN_EXTRACTION_CONFIDENCE = 0.5

# "3x rent" means monthly income; "40x rent" means annual. Multipliers below
# this are read as monthly and converted (x12).
MONTHLY_MULTIPLIER_MAX = 10

# Credit minimums at or above this get an R3 review flag.
CREDIT_SCORE_REVIEW_AT = 650

# CCHR guidance treats employment-only requirements as a proxy for excluding
# voucher holders, but R3 stays "review" unless the guidance clearly supports a
# violation. Flip only after checking the guidance.
EMPLOYMENT_IS_VIOLATION = False

GEMINI_TIMEOUT_S = 20
