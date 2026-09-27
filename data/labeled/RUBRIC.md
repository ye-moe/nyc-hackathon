# Labeling rubric

Label each NYC rental listing with exactly one of `violation`, `needs_review`, `no_issue_found`.
Judge only what the listing text says. Humans and agents both label against this document.

## Law
- NYC Human Rights Law (Admin. Code § 8-107(5)(a)) makes it illegal to refuse a tenant because of their lawful
  source of income: CityFHEPS, Section 8 / Housing Choice Voucher, HASA, other rental assistance.
- NYC Commission on Human Rights guidance: income and credit requirements may only be applied to the portion of
  rent the tenant pays, not the portion the voucher covers.
- A CityFHEPS tenant typically pays 30% of household income; the voucher pays the rest.
- Approx. CityFHEPS max rent by bedrooms: studio $2,387 · 1BR $2,440 · 2BR $2,748 · 3BR $3,433 · 4BR $3,698
  (treat up to ~10% above as "within range").

## `violation`
The listing clearly excludes voucher holders:
- Explicit refusal in any language or wording: "no programs", "no vouchers", "no Section 8", "we don't take HRA",
  "programs need not apply", "private pay only", "Section 8 only" (excludes CityFHEPS), "Section 8 welcome, no CityFHEPS".
- Coded refusal: "no third-party payments", "no shelter/agency referrals", "no caseworker calls", "tenant pays full rent, no assistance".
- An income requirement applied to the full rent (e.g. "40x rent", "3x rent monthly", "$90k minimum income") with no
  exception for voucher holders, **when the rent is within CityFHEPS range** (or the requirement is an absolute dollar figure a
  voucher household couldn't meet).

## `needs_review`
Something may exclude voucher holders, but it isn't clear-cut from the text alone:
- Employment-only requirements: "working professionals only", "must be employed", "W-2 only", "pay stubs required",
  "income must come from employment", "only rents to tenants with jobs".
- A high credit minimum (650+) with no statement welcoming vouchers.
- An income requirement where the rent is unknown, or the rent is well above the CityFHEPS range (voucher may not cover it anyway).

## `no_issue_found`
- Nothing about income source, or only lawful terms: "no pets", "no broker fee", "no smoking", background check,
  application fee, guarantor companies accepted.
- Welcoming language: "vouchers welcome", "all programs accepted", "CityFHEPS OK" — including when paired with an income
  requirement or credit minimum (the welcome signals the requirement doesn't apply to voucher holders).
- Income requirement explicitly applied only to the tenant's share, or rental assistance counted as income.
- Government-set income bands: Housing Connect / HPD lottery, "% AMI", Mitchell-Lama, HDFC.
- Phrases with "no program" that aren't refusals: "no program fee", "no program needed to apply".
- Owner-occupied 2-family houses may be legally exempt; without an explicit refusal, label `no_issue_found`.

## Tie-breaks
- Both a refusal and welcoming language for a *different* program → `violation`.
- When genuinely unsure between two labels, pick the less severe one and say why in `rationale`.
