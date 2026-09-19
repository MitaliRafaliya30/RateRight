"""
Milestone 4 (part 1) - Prepare
Adds the shared columns decided in Milestone 3 (docs/eda_decisions.md):
stay type, license status, studio-filled bedrooms, base price, outlier flag,
and a price_confidence flag for segments with too little data (Milestone 5).

Output: data/gold/nyc/listings_prepared.parquet
"""
from pathlib import Path
import duckdb

SILVER_DIR = Path("data/silver")
GOLD_DIR = Path("data/gold")

SHORT_STAY_MAX_NIGHTS = 27   # quotes under 28 nights count as short stays
OUTLIER_IQR_MULTIPLIER = 3   # how many IQRs outside the middle 50% counts as extreme
MIN_TRAINING_LISTINGS = 50   # segments with fewer priced, non-outlier listings get price_confidence = "low"


def prepare_sql(source: str) -> str:
    k = OUTLIER_IQR_MULTIPLIER
    min_training = MIN_TRAINING_LISTINGS
    return f"""
    WITH base AS (
        SELECT
            *,

            -- stay type (eda_decisions.md, section 3)
            CASE
                WHEN quote_nights IS NULL                    THEN NULL
                WHEN quote_nights <= {SHORT_STAY_MAX_NIGHTS} THEN 'short stay'
                ELSE 'monthly stay'
            END AS stay_type,

            -- license status (section 3)
            CASE
                WHEN license IS NULL OR TRIM(license) = '' THEN 'no license'
                WHEN LOWER(license) LIKE '%exempt%'        THEN 'exempt'
                ELSE 'registration number'
            END AS license_status,

            -- studio rule (section 5)
            CASE
                WHEN bedrooms IS NULL
                 AND room_type = 'Entire home/apt'
                 AND LOWER(name) LIKE '%studio%' THEN 0
                ELSE bedrooms
            END AS bedrooms_filled,

            -- model target and comparison price (section 2)
            pre_discount_nightly_price AS base_price
        FROM read_parquet('{source}')
    ),

    with_log AS (
        SELECT
            *,
            bedrooms_filled IS NULL AS bedrooms_missing,
            CASE WHEN base_price > 0 THEN LOG10(base_price) END AS log_base_price
        FROM base
    ),

    -- middle 50% of log base price in each room type + stay type segment
    segment_range AS (
        SELECT
            room_type,
            stay_type,
            QUANTILE_CONT(log_base_price, 0.25) AS q1,
            QUANTILE_CONT(log_base_price, 0.75) AS q3
        FROM with_log
        WHERE log_base_price IS NOT NULL
        GROUP BY room_type, stay_type
    ),

    -- how many priced listings exist in each room+stay segment
    -- (used to flag segments too small to trust for pricing)
    segment_size AS (
        SELECT room_type, stay_type, COUNT(*) AS segment_listings
        FROM with_log
        WHERE base_price IS NOT NULL
        GROUP BY room_type, stay_type
    )

    -- outlier flag (section 6) and confidence flag; empty for listings without a price
    SELECT
        w.*,
        CASE
            WHEN w.log_base_price IS NULL THEN NULL
            ELSE w.log_base_price > s.q3 + {k} * (s.q3 - s.q1)
              OR w.log_base_price < s.q1 - {k} * (s.q3 - s.q1)
        END AS price_outlier,
        CASE
            WHEN w.base_price IS NULL THEN NULL
            WHEN COALESCE(sz.segment_listings, 0) < {min_training} THEN 'low'
            ELSE 'normal'
        END AS price_confidence
    FROM with_log w
    LEFT JOIN segment_range s
      ON w.room_type = s.room_type
     AND w.stay_type = s.stay_type
    LEFT JOIN segment_size sz
      ON w.room_type = sz.room_type
     AND w.stay_type = sz.stay_type
    """


def prepare_city(city: str) -> None:
    source = (SILVER_DIR / city / "listings.parquet").as_posix()
    target_path = GOLD_DIR / city / "listings_prepared.parquet"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target = target_path.as_posix()

    con = duckdb.connect()
    con.execute(f"COPY ({prepare_sql(source)}) TO '{target}' (FORMAT parquet)")

    summary = con.execute(f"""
        SELECT
            COUNT(*)                                        AS listings,
            COUNT(base_price)                               AS with_base_price,
            COUNT(*) FILTER (WHERE price_outlier)           AS outliers,
            COUNT(*) FILTER (WHERE bedrooms IS NULL
                             AND bedrooms_filled = 0)       AS studios_filled,
            COUNT(*) FILTER (WHERE base_price IS NOT NULL
                             AND price_confidence = 'low') AS low_confidence
        FROM read_parquet('{target}')
    """).fetchone()
    con.close()

    print(f"listings        = {summary[0]:,}")
    print(f"with base price = {summary[1]:,}")
    print(f"outliers        = {summary[2]:,}")
    print(f"studios filled  = {summary[3]:,}")
    print(f"low confidence  = {summary[4]:,}")


if __name__ == "__main__":
    prepare_city("nyc")