# Voucher Discrimination Detector

Finds illegal source-of-income discrimination against NYC CityFHEPS voucher holders in rental listings, shows the clause and the math, and produces an evidence packet and a human-reviewed complaint draft. Nothing is filed automatically, and no landlord is ever contacted.

## The app: Homeward NYC

Three features, each with a **List** and a **Map** view, at http://localhost:8000/ (run `uvicorn core.api:app --port 8000`):

| Feature | What it does | Page | API |
|---|---|---|---|
| **Voucher Guard** | Finds rental listings that refuse CityFHEPS/Section 8 (explicit refusals, income rules on full rent, coded language), shows the clause and math, builds an evidence packet and a CHR complaint draft for a person to review. Tools: scraped-listing queue, paste-a-listing check, camera/photo scanner. | `/voucher-guard/`, `/voucher-guard/scan/` | `/guard/listings`, `/analyze`, `/packet`, `/complaint` |
| **Open Doors** | Affordable vacancies: live open Housing Connect lotteries + voucher-friendly scraped listings, filtered by household size, income, voucher, bedrooms, borough. | `/open-doors/` | `/vacancies` |
| **Shelter Match** | Narrows 287 NYC homeless shelters with public addresses to the ones a person is eligible for, by demographics, with how to get in and what to bring. | `/shelter-match/` | `/shelters/match`, `/shelters` |

**Maps:** Google **Maps JavaScript API** only. Put a browser key in `.env` as `GOOGLE_MAPS_API_KEY` (restrict it to your domains and to the Maps JavaScript API); the pages fetch it from `GET /config`. Addresses are geocoded with NYC Planning's free GeoSearch (cached in `data/geo_cache.json`), with a borough check so nothing is pinned in the wrong place; places that can't be geocoded stay in the List view only.

**Scraper contract** (Voucher Guard and Open Doors both read it, via `scanner/store.py`): write a JSON array to `scanner/python/listings.json`. Required: `url`, `text`. Optional: `source`, `discovered_at`, `address`, `borough`, `rent`, `bedrooms`, `image_url`, `lat`, `lng`. Every listing is checked once; discriminatory ones go to Voucher Guard, clean ones to Open Doors. Listings without an address appear in lists but not on maps. Until the real scrape exists, `scanner/data/cached_listings.json` (3 samples) is used.

## Quick start (Python 3.9+)

```bash
pip install -r requirements.txt
cp .env.example .env                        # add GEMINI_API_KEY (optional; works offline without it)

python -m unittest discover tests            # 23 tests, offline
python demo.py                               # walkthrough + data/cache/demo-packet.html + demo-complaint.html
python -m eval.run --v2                      # blind test set: the number for the pitch
uvicorn core.api:app --reload --port 8000    # HTTP API for the iMessage agent + dashboard; docs at /docs
python -m eval.review --by "Your Name"       # label review page: http://localhost:4321
```

**Camera scanner:** start the API, then open http://localhost:8000/voucher-guard/scan/. Point the webcam at a flyer or upload a photo. The page runs on-device OCR (Tesseract, English + Spanish), then sends the photo and text to the Python engine: Gemini reads the photo (any language), rules R1–R4 decide, and it shows the math plus a CCHR complaint draft with a "Open review page" button. If the API is unreachable, it falls back to a basic in-browser check and says so. Opening the HTML file directly works too: add `?api=http://localhost:8000`.

`.env` is read automatically and is in `.gitignore`.

## Layout

| dir | what | language |
|---|---|---|
| `core/` | engine: extraction (Gemini + offline fallback), rules R1–R4, evidence packet, complaint drafts, FastAPI server | Python |
| `config/` | CityFHEPS numbers, legal text, agencies, phrase lists, thresholds (**verify numbers**) | Python |
| `scanner/` | `analyze_url()`: listing link → jev browser agent (or plain download) → engine | Python |
| `eval/` | precision/recall script, label review page | Python |
| `data/labeled/` | 144 labeled listings, rubric, blind agent labels | JSONL |
| `tests/` | unit tests | Python |
| `shelters/` | shelter eligibility matcher, public-address shelter list builder, DHS directory builder | Python |
| `web/` | the app: home, `voucher-guard/` (+ `scan/`), `open-doors/`, `shelter-match/`, `shared/` (nav, List/Map tabs, Google Maps) | HTML/JS |
| `vacancies/` | affordable vacancy feed: live Housing Connect lotteries + voucher-friendly scraped listings | Python |
| `/agent` | Photon Spectrum iMessage bot: **must be TypeScript** (Spectrum is TS-only); calls the API | teammate |
| `/web` | Next.js dashboard; calls the API | teammate |
| `legacy/` | earlier versions (TypeScript port, first Python prototype), reference only | |

## Using it from Python

```python
from core import analyze, build_packet, draft_complaint, approve_draft

result = analyze({"text": text, "image": {"base64": b64, "mime_type": "image/jpeg"}, "hints": {"bedrooms": 2}})
result.verdict      # "violation" | "needs_review" | "no_issue_found"
result.flags        # [Flag(rule_id, code, severity, evidence_text, span, explanation, calculation)]

packet = build_packet(result, tenant_language="es", packet_url=url)
packet.summary_text # iMessage reply
packet.html         # shareable page

draft = draft_complaint(result, agency="cchr", listing={"source": "Craigslist", "url": url, "screenshot_saved": True},
                        reporter={"role": "caseworker"}, tenant_language="es")
draft.form          # answers for the CCHR online form, field by field
draft.blocking      # must be fixed before submitting (missing respondent name, screenshot, ...)
draft.html          # printable review page with Copy buttons
approve_draft(draft, "Reviewer name")   # records the review; still sends nothing
```

`analyze` never raises on a Gemini failure. A 503 ("high demand") is retried; anything else, including a 429 quota error, falls back to the offline extractor with a short note. Set `VDD_DEBUG=1` to see the full Gemini errors.

## Using it from TypeScript (iMessage agent, dashboard)

Run `uvicorn core.api:app --port 8000`, then:

| endpoint | body | returns |
|---|---|---|
| `POST /analyze` | `{text?, image?: {base64, mime_type}, hints?, use_gemini?}` | analysis result |
| `POST /analyze-url` | `{url, bedrooms?, monthly_rent?}` | `{result, fetched}` |
| `POST /packet` | `{result, tenant_language?, packet_url?, listing_url?}` | `{summary_text, html, ...}` |
| `POST /complaint` | `{result, agency?, listing?, respondent?, reporter?, contact?, tenant_language?}` | draft (422 if no issue found) |
| `POST /complaint/approve` | `{draft, reviewer}` | draft marked reviewed (sends nothing) |
| `POST /complaint/html` | a draft | the review page as HTML |
| `GET /health` | | `{ok, gemini, model}` |

Full schemas at http://localhost:8000/docs.

## Shelter finder

Open http://localhost:8000/shelter-match/ (API running). Answer: household type, age, gender, borough, and yes/no questions (fleeing violence, in a NYC shelter in the last year, veteran, LGBTQ+, working, mental health, substance use, HIV/AIDS, medical). Nothing is stored.

It returns only **homeless shelters with a publicly published street address** (285 across the five boroughs), narrowed to the ones this person is eligible for:
- **How to get in**: the right DHS intake door (men: 8 E. 3rd St; women: Franklin or HELP; families: PATH; adult families: 30th St), the 12-month return rule, youth shelters taking young people directly, and the domestic violence hotline (DV shelters are confidential and never listed).
- **Each shelter is a dropdown**: how to get in, eligibility, what to bring, contact, forms and links (source, DHS application page, directions), the exact source quote, and a "call to confirm" warning when the source is older than 2025.
- **Filters on the results**: borough, shelter type, special populations, walk-in only; sort by best fit, borough, beds, or name.
- **Not eligible, and why**: every ruled-out shelter with its reason ("Women only", "Up to age 24", "For veterans").

Data: `data/shelters/public_shelters.json`, built by `python -m shelters.build_public` from a hand-checked seed plus research files in `data/shelters/research/`. Addresses come from DHS contract notices in the City Record (NYC Open Data `dg92-zbpx`), nyc.gov pages, and operator websites; 12 of 12 randomly sampled addresses matched their cited source. Each shelter is cross-checked against the city's DHS shelter directory (NYC Open Data `dvaj-b7yx`, as of Dec 2022) for type and bed count. Where sources disagreed, DHS wins (men's intake moved from 30th St to 8 E. 3rd St).

API: `POST /shelters/match` (a `Profile`), `GET /shelters` (the full list).

## Affordable vacancies

Open http://localhost:8000/open-doors/. One feed with:
- **Open Housing Connect lotteries**, live from Housing Connect's public API (the same data housingconnect.nyc.gov shows): deadline and days left, address, every unit type's rent, household-size range, and income range by household size, whether a CityFHEPS voucher covers the rent, paper-application address, and the apply link. Falls back to NYC Open Data (HPD `vy5i-a666`), which lags by weeks.
- **Voucher-friendly listings** from the scraper (`scanner/python/listings.json`, or `scanner/data/cached_listings.json`), run through the detector: discriminatory and questionable listings are hidden (and counted); listings that welcome vouchers rank first, then ones within the CityFHEPS rent limit.

Filters: household size, yearly income, "has a voucher" (Housing Connect: minimum income "may not apply to applicants with Section 8 or other qualifying rental subsidies"), bedrooms, borough, lotteries/listings, rent within voucher limit. Example: a family of 3 earning $30,000 fits 2 of 11 open lotteries on paper, and may qualify for all 11 with a voucher.

API: `GET /vacancies?household_size=&income=&has_voucher=&bedrooms=&borough=&kind=&within_voucher_limit=`, `POST /vacancies/refresh`. Lotteries are cached 6 hours in `data/vacancies/lotteries.json`.

## How a verdict is made

Gemini extracts facts only (rent, bedrooms, income requirement, exclusion phrases, contact, language, translation). The **rules engine decides**, with no model involved:

- **R1 Explicit exclusion**: phrase list (EN/ES/ZH/RU/BN + misspellings + coded phrases like "no third-party payments") run over the listing, the text read from the image, and the English translation. An exclusion Gemini found that the phrase list missed only counts if its quote is really in the text, and then only as `review`.
- **R2 Income applied to full rent**: builds the math step by step (requirement × rent, the tenant's 30% share for an illustrative household, the lawful requirement on that share, the full-rent requirement). Lawful: tenant-share carve-outs, "vouchers welcome", lottery/AMI bands. Unknown rent or rent above the payment standard gives `review`.
- **R3 Other barriers**: employment-only and credit minimums give `review` (switch in `config/thresholds.py`).
- **R4 Voucher range**: is the rent within the CityFHEPS payment standard? Informational; feeds the split-screen view.

## Complaint drafts (human-reviewed, never auto-filed)

- **Matches the real CCHR form** (nyc.gov/site/cchr/about/report-discrimination.page), field by field. Each answer is `auto` (from the listing), `suggested` (confirm it), or `you` (only the person can answer).
- **Never pre-filled:** the person's name and contact info, "filed with us before?", and the required acknowledgment checkbox.
- **The narrative is a template**, not model-written: it only states facts from the flagged clauses and the math, quotes full sentences, and says the listing was found with an automated tool and checked by a person.
- **Deadlines:** CCHR one year from the last act; NYS Division of Human Rights (`agency="nysdhr"`) three years for incidents on or after Feb 15, 2024. CCHR can't take a complaint already filed elsewhere, so the draft makes the reviewer answer that.

## jev-ultrafast (browser agent) on OpenJev

[browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast) opens a listing link, dismisses pop-ups, clicks "See more", and returns the full page text plus a screenshot. `scanner/jev/fetch_listing.py` runs jev's steps itself and **blocks** typing into any field and clicking anything labeled contact / message / apply / call / schedule / sign in, so it can't contact a landlord.

jev's decisions come from a "System One" model API. TypeSafe's hosted API is paused, so we use **[OpenJev](https://github.com/razorback16/openjev)**, an open-source server with the same API (open model: DiffusionGemma 26B-A4B), hosted free at Codiv. jev hardcodes TypeSafe's URL, so the sidecar redirects it when `TYPESAFE_BASE_URL` is set.

Setup:
```bash
brew install uv
git clone https://github.com/browser-use/jev-ultrafast.git ~/jev-ultrafast
cd ~/jev-ultrafast && uv sync
```
Then in our `.env`:
```
JEV_DIR=/Users/<you>/jev-ultrafast
TYPESAFE_BASE_URL=https://api.codiv.ai     # or http://127.0.0.1:8080 for a self-hosted OpenJev
TYPESAFE_API_KEY=sk-codiv-...              # free Codiv key (codiv.ai)
TYPESAFE_MODEL=openjev-latest
JEV_CHROME_PORT=9333
```
Before using links, start jev's private Chrome in its own terminal and leave it running (empty profile, none of your logins, no window):
```bash
scanner/jev/start_chrome.sh          # uses JEV_CHROME_PORT=9333 from .env
```

`TEXT_MODEL_API_KEY` is only used to type into fields, which our guard blocks, so it shouldn't be needed. Without any of this, links fall back to a plain download. Listing page text is sent to Codiv to choose clicks; it's public listing content, never tenant data.

## Eval: read before quoting numbers

Offline results (regex extractor, no Gemini):

| set | n | violation precision | violation recall | reaches a human | false alarms |
|---|---|---|---|---|---|
| dev (rules built from it) | 59 | 100% | 100% | 100% | 0% |
| holdout v1 (contaminated) | 25 | 100% | 91% | 91% | 0% |
| **holdout_v2 (blind; quote this)** | **60** | **92.9%** | **59.1%** | **63.6%** | **3.8%** |

- `holdout_v2` was written by an agent that only saw `data/labeled/RUBRIC.md`, never the rules. **Don't change rules because of its misses**; if you do, the number stops being honest and you need a v3.
- Misses are mostly paraphrases and non-English refusals the phrase list doesn't know. That's Gemini's job; rerun with `--gemini` once the key has quota.
- Two blind agents pre-labeled the data (`data/labeled/agent/`). A person verifies each label with `python -m eval.review --by "Name"` (1/2/3 pick, Enter accepts, Backspace goes back).
- The rubric was written knowing the existing labels, so agent agreement partly reflects the rubric.
- Total labeled: 144. For ~150, add real cached listings to `data/labeled/real.jsonl` and run `python -m eval.run --file data/labeled/real.jsonl`.
