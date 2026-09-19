# Exploration Decisions — RateRight (Milestone 3)

**Data:** Inside Airbnb — New York City, snapshot dated 14 June 2026
**Notebooks:** `04_explore_price` · `05_explore_segments` · `06_explore_demand` · `07_final_checks`

Every decision below links back to evidence measured in the notebooks.
Numbers refer to the 21,515 listings that have a price, unless stated otherwise.

---

## 1. Which listings the project covers

| Decision | Evidence |
|---|---|
| Model and demand analysis use **priced (active) listings only** | Unpriced listings (8,744) have a median of **0** available days in the next year and far fewer superhosts (6.3% vs 30.8%) |
| State this as a limitation | Results apply to active listings, which are the listings a pricing tool is for |

---

## 2. Which price to model

| Decision | Evidence |
|---|---|
| Model **log(price)**, not price | Prices are right-skewed: median $174.69, mean $278.23, max $30,972.96. log10(price) is roughly bell-shaped |
| Use **pre-discount nightly price** as the model target | `price` is the rate *after* length-of-stay discounts. About half of 28+ night quotes are discounted (median 17.6%). PriceLabs' base price is the price *before* such discounts |
| Keep `price` (after discount) for display and comparison | It is the price guests see in the quote |

---

## 3. Market segments

| Decision | Evidence |
|---|---|
| **Stay type** (short stay < 28 nights / monthly stay) is a required model feature | Short stays cost ~2–3× more within the same room type (entire home $403 vs $202; private room $248 vs $77). Discounts do not explain the gap (pre-discount $313 vs $161) |
| **License status** (exempt / registration number / no license) is a model feature | 94% of short stays are exempt or registered; 99.3% of monthly stays have no license. Short-stay medians: exempt $402, registered $238 |
| **Room type** is a required feature | It explains the two price peaks (private room ~$65, entire home ~$200) |
| **Bedrooms and accommodates** are features | Entire-home medians rise from $186 (1 bedroom) to $454 (4+) for monthly stays; short stays ~2× at every size |
| **Location** uses borough, neighbourhood, latitude and longitude | Monthly entire homes: Tribeca $562 vs Ozone Park $120 (4.7×). Only 60 neighbourhoods have 30+ such listings, so coordinates help where neighbourhoods are small |

---

## 4. Comparable listings (Milestone 4)

Use the **narrowest group with at least 10 listings**:

| Level | Group definition | Coverage with 10+ listings |
|---:|---|---:|
| 1 | neighbourhood + room type + stay type + bedrooms | 78.2% |
| 2 | neighbourhood + room type + stay type | 92.8% |
| 3 | borough + room type + stay type | 99.9% |
| 4 | room type + stay type (citywide) | remaining listings |

Each listing's result records which level was used, so the app can say how close the comparison is.

---

## 5. Missing bedrooms

| Decision | Evidence |
|---|---|
| If an entire home has no bedroom count **and** its name mentions "studio", set bedrooms to **0** | 67.8% of the 1,743 entire homes missing bedrooms mention "studio"; no entire home has bedrooms = 0 in the data |
| Otherwise keep bedrooms unknown and add a `bedrooms_missing` flag | Only 1.4% of names mention a bedroom number |
| Apply this during feature building (Milestone 5), not cleaning | It is an interpretation of the name, not a correction of a wrong value |
| Known risk | A name such as "Studio-Loft" may not be a true 0-bedroom home |

---

## 6. Price outliers

| Decision | Evidence |
|---|---|
| Flag a price if its log price is more than **3 IQRs** outside the middle 50% of its **room type + stay type** segment | Judges each listing against similar listings, and treats "too cheap" and "too expensive" equally |
| Flagged listings stay in the data but are **excluded from model training** | 103 listings flagged (0.5%), including $4.58–$12.33 nightly prices, round $10,000 prices, repeated $10,986 prices, and a $30,972.96 listing |
| In Milestone 5, apply the same rule to the model target (pre-discount price) | Keeps the rule consistent with what the model learns |
| Show flagged listings a warning in the health check | "Your price is far outside the normal range for similar listings" |
| Repeated identical prices are **not** used alone as an outlier rule | 52 of 164 listings above $2,000 share an exact price with the same host; this can be legitimate (identical units) |

---

## 7. Demand signal (Milestone 6)

| Decision | Evidence |
|---|---|
| Measure demand using **open-calendar listings** (at least one open night 330+ days ahead) | 13,428 active listings qualify. For them, the jump at day 270 disappears (monthly 2.5%, short 5.1% unavailable) |
| Ignore the step jumps in the raw signal | They fall ~3, 6 and 9 months after the scrape dates (mid-Sep, mid-Dec, mid-Mar), matching Airbnb booking-window settings |
| Compare each date against what is normal **for the same number of days ahead** | Near-term dates are always busier (open-calendar: ~53–61% unavailable in days 0–29, falling to ~2–5% by day 270+) |
| Add a **weekend increase** for short stays | Fri 45.4% and Sat 46.7% unavailable vs Mon 35.3% (short stays, next 90 days) |
| Add **holiday increases** from date-specific peaks | ~72% unavailable around 4 July; rising toward New Year |
| No seasonal adjustment from quoted prices | Short-stay quotes are almost all for June (1,235) and July (264); other months have too few listings |

---

## 8. Known limitations

1. **Listed price is not the booked price.** Prices are what hosts ask, not what guests paid.
2. **Only active listings are modelled.** Unpriced listings are mostly inactive.
3. **No nightly price history.** The calendar has no price columns, so the price calendar is built from rules.
4. **Unavailable does not always mean booked.** Hosts also block dates.
5. **Open-calendar listings may differ** from other listings (for example, more actively managed).
6. **Single snapshot.** Price changes over time cannot be measured.
7. **Short-stay regulation shapes the market.** Results reflect NYC's rules and may not apply to other cities.
8. **Studio inference from names** may be wrong for a small number of listings.
