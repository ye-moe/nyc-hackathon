// CityFHEPS / legal parameters. EVERY number here is an approximation for the
// demo. Verify against current HRA payment standards and CCHR guidance before
// the pitch, and update `verifiedOn` when you do.

export const cityfheps = {
  verifiedOn: null as string | null, // e.g. "2026-09-26"

  // Max monthly rent CityFHEPS pays, by bedroom count (tracks the Section 8
  // payment standard; approx HUD FY2025 NYC FMR).
  paymentStandard: { 0: 2387, 1: 2440, 2: 2748, 3: 3433, 4: 3698 } as Record<number, number>,
  // Payment standards shift yearly and our table is approximate; rents up to
  // this factor above the standard still count as "in voucher range".
  paymentStandardSlack: 1.1,

  // Share of household income a CityFHEPS tenant pays toward rent.
  tenantShareOfIncome: 0.3,

  // Illustrative household used to show the R2 math. A family of 3 with one
  // part-time earner. Not a real person; label it as illustrative in the UI.
  exampleHousehold: { size: 3, annualIncome: 24000 },

  // Most generous income a CityFHEPS-eligible household can have (post-2023
  // expansion, ~50% AMI for 3 people). If a requirement exceeds this, it
  // excludes every eligible household: a conservative, defensible claim.
  incomeCeiling: 73000,
};

export const legal = {
  citation: "NYC Admin. Code § 8-107(5)(a)",
  summary:
    "The NYC Human Rights Law makes it illegal for landlords, brokers, and agents to refuse " +
    "a tenant because of their lawful source of income, including CityFHEPS, Section 8, and other rental assistance.",
  incomeRule:
    "Per NYC Commission on Human Rights guidance, income and credit requirements may only be applied " +
    "to the portion of rent the tenant pays, not the portion the voucher covers.",
  nextSteps: [
    "Save this packet and a screenshot of the original listing.",
    "Report it to the NYC Commission on Human Rights: call 311 and ask for the Commission on Human Rights, or go to nyc.gov/cchr.",
    "If you have a caseworker, share this packet with them.",
    "This packet is information, not legal advice. A person decides whether to file.",
  ],
};
