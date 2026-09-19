"""
Milestone 5 (part 1) - Model table
Builds one row per priced listing with the target and model features.

Excluded on purpose (see docs/eda_decisions.md):
- price, quote columns          -> they contain the answer
- est_revenue_l365d             -> calculated from price (leakage)
- availability, est. occupancy  -> depend on price (reverse cause and effect)

Output: data/gold/nyc/model_table.parquet
"""
from pathlib import Path
import duckdb

GOLD_DIR = Path("data/gold")


def features_sql(source: str) -> str:
    return f"""
    SELECT
        -- identifiers (not features)
        listing_id,
        host_id,

        -- target and training filter
        base_price,
        log_base_price,
        price_outlier,

        -- market segment
        room_type,
        stay_type,
        license_status,
        property_type,

        -- location
        borough,
        neighbourhood,
        latitude,
        longitude,

        -- size
        accommodates,
        bedrooms_filled                                   AS bedrooms,
        bedrooms_missing,
        beds,
        COALESCE(
            bathrooms,
            CASE
                WHEN LOWER(bathrooms_text) LIKE '%half%' THEN 0.5
                ELSE TRY_CAST(REGEXP_EXTRACT(bathrooms_text, '([0-9.]+)', 1) AS DOUBLE)
            END
        )                                                 AS bathrooms,
        LOWER(COALESCE(bathrooms_text, '')) LIKE '%shared%'
                                                          AS shared_bath,
        json_array_length(TRY_CAST(amenities AS JSON))    AS amenities_count,

        -- booking rules
        minimum_nights,
        instant_bookable,

        -- quality and reputation
        rating_overall,
        number_of_reviews,
        COALESCE(reviews_per_month, 0)                    AS reviews_per_month,

        -- host
        host_is_superhost,
        host_listings_count,
        host_years
    FROM read_parquet('{source}')
    WHERE base_price IS NOT NULL
      AND stay_type IS NOT NULL
    """


def build_model_table(city: str) -> None:
    source = (GOLD_DIR / city / "listings_prepared.parquet").as_posix()
    target = (GOLD_DIR / city / "model_table.parquet").as_posix()

    con = duckdb.connect()
    con.execute(f"COPY ({features_sql(source)}) TO '{target}' (FORMAT parquet)")

    rows, trainable = con.execute(f"""
        SELECT COUNT(*), COUNT(*) FILTER (WHERE NOT price_outlier)
        FROM read_parquet('{target}')
    """).fetchone()
    con.close()

    print(f"model table rows      = {rows:,}")
    print(f"usable for training   = {trainable:,}  (outliers excluded)")


if __name__ == "__main__":
    build_model_table("nyc")