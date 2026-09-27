# Voucher Discrimination Detector: models (Person 2)

Listing → `discriminatory | needs_review | clean` + confidence + reasons + highlighted evidence.
Building → voucher-friendliness score + habitability warning + repeat-offender-owner flag.

## Run it

```bash
pip install -r requirements.txt
python demo.py                          # terminal demo, no API key needed
python -m vdd.eval                      # dev-set metrics (rules only)
python -m vdd.eval --holdout            # held-out metrics: the honest number
python -m vdd.buildings                 # score mock buildings
python -m unittest discover tests
uvicorn vdd.api:app --reload --port 8000   # API for the frontend; docs at /docs

export ANTHROPIC_API_KEY=...            # enables the Claude layer (text + images)
python -m vdd.eval --llm --holdout
```

## How the classifier decides

1. **Rules** ([vdd/rules.py](vdd/rules.py)): regex patterns in EN/ES/ZH/RU, each with a weight and an exact character span. Scores combine with noisy-OR.
2. **Income math**: "40x rent" becomes a dollar figure, compared against the most generous CityFHEPS income ceiling. If it's higher, the requirement *mathematically excludes every eligible family*, and the reason text says so.
3. **Suppressors**: "vouchers welcome", "tenant portion only", and government lottery/AMI bands discount soft signals. Explicit refusals are not discounted: "Section 8 welcome, no CityFHEPS" still flags.
4. **Claude** ([vdd/llm.py](vdd/llm.py)): called only when rules aren't confident (score < 0.9) or the listing is an image. It returns structured JSON with verbatim evidence quotes, language, and an English translation.
5. **Grounding check**: if Claude flags a listing the rules missed, its quotes must actually appear in the text. Otherwise the result is capped at `needs_review` and can never become a complaint.

Thresholds: `≥ 0.80` discriminatory (complaint gets drafted), `0.45–0.80` human review, else clean.

## Current numbers (rules only, no API key)

| set | n | precision | FPR | recall (auto-flag) |
|---|---|---|---|---|
| dev (`labeled_edge_cases.jsonl`, rules tuned on it) | 59 | 100% | 0% | 100% |
| **holdout** (written before scoring, never tuned on) | 25 | **90%** | 8% | 69% |

The holdout misses are paraphrases ("prefers tenants without government programs", "only rents to tenants with jobs"), which is the Claude layer's job. Report the holdout number. Before judging, have a teammate write `holdout_v2.jsonl` without looking at the rules.

## Data contract

**Input from Person 1: listings** (`vdd/schema.py: Listing`)
`id, text, source, url, rent, bedrooms, address, bbl, image_b64, image_media_type`
If the listing is a screenshot, send `image_b64` and leave `text` empty or partial; Claude reads the image directly, so no separate OCR step is needed.

**Input from Person 1: buildings** (any subset; missing columns default to 0)
`bbl, address, borough, lat, lon, units, owner, hra_placements_3yr, flagged_listings, clean_listings, chr_complaints, class_c_violations, open_violations, rent_stabilized_units`, plus optional `accepted_voucher` (0/1) to switch on the supervised model.

**Output to Person 3: `POST /classify`, `POST /classify/batch`**
```json
{
  "listing_id": "1", "label": "discriminatory", "confidence": 0.85,
  "category": "income_requirement",
  "reasons": ["Requires ~$88,000/yr (40x monthly rent, per year). CityFHEPS households earn at most ~$73,000/yr, so this requirement excludes every eligible voucher holder."],
  "evidence": [{"quote": "earn 40x", "start": 44, "end": 52, "rule_id": "income_requirement"}],
  "language": "en", "translation_en": null,
  "income_analysis": {"required_annual_income": 88000, "voucher_income_ceiling": 73000, "excludes_all_voucher_holders": true, "...": "..."},
  "legal_basis": "NYC Admin. Code § 8-107(5)(a) ...",
  "signals": {"rules": 0.85}
}
```
Use `evidence[].start/end` to highlight text. Paste `reasons` + `evidence` + `legal_basis` into the CHR complaint draft.

**`POST /buildings/score`, `GET /buildings/mock`**: rows with `friendliness` (0–1), `tier` (friendly/unknown/avoid), `habitability_warning`, `repeat_offender_owner`, `evidence_strength`, `reasons[]`, `lat/lon`.

## Caveats
- Numbers in [vdd/config.py](vdd/config.py) (CityFHEPS rent limits, income ceiling) are approximations; verify them before quoting.
- Mock building data is synthetic. The supervised model's AUC on it doesn't mean anything yet.
- Owner-occupied 2-family houses may be exempt from the law. The classifier doesn't know occupancy; that's a caseworker check.
