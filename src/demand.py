"""
Milestone 6 (part 1) - Demand baseline
Builds a smoothed curve of expected unavailability by "days ahead",
separately for short stay and monthly stay listings. This baseline
is what later steps compare specific dates against.

Only uses:
- open-calendar listings (calendar reaches 330+ days ahead) -> avoids
  the booking-window artifact found in Milestone 3D
- active (priced) listings -> avoids inactive listings that are always
  unavailable

Output: data/gold/nyc/demand_curve.parquet
"""
from pathlib import Path
import duckdb

GOLD_DIR = Path("data/gold/nyc")
SILVER_DIR = Path("data/silver/nyc")

OPEN_CALENDAR_MIN_DAYS = 330   # a listing counts as "open" if any night
                               # this far ahead is available
SMOOTHING_WINDOW = 3           # days on each side; 3+1+3 = 7-day average


def demand_sql(listings_path: str, calendar_path: str) -> str:
    return f"""
    WITH active_listings AS (
        -- priced (active) listings, with their stay type
        SELECT listing_id, stay_type
        FROM read_parquet('{listings_path}')
        WHERE base_price IS NOT NULL
    ),

    open_listings AS (
        -- listings whose calendar is open ~a year ahead
        -- (see eda_decisions.md, section 7)
        SELECT listing_id
        FROM read_parquet('{calendar_path}')
        WHERE days_from_start >= {OPEN_CALENDAR_MIN_DAYS}
        GROUP BY listing_id
        HAVING BOOL_OR(is_available)
    ),

    daily AS (
        SELECT
            a.stay_type,
            c.days_from_start,
            COUNT(*)                                            AS listings,
            AVG(CASE WHEN c.is_available = FALSE THEN 100.0
                     WHEN c.is_available = TRUE  THEN 0.0 END)   AS pct_unavailable
        FROM read_parquet('{calendar_path}') c
        JOIN active_listings a ON a.listing_id = c.listing_id
        JOIN open_listings   o ON o.listing_id = c.listing_id
        WHERE c.days_from_start < {OPEN_CALENDAR_MIN_DAYS}
        GROUP BY a.stay_type, c.days_from_start
    )

    -- smooth with a 7-day rolling average, per stay type
    SELECT
        stay_type,
        days_from_start                                          AS days_ahead,
        listings,
        ROUND(pct_unavailable, 1)                                AS pct_unavailable_raw,
        ROUND(
            AVG(pct_unavailable) OVER (
                PARTITION BY stay_type
                ORDER BY days_from_start
                ROWS BETWEEN {SMOOTHING_WINDOW} PRECEDING AND {SMOOTHING_WINDOW} FOLLOWING
            ), 1
        )                                                        AS pct_unavailable_smoothed
    FROM daily
    ORDER BY stay_type, days_from_start
    """


def build_demand_curve(city: str) -> None:
    listings_path = (GOLD_DIR / "listings_prepared.parquet").as_posix()
    calendar_path = (SILVER_DIR / "calendar.parquet").as_posix()
    target = (GOLD_DIR / "demand_curve.parquet").as_posix()

    con = duckdb.connect()
    con.execute(f"COPY ({demand_sql(listings_path, calendar_path)}) "
                f"TO '{target}' (FORMAT parquet)")

    summary = con.execute(f"""
        SELECT
            stay_type,
            COUNT(*)                        AS days_covered,
            MIN(listings)                   AS fewest_listings_on_a_day,
            ROUND(AVG(pct_unavailable_smoothed), 1) AS overall_avg_unavailable
        FROM read_parquet('{target}')
        GROUP BY stay_type
    """).df()
    con.close()

    print(summary.to_string(index=False))


if __name__ == "__main__":
    build_demand_curve("nyc")