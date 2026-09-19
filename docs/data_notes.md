# Data Notes — RateRight

**Data source:** Inside Airbnb — New York City
**Snapshot date:** 14 June 2026
**Stage covered:** Milestone 0 (Setup) and Milestone 1 (Ingest)
**Tools:** Python, DuckDB, pandas, Parquet

These notes record what was measured in the raw data before any cleaning.
Every number below comes from `notebooks/01_first_look.ipynb`.

---

## 1. Files received

| File | Format received | Stored as |
|---|---|---|
| `listings.csv` | Unzipped CSV | `data/bronze/nyc/listings.parquet` |
| `calendar.csv` | Unzipped CSV | `data/bronze/nyc/calendar.parquet` |
| `reviews.csv` | Unzipped CSV | `data/bronze/nyc/reviews.parquet` |

Raw files are kept in `data/raw/nyc/` and are not modified.
The `data/` folder is excluded from Git because the files are large.

---

## 2. Ingestion (Milestone 1)

**Script:** `src/ingest.py`

**What it does:** Reads each CSV with DuckDB and saves it as a Parquet file.

**Key decision:** Every column is saved as text (`all_varchar = true`).
- Prices arrive as text such as `"$1,250.00"`, and automatic type guessing could convert them wrongly.
- The Parquet copy stays identical to what was received.
- All type conversions happen in Milestone 2, where each rule is visible and documented.

### Row counts and file sizes

| Dataset | Rows | Parquet size |
|---|---:|---:|
| listings | 30,259 | 20.0 MB |
| calendar | 11,152,576 | 4.2 MB |
| reviews | 990,170 | 180.8 MB |

**Why the calendar is so small:** Parquet stores data column by column and compresses repeated values well.
The calendar is highly repetitive (the same listing ID repeated 365 times, sequential dates, only `t`/`f` for availability).
Reviews contain mostly unique free text in many languages, so they compress much less.

### Row count validation

- pandas reads `listings.csv` as **30,259** rows.
- DuckDB Parquet also has **30,259** rows. ✓
- The listings file contains line breaks inside text fields. Matching counts confirm these were read correctly.

---

## 3. Schema findings

### Calendar has only 5 columns

| Column | Meaning |
|---|---|
| `listing_id` | Links the row to a listing |
| `date` | The night being described |
| `available` | `t` = available, `f` = not available |
| `minimum_nights` | Minimum stay rule for that date |
| `maximum_nights` | Maximum stay rule for that date |

- `price` and `adjusted_price` are **not present** in this snapshot.
- In the August 2025 snapshot, these columns existed but were 100% empty.
- **Impact:** Nightly prices cannot come from the calendar. The only price source is `listings.price`.

---

## 4. Calendar investigation

### Summary

| Measure | Value |
|---|---:|
| Total rows | 11,152,576 |
| Distinct listings | 30,555 |
| First date | 2026-06-14 |
| Last date | 2027-06-22 |

### Dates per listing

| Dates per listing | Number of listings |
|---:|---:|
| 365 | 30,554 |
| 366 | 1 |

### Integrity checks

| Check | Result |
|---|---:|
| Duplicate (`listing_id`, `date`) rows | 0 |
| Calendar listings not found in `listings` | 296 |

### Row count explained

```
30,554 listings × 365 dates = 11,152,210
     1 listing  × 366 dates =        366
                              ----------
Total                       = 11,152,576  ✓ matches file
```

- The calendar has **296 more listings** than the listings file (30,555 vs 30,259).
- These 296 listings have no matching record in `listings`. They were likely removed or delisted between the two files being collected.
- There are no duplicate rows. Every calendar row is accounted for.

### Calendar start dates

| First calendar date | Number of listings |
|---|---:|
| 2026-06-14 | 14,544 |
| 2026-06-15 | 7,224 |
| 2026-06-22 | 2,088 |
| 2026-06-23 | 6,699 |
| **Total** | **30,555** ✓ |

- Listings do **not** all start on the same date.
- Start dates fall into two groups about a week apart: 14–15 June and 22–23 June.
- This suggests the data was collected in batches over more than a week.
- **Impact:** "Next 30 days" must be calculated from each listing's own first calendar date, not from one fixed date.
- The date range where **every** listing has calendar data is **2026-06-23 to 2027-06-13**. Use this window when comparing listings over the same dates.

---

## 5. Price investigation (listings)

| Measure | Value |
|---|---:|
| Total listings | 30,259 |
| Listings with a price | 21,515 |
| Share with a price | 71.1% |
| Median price | $174.69 |
| Non-empty prices converted to numbers | 21,515 of 21,515 ✓ |

- Every non-empty price converts cleanly after removing `$` and `,`.
- The median is used instead of the mean because of very high outlier prices.
- 8,744 listings (28.9%) have no price.

### Comparison with the earlier snapshot

| Snapshot | Listings with price | Median price |
|---|---:|---:|
| August 2025 | 58.4% | $150.00 |
| **June 2026** | **71.1%** | **$174.69** |

Price coverage is much better in this snapshot, giving about 21,500 listings for the base price model.

---

## 6. Cleaning decisions for Milestone 2

| Finding | Decision | Reason |
|---|---|---|
| 296 calendar listings not in `listings` | Drop them from the cleaned calendar | No location, room type or price, so they cannot be compared |
| 1 listing with 366 dates | Keep it | No duplicates; it is valid data |
| Listings start on different dates | Measure "next N days" from each listing's first date; use 2026-06-23 to 2027-06-13 for same-date comparisons | Collection happened in batches |
| 28.9% of listings have no price | Keep them for market and demand analysis; exclude them from model training | They are still real supply |
| Price stored as text (`$1,250.00`) | Remove `$` and `,`, convert to a number | All 21,515 values convert successfully |
| Calendar price columns missing | Build the price calendar from base price plus availability-based demand rules | No nightly price history is available |

---

## 7. Known limitations

1. **Listed price is not the booked price.** `listings.price` is what the host asks, not what guests paid.
2. **Unpriced listings may differ from priced ones.** The model learns only from the 71.1% with a price.
3. **No nightly price history.** The calendar has no price columns, so price-by-date must be simulated.
4. **Unavailable does not mean booked.** A host may block dates, so availability is a demand signal, not actual bookings.
5. **Single snapshot.** Price changes over time cannot be measured from this data.

---

## 8. Open questions

- Do the calendar start dates match each listing's `last_scraped` date? Check in Milestone 2.
- Which listing has 366 dates, and why? Low priority.
- Are there extreme or placeholder values in `minimum_nights` and `maximum_nights`? The August 2025 snapshot had `2,147,483,647`. Check in Milestone 2.

---

## 9. Environment note

- The notebook should run on the project's `.venv` kernel, not the global `base` Python.
- Install the notebook kernel inside `.venv` with `pip install ipykernel`, then select `.venv` in VS Code.


## Milestone 2 — Cleaning results

**Script:** `src/clean.py` → `data/silver/nyc/`

| Dataset | Bronze rows | Silver rows | Difference |
|---|---:|---:|---|
| listings | 30,259 | 30,259 | none removed |
| calendar | 11,152,576 | 11,044,536 | 108,040 rows from 296 unmatched listings removed |
| reviews | 990,170 | 980,552 | 9,618 reviews from 239 unmatched listings removed |

### Price quote findings
- `price` equals the quote's per-night price for all 21,514 quoted listings
- The quote is for each listing's minimum stay (96.4% exactly equal; never shorter)
- 73.6% of quotes are for 30 nights; 13.8% are for 1 night
- `price` is **after** any length-of-stay discount and **excludes** fees
- About half of 28+ night quotes are discounted (median discount 17.6%)
- Cleaning and service fees are never filled; taxes appear in only 58 quotes
- All prices are in USD
- Added columns: `quote_nights`, `quote_discount`, `pre_discount_nightly_price`

### Validation
- 0 placeholder `maximum_nights` values left
- 0 zero ratings left
- No negative discounts
- Every calendar listing exists in listings
- 2 listings initially showed a pre-discount price 1 cent below the listed price.
  Cause: floating-point rounding of values ending in exactly half a cent
  (e.g. 279.59 ÷ 2 = 139.795). Fixed by storing unrounded values and rounding
  only for display. After the fix: 0 rows.

  ## Milestone 3A — Price exploration

- Price is right-skewed: median $174.69, mean $278.23, max $30,972.96
- log10(price) is roughly bell-shaped with two peaks (~$65 and ~$200)
  → model log(price), not price
- Short stays (<28 nights, 4,993 listings) cost ~2–3× more than monthly stays
  (16,522 listings) within the same room type
  (entire home $403 vs $202; private room $248 vs $77)
- Removing discounts barely changes this (pre-discount medians $313 vs $161)
  → stay type must be part of the model
- Unpriced listings mostly have 0 available days (median) and far fewer
  superhosts (6.3% vs 30.8%) → the model applies to active listings only
- Top prices include identical very high prices on multiple hotel listings,
  likely blocking prices; 12 listings above $10,000
- Outlier rule: to be decided in 3D

### Short stays and licensing
- Short stays: 50.5% exempt, 43.7% registered, 5.9% no license
- Monthly stays: 99.3% no license
- Short vs monthly is effectively a regulatory market segment
  (licensed/exempt short-term rentals vs 30+ night rentals)
- Short-stay median price: exempt $402, registered $238, no license $329

### High-price listings
- 52 of 164 listings above $2,000 share an exact price with another listing
  from the same host — could be identical units or blocking prices
- Not used alone as an outlier rule
- 1 priced listing has no quote → stay_type = "unknown"

## Milestone 3B — Market segments

- Room type explains the two price peaks (private room ~$65, entire home ~$200)
- Registered short stays are 75% private rooms; exempt short stays are mostly
  entire homes (1,081) and hotel rooms (459)
- Entire-home medians rise with bedrooms (monthly $186 → $454 from 1 to 4+);
  short stays cost ~2× at every size
- No entire homes have bedrooms = 0; 1,743 entire homes have no bedroom count
  (possibly studios — check in 3D)
- Manhattan > Brooklyn > Queens > Bronx / Staten Island, in every segment
- Monthly entire homes: Tribeca $562 vs Ozone Park $120 (4.7×)
- Only 60 neighbourhoods have 30+ monthly entire homes
- Comparable-listing coverage (groups with 10+ listings):
  neighbourhood + room + stay + bedrooms 78.2%;
  neighbourhood + room + stay 92.8%;
  borough + room + stay 99.9%
  → use a fallback chain with a minimum of 10 listings
- All 21,515 priced listings have quote dates, so every priced listing has a stay type

## Milestone 3C — Demand

- Demand signal uses priced (active) listings only,
  over 2026-06-23 to 2027-06-13
- Near-term dates are busiest: 53–58% unavailable in days 0–29,
  falling to ~25–30% by days 60–90
- Short stays show a weekly pattern: Fri 45.4% and Sat 46.7% unavailable
  vs Mon 35.3% (next 90 days) → supports a weekend price increase
- Holiday peaks in short stays: ~72% around 4 July; rising toward New Year
- Step jumps at ~3, 6 and 9 months after the scrape dates (mid-Sep,
  mid-Dec, mid-Mar) match Airbnb booking-window settings → not real demand
- Quote months are almost all June/July for short stays
  → no reliable seasonal price data; the price calendar relies on
  availability patterns

  ## Milestone 4 — Comparable listings

- prepare.py: 30,259 listings; 21,514 with base price; 101 outliers
  (on base price); 1,573 studios filled; 860 entire homes still missing bedrooms
- 1 listing has a listed price but no base price (no per-night quote value)
- comps.py levels: L1 76.4%, L2 15.5%, L3 8.0%, L4 0.1% (18 listings)
- Smallest group: 10 comps (levels 1–3), 20 (level 4)
- Validation: median gap +1.7%; 0 contradictions; SQL matched an
  independent pandas recalculation exactly (219 comps, median $227.49)
- Gap % is lopsided (p25 −21%, p75 +42%) → health check uses
  pct_comps_cheaper as the main position measure

  ## Milestone 5 (Step 5.1) — Baselines

- Split by host_id (GroupShuffleSplit, 80/20, random_state=42):
  17,035 train / 4,378 test listings; 0 hosts appear in both
- Bug found: 21 test listings are Hotel room + monthly stay, a segment
  with 0 training examples. The initial evaluate() function let this
  produce NaN, which silently corrupted median_abs_pct_error and
  understated within_20pct. Fixed by having evaluate() detect and
  report missing predictions instead of averaging over them.
- Baselines to beat:
  | Model                        | n     | median % error | within 20% |
  |-------------------------------|------:|---:|---:|
  | Segment median (room + stay)  | 4,357 | 39.7% | 26.6% |
  | Comp median (Milestone 4)     | 4,378 | 30.1% | 35.3% |
- Hotel room + monthly stay (21 test listings) has no training data
  at all → tracked separately in Step 5.4, not folded into overall
  model error; RateRight should flag low confidence for this segment.

## Milestone 5 — host_years distribution check

- Investigated whether 15 (the max) was a placeholder, since early
  sample rows all showed 15. Checked the full distribution:
  smooth, single-peaked-ish spread from 0-15, only 1.5% at 15.
  Airbnb launched in 2008, so 15 years is plausible for a June 2026
  snapshot. Treated as genuine, no cap flag added.

## Milestone 5 — stay_type had near-zero LightGBM importance

- Investigated why stay_type (importance 39) ranked far below borough (108)
  despite a 2-3x price effect found in Milestone 3.
- Ruled out: data loss (counts correct, 4,993/16,521), and
  latitude/longitude substituting for it (short-stay and monthly-stay
  listings are geographically similar: avg coords ~0.004-0.008° apart,
  similar spread).
- Confirmed cause: minimum_nights already encodes ~96% of stay_type's
  information (from Milestone 3B: quoted stay = minimum_nights in 96.4%
  of cases). Retrained LightGBM without stay_type: test error 25.3%
  (vs 25.1% with it) — essentially no change, confirming redundancy,
  not a bug.
- Decision: keep stay_type in the model table anyway (free, and needed
  for readable app/health-check logic), but note the model itself
  leans on minimum_nights for this signal.


## Milestone 5 — price_confidence flag (final)

- Added in prepare.py: segments (room_type + stay_type) with fewer than
  50 priced, non-outlier listings get price_confidence = 'low'; all
  other priced listings get 'normal'; unpriced listings get NULL
  (no verdict, consistent with price_outlier's handling of them).
- Bug found and fixed: the first version joined on stay_type using `=`,
  which never matches NULL to NULL in SQL. Since unpriced listings have
  a NULL stay_type, this caused ~8,700 unpriced listings to be wrongly
  flagged 'low' or 'normal'. Fixed by explicitly setting
  price_confidence = NULL whenever base_price IS NULL, rather than
  relying on the join to handle it.
- Final result (priced listings only, n=21,514):
  - low: 61 (Hotel room + monthly stay: 21; Shared room + short stay: 40)
  - normal: 21,453 (all other room_type + stay_type combinations)

## Milestone 6, Step 6.1 — Demand baseline

- Built demand_curve.parquet: smoothed (7-day rolling average) %
  unavailable by days_ahead (0-329), separately for short stay and
  monthly stay, using only open-calendar + active (priced) listings.
- 10,775 monthly-stay and 2,652 short-stay listings qualify as
  open-calendar; every one of them has data on every day 0-329, so
  coverage is constant across the whole curve.
- No booking-window jump at day ~270 (confirmed the open-calendar
  filter removed the Milestone 3D artifact).
- Values broadly match Milestone 3D's 30-day-bucket figures (e.g.
  monthly day 0: 69.5% here vs 60.8% bucketed; day 270: 2.9% vs 2.5%).
- New detail visible at daily resolution: short-stay unavailability
  rises slightly from day 60 (26.3%) to day 90 (29.4%) before
  continuing to fall — smoothed out of the coarser 30-day buckets.
- Short-stay raw curve visibly shows the Fri/Sat weekly pattern found
  in Milestone 3C; monthly-stay raw and smoothed lines are nearly
  identical (no weekly rhythm for 30-night stays).


## Milestone 6, Step 6.2 — Weekday and date adjustments

- Computed excess = observed - expected (from the days-ahead baseline),
  per listing-night, for short-stay open-calendar listings, days_ahead < 180.
- Weekday effect (avg excess, pp): Mon -3.5, Tue -3.4, Wed -2.2, Thu +0.3,
  Fri +4.4, Sat +5.3, Sun -0.6. Confirmed absent for monthly stays
  (all 7 days within 30.3-31.3%, no pattern) — validates restricting
  this adjustment to short stays only.
- Date-level finding, revised from Milestone 3C: the top-excess dates
  are overwhelmingly ordinary summer/early-fall Fri/Sat nights
  (17 of the top 20), not holidays specifically. Actual holidays in
  range (Jul 4: +8.8pp, Oct 31: +9.4pp, Nov 25-26: +7.0/+6.3pp) show
  real but smaller excess than several ordinary summer Saturdays
  (e.g. Jul 18: +16.6pp). Reframed as a general "summer weekend"
  effect rather than a distinct "holiday" effect.
- Decision: use date_adjustment.parquet's excess value directly per
  date (days_ahead < 180), rather than hardcoding a holiday list.
  Beyond 180 days, fall back to the weekday adjustment only.


## Milestone 6, Step 6.3 — Price calendar

- Built price_calendar.parquet: 90-day (2026-06-23 to 2026-09-20)
  suggested nightly price per listing, from base_price (Milestone 5)
  adjusted by demand excess (Step 6.2), capped at +/-15%.
  Rule-based conversion (1pp excess -> 1.5% price change), NOT a
  learned price elasticity -- no booking/price history exists to
  learn one from. Documented as an assumption.
- Monthly-stay listings get a flat calendar (0% adjustment always,
  confirmed: exact 0.0 to 0.0 range) -- they're quoted once for a
  30-night block, so a nightly price doesn't apply.
- Short-stay listings (4,993 listings, 449,370 listing-nights):
  adjustment range -14.0% to +15.0%, median -1.8%, mean -0.3%.
  Confirmed every date in the 90-day window has real date-specific
  demand data (0 missing from date_adjustment.parquet), so the
  weekday-only fallback is correctly unused here (would activate for
  a calendar extending past the 180-day reliable window).
- Distribution shape is asymmetric by design, not a bug: only 5.6% of
  nights hit the +15% cap (genuine demand spikes like Jul 18: +16.6pp
  raw excess), 0% hit the -15% floor. Median sits slightly below zero
  (-1.0pp raw excess) since most nights are unremarkable while a
  smaller set of summer weekends pull the average up -- a normal,
  right-skewed demand pattern.


## Milestone 7 — Health score (final)

- Built health_score.parquet: 7 rule-based flags, each with a fixed
  point deduction from 100, floored at 0. Benchmark groups: borough +
  room_type + stay_type (simpler than Milestone 4's comp fallback --
  appropriate for directional signals, not precise price comparisons).
- Bug found: flag_restrictive_stay returned NULL instead of False when
  a listing's own minimum_nights was NULL, which then propagated to a
  NULL (silently shown as 0) health_score. Root cause: exactly 1
  listing citywide (of 21,514 priced) has a NULL minimum_nights in the
  source data -- confirmed a genuine one-off data gap, not a pipeline
  issue (this listing does have a valid quote_nights=2 and price).
  Fixed with COALESCE(minimum_nights, 0) and COALESCE(benchmark, 0) in
  the flag condition, plus COALESCE(flag, FALSE) around every flag in
  the score formula as a general safety net.
- price_outlier_flag count matches Milestone 5 exactly (101).
- Final distribution (n=21,514): mean score 79.3, 1,506 listings
  (7.0%) below 50.
- Flag rates: overpriced 28.4%, underpriced 25.7%, high availability
  34.2%, gone quiet 26.4%, rating gap 8.2%, restrictive stay 3.5%,
  price outlier 0.5%.
- Noted limitation: flags correlate heavily rather than being
  independent -- a single root cause (e.g. an extreme outlier price)
  typically triggers overpriced + high_availability + gone_quiet +
  price_outlier together, so a very low score usually reflects one
  underlying problem showing up four ways, not four separate issues.

## Milestone 8 — Diagnosis generator

- Built diagnosis.parquet: template-based (not LLM), hedged,
  number-backed sentences per listing, ordered by flag severity,
  capped at 3 issues shown. Low-confidence listings get a prepended
  caveat.
- Validated: 0 diagnoses contain "nan"; all 61 low-confidence listings
  (matching Milestone 5's count exactly) carry the caveat prefix, with
  no false positives or negatives.
- Issue-count distribution matches Milestone 7's flag counts exactly:
  5,007 healthy (0 issues) = Milestone 7's "0 flags" count; 8,408 with
  1 issue; 5,698 with 2; 2,401 with 3 (= Milestone 7's "3+ flags"
  count, since the cap means 3+ always displays as exactly 3).
- Spot-checked sample diagnoses read naturally and are internally
  consistent (e.g. score deductions match the sentences shown).
- Applied a wording polish to sentence_overpriced (and could similarly
  apply to sentence_underpriced) so a 100%/0% comp position reads as
  "every comparable listing nearby" instead of "100% of comparable
  listings." Re-ran diagnosis.py: identical counts across all
  categories (21,514 / 5,007 / 8,408 / 5,698 / 2,401), confirming the
  change was cosmetic only and didn't alter any flag logic.


## Milestone 9 — App debugging: session state, not data, was the root cause

- Investigated an app bug where searching a known listing ID showed a
  completely different listing's data. Ruled out (in order): stale
  Streamlit cache, leftover server processes still holding port 8501
  across multiple restarts, pandas merge row duplication, and
  int64/float64 precision loss on large listing IDs -- all confirmed
  clean via direct notebook checks against the same Parquet files.
- Root cause: the "Surprise me" button wrote a new value into
  st.session_state["random_id"] separately from the text input's own
  displayed value, so the box could show one ID while the app actually
  looked up a different one -- a UI state desync, not a data bug.
- Fixed by binding the text input directly to session state via
  key="listing_id_input", and updating it through an on_click callback
  (required by Streamlit -- session state for an already-instantiated
  widget can't be set directly in the main script body).
- Added permanent safeguards: a "Showing listing ID: X" caption so the
  displayed ID is always verifiable, and a check that warns if a
  listing_id ever matches more than one row.
- Also fixed: diagnosis text with two dollar amounts (e.g. "$268 ...
  $172") was rendered by Streamlit as inline code, because st.write()
  interprets $...$ as LaTeX. Fixed by switching to st.text(), which
  renders plain text with no markdown/LaTeX interpretation.