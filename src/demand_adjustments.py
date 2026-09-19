"""
Milestone 6 (part 2) - Weekday and holiday adjustments
For short-stay listings, measures how much specific weekdays and
specific dates run hotter or cooler than the days-ahead baseline
(Step 6.1) predicts. The difference (observed - expected) isolates
the weekday/date effect from the already-known "near-term is busier"
trend.

Only uses open-calendar + active listings, days_from_start < 180
(the range with the clearest signal, per eda_decisions.md section 7).

Output:
- data/gold/nyc/weekday_adjustment.parquet
- data/gold/nyc/date_adjustment.parquet
"""
from pathlib import Path
import duckdb

GOLD_DIR = Path("data/gold/nyc")
SILVER_DIR = Path("data/silver/nyc")

OPEN_CALENDAR_MIN_DAYS = 330
RELIABLE_DAYS_AHEAD = 180   # beyond this, the baseline is near 0% and noisy


def excess_rows_sql(listings_path: str, calendar_path: str, curve_path: str) -> str:
    """Every short-stay listing-night, with observed vs expected unavailability."""
    return f"""
    WITH short_stay_listings AS (
        SELECT listing_id
        FROM read_parquet('{listings_path}')
        WHERE base_price IS NOT NULL AND stay_type = 'short stay'
    ),

    open_listings AS (
        SELECT listing_id
        FROM read_parquet('{calendar_path}')
        WHERE days_from_start >= {OPEN_CALENDAR_MIN_DAYS}
        GROUP BY listing_id
        HAVING BOOL_OR(is_available)
    )

    SELECT
        c.calendar_date,
        c.days_from_start,
        CASE WHEN c.is_available = FALSE THEN 100.0
             WHEN c.is_available = TRUE  THEN 0.0 END        AS observed,
        curve.pct_unavailable_smoothed                       AS expected
    FROM read_parquet('{calendar_path}') c
    JOIN short_stay_listings s ON s.listing_id = c.listing_id
    JOIN open_listings       o ON o.listing_id = c.listing_id
    JOIN read_parquet('{curve_path}') curve
      ON curve.stay_type = 'short stay'
     AND curve.days_ahead = c.days_from_start
    WHERE c.days_from_start < {RELIABLE_DAYS_AHEAD}
      AND c.is_available IS NOT NULL
    """


def weekday_sql(excess_rows: str) -> str:
    return f"""
    WITH rows AS ({excess_rows})
    SELECT
        ISODOW(calendar_date)          AS day_number,   -- 1 = Monday ... 7 = Sunday
        DAYNAME(calendar_date)         AS day_name,
        COUNT(*)                       AS listing_nights,
        ROUND(AVG(observed), 1)        AS avg_observed_pct,
        ROUND(AVG(expected), 1)        AS avg_expected_pct,
        ROUND(AVG(observed - expected), 1) AS avg_excess_pct
    FROM rows
    GROUP BY 1, 2
    ORDER BY 1
    """


def date_sql(excess_rows: str) -> str:
    return f"""
    WITH rows AS ({excess_rows})
    SELECT
        calendar_date,
        DAYNAME(calendar_date)             AS day_name,
        COUNT(*)                           AS listing_nights,
        ROUND(AVG(observed), 1)            AS avg_observed_pct,
        ROUND(AVG(expected), 1)            AS avg_expected_pct,
        ROUND(AVG(observed - expected), 1) AS excess_pct
    FROM rows
    GROUP BY 1, 2
    ORDER BY calendar_date
    """


def build_adjustments(city: str) -> None:
    listings_path = (GOLD_DIR / "listings_prepared.parquet").as_posix()
    calendar_path = (SILVER_DIR / "calendar.parquet").as_posix()
    curve_path = (GOLD_DIR / "demand_curve.parquet").as_posix()

    excess_rows = excess_rows_sql(listings_path, calendar_path, curve_path)

    con = duckdb.connect()

    weekday_target = (GOLD_DIR / "weekday_adjustment.parquet").as_posix()
    con.execute(f"COPY ({weekday_sql(excess_rows)}) TO '{weekday_target}' (FORMAT parquet)")

    date_target = (GOLD_DIR / "date_adjustment.parquet").as_posix()
    con.execute(f"COPY ({date_sql(excess_rows)}) TO '{date_target}' (FORMAT parquet)")

    print("Weekday adjustment:")
    print(con.execute(f"SELECT * FROM read_parquet('{weekday_target}')").df().to_string(index=False))

    print()
    print("Date adjustment - top 10 highest-excess dates:")
    print(con.execute(f"""
        SELECT * FROM read_parquet('{date_target}')
        ORDER BY excess_pct DESC LIMIT 10
    """).df().to_string(index=False))

    con.close()


if __name__ == "__main__":
    build_adjustments("nyc")