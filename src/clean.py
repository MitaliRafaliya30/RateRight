"""
Milestone 2 - Clean
Reads bronze Parquet files, fixes types and known data problems,
and saves cleaned (silver) Parquet files.

Rule: fix what is wrong; do not decide what it means yet.
Data source: Inside Airbnb - New York City, snapshot dated 14 June 2026
"""
from pathlib import Path
import duckdb

BRONZE_DIR = Path("data/bronze")
SILVER_DIR = Path("data/silver")

# "No limit" placeholder found in maximum_nights (largest 32-bit integer)
MAX_NIGHTS_PLACEHOLDER = 2147483647


# ---------------------------------------------------------------------------
# Helper functions: each returns a small piece of SQL for one cleaning rule
# ---------------------------------------------------------------------------

def money(col: str) -> str:
    """'$1,250.00' -> 1250.00 (empty if it cannot be converted)."""
    return f"TRY_CAST(REPLACE(REPLACE({col}, '$', ''), ',', '') AS DOUBLE)"


def boolean(col: str) -> str:
    """'t' -> TRUE, 'f' -> FALSE, anything else -> empty (we do not guess)."""
    return f"CASE {col} WHEN 't' THEN TRUE WHEN 'f' THEN FALSE END"


def percent(col: str) -> str:
    """'95%' -> 95.0 (kept on a 0-100 scale)."""
    return f"TRY_CAST(REPLACE({col}, '%', '') AS DOUBLE)"


def rating(col: str) -> str:
    """Ratings run from 1 to 5, so a 0 is a placeholder -> empty."""
    return f"NULLIF(TRY_CAST({col} AS DOUBLE), 0)"


def max_nights(col: str) -> str:
    """Replace the 'no limit' placeholder with empty."""
    return f"NULLIF(TRY_CAST({col} AS BIGINT), {MAX_NIGHTS_PLACEHOLDER})"


def quote_number(field: str) -> str:
    """Read one number from the price_quote_raw JSON text."""
    return (f"TRY_CAST(json_extract_string(price_quote_raw, "
            f"'$.quote.{field}') AS DOUBLE)")


# ---------------------------------------------------------------------------
# Cleaning queries
# ---------------------------------------------------------------------------

def listings_sql(source: str) -> str:
    return f"""
    WITH typed AS (
        SELECT
            -- identity and snapshot
            TRY_CAST(id AS BIGINT)                          AS listing_id,
            TRY_CAST(host_id AS BIGINT)                     AS host_id,
            TRY_CAST(last_scraped AS DATE)                  AS last_scraped,
            name,

            -- location
            neighbourhood_cleansed                          AS neighbourhood,
            neighbourhood_group_cleansed                    AS borough,
            TRY_CAST(latitude AS DOUBLE)                    AS latitude,
            TRY_CAST(longitude AS DOUBLE)                   AS longitude,

            -- property
            property_type,
            room_type,
            TRY_CAST(accommodates AS BIGINT)                AS accommodates,
            TRY_CAST(bedrooms AS DOUBLE)                    AS bedrooms,
            TRY_CAST(beds AS DOUBLE)                        AS beds,
            TRY_CAST(bathrooms AS DOUBLE)                   AS bathrooms,
            bathrooms_text,
            amenities,

            -- price (after any length-of-stay discount, no fees)
            {money('price')}                                AS price,
            TRY_CAST(price_quote_checkin_date AS DATE)      AS quote_checkin_date,
            TRY_CAST(price_quote_checkout_date AS DATE)     AS quote_checkout_date,
            TRY_CAST(price_quote_total_price AS DOUBLE)     AS quote_total,
            {quote_number('discount_amount')}               AS raw_discount,

            -- booking rules
            TRY_CAST(minimum_nights AS BIGINT)              AS minimum_nights,
            {max_nights('maximum_nights')}                  AS maximum_nights,
            {boolean('instant_bookable')}                   AS instant_bookable,

            -- availability (counted from each listing's scrape date)
            TRY_CAST(availability_30 AS BIGINT)             AS availability_30,
            TRY_CAST(availability_60 AS BIGINT)             AS availability_60,
            TRY_CAST(availability_90 AS BIGINT)             AS availability_90,
            TRY_CAST(availability_365 AS BIGINT)            AS availability_365,

            -- reviews
            TRY_CAST(number_of_reviews AS BIGINT)           AS number_of_reviews,
            TRY_CAST(number_of_reviews_ltm AS BIGINT)       AS number_of_reviews_ltm,
            TRY_CAST(number_of_reviews_l30d AS BIGINT)      AS number_of_reviews_l30d,
            TRY_CAST(reviews_per_month AS DOUBLE)           AS reviews_per_month,
            TRY_CAST(first_review AS DATE)                  AS first_review,
            TRY_CAST(last_review AS DATE)                   AS last_review,
            {rating('review_scores_rating')}                AS rating_overall,
            {rating('review_scores_accuracy')}              AS rating_accuracy,
            {rating('review_scores_cleanliness')}           AS rating_cleanliness,
            {rating('review_scores_checkin')}               AS rating_checkin,
            {rating('review_scores_communication')}         AS rating_communication,
            {rating('review_scores_location')}              AS rating_location,
            {rating('review_scores_value')}                 AS rating_value,

            -- host
            TRY_CAST(host_since AS DATE)                    AS host_since,
            TRY_CAST(hosts_time_as_host_years AS DOUBLE)    AS host_years,
            {boolean('host_is_superhost')}                  AS host_is_superhost,
            {boolean('host_identity_verified')}             AS host_identity_verified,
            host_response_time,
            {percent('host_response_rate')}                 AS host_response_rate,
            {percent('host_acceptance_rate')}               AS host_acceptance_rate,
            TRY_CAST(calculated_host_listings_count AS BIGINT)
                                                            AS host_listings_count,

            -- estimates made by the data provider (not real bookings)
            TRY_CAST(estimated_occupancy_l365d AS BIGINT)   AS est_occupancy_nights_l365d,
            TRY_CAST(estimated_revenue_l365d AS DOUBLE)     AS est_revenue_l365d,

            license
        FROM read_parquet('{source}')
    )
    SELECT
        * EXCLUDE (raw_discount),

        -- length of the quoted stay
        quote_checkout_date - quote_checkin_date            AS quote_nights,

        -- discount: 0 when a priced quote had no discount
        CASE WHEN price IS NOT NULL
             THEN COALESCE(raw_discount, 0) END             AS quote_discount,

        -- nightly price before the discount
        -- (not rounded here: rounding happens only when displaying values)
        CASE WHEN price IS NOT NULL
              AND quote_checkout_date > quote_checkin_date
             THEN (quote_total + COALESCE(raw_discount, 0))
                  / (quote_checkout_date - quote_checkin_date)
        END                                                 AS pre_discount_nightly_price
    FROM typed
    """


def calendar_sql(source: str, silver_listings: str) -> str:
    return f"""
    SELECT
        TRY_CAST(listing_id AS BIGINT)                      AS listing_id,
        TRY_CAST(date AS DATE)                              AS calendar_date,
        {boolean('available')}                              AS is_available,
        TRY_CAST(minimum_nights AS BIGINT)                  AS minimum_nights,
        {max_nights('maximum_nights')}                      AS maximum_nights,

        -- 0 = the listing's first calendar day (its scrape day)
        TRY_CAST(date AS DATE)
          - MIN(TRY_CAST(date AS DATE)) OVER (PARTITION BY listing_id)
                                                            AS days_from_start
    FROM read_parquet('{source}')
    -- keep only listings that exist in the cleaned listings table
    WHERE TRY_CAST(listing_id AS BIGINT) IN (
        SELECT listing_id FROM read_parquet('{silver_listings}')
    )
    """


def reviews_sql(source: str, silver_listings: str) -> str:
    return f"""
    SELECT
        TRY_CAST(id AS BIGINT)                              AS review_id,
        TRY_CAST(listing_id AS BIGINT)                      AS listing_id,
        TRY_CAST(date AS DATE)                              AS review_date,
        TRY_CAST(reviewer_id AS BIGINT)                     AS reviewer_id
    FROM read_parquet('{source}')
    WHERE TRY_CAST(listing_id AS BIGINT) IN (
        SELECT listing_id FROM read_parquet('{silver_listings}')
    )
    """


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def save(con, query: str, target_path: Path) -> int:
    """Write a query result to Parquet and return its row count."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target = target_path.as_posix()
    con.execute(f"COPY ({query}) TO '{target}' (FORMAT parquet)")
    return con.execute(
        f"SELECT COUNT(*) FROM read_parquet('{target}')"
    ).fetchone()[0]


def clean_city(city: str) -> None:
    bronze = BRONZE_DIR / city
    silver = SILVER_DIR / city
    silver_listings = (silver / "listings.parquet").as_posix()

    con = duckdb.connect()

    # Listings first: calendar and reviews are filtered against it
    steps = [
        ("listings", listings_sql((bronze / "listings.parquet").as_posix())),
        ("calendar", calendar_sql((bronze / "calendar.parquet").as_posix(), silver_listings)),
        ("reviews",  reviews_sql((bronze / "reviews.parquet").as_posix(), silver_listings)),
    ]

    for name, query in steps:
        rows = save(con, query, silver / f"{name}.parquet")
        print(f"{name:<10} rows = {rows:>12,}")

    con.close()


if __name__ == "__main__":
    clean_city("nyc")