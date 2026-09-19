"""
Milestone 6 (part 3) - Price calendar
Combines base price (Milestone 5), the days-ahead demand baseline
(Step 6.1), and weekday/date demand excess (Step 6.2) into a 90-day
suggested nightly price per listing.

IMPORTANT ASSUMPTION: there is no price/booking history in this data,
so the excess-to-price conversion below is a capped, rule-based
adjustment, not a learned price elasticity. See docs/eda_decisions.md.

Only short-stay listings get a day-by-day price; monthly-stay listings
are quoted once for a full stay and get a flat calendar at their base
price.

Output: data/gold/nyc/price_calendar.parquet
"""
from pathlib import Path
import duckdb

GOLD_DIR = Path("data/gold/nyc")
SILVER_DIR = Path("data/silver/nyc")

CALENDAR_START = "2026-06-23"   # first date every listing's calendar covers
CALENDAR_DAYS = 90

# Rule-based excess -> price adjustment (see limitation above)
SENSITIVITY = 1.5     # 1 percentage point of excess demand -> 1.5% price change
MAX_ADJUSTMENT = 0.15  # cap: price moves at most +/-15% from base


def price_calendar_sql(listings_path: str, calendar_path: str,
                        demand_curve_path: str, weekday_path: str,
                        date_adj_path: str) -> str:
    return f"""
    WITH listings AS (
        SELECT listing_id, stay_type, base_price, price_confidence
        FROM read_parquet('{listings_path}')
        WHERE base_price IS NOT NULL
    ),

    calendar_window AS (
        SELECT listing_id, calendar_date, days_from_start,
               ISODOW(calendar_date) AS day_number
        FROM read_parquet('{calendar_path}')
        WHERE calendar_date >= DATE '{CALENDAR_START}'
          AND calendar_date <  DATE '{CALENDAR_START}' + INTERVAL '{CALENDAR_DAYS} days'
    ),

    -- excess for short stays: prefer the exact date, else the weekday-only figure
    excess AS (
        SELECT
            cw.listing_id,
            cw.calendar_date,
            cw.days_from_start,
            COALESCE(da.excess_pct, wa.avg_excess_pct, 0.0) AS excess_pct,
            (da.excess_pct IS NOT NULL)                     AS used_date_specific
        FROM calendar_window cw
        LEFT JOIN read_parquet('{date_adj_path}') da
          ON da.calendar_date = cw.calendar_date
        LEFT JOIN read_parquet('{weekday_path}') wa
          ON wa.day_number = cw.day_number
    )

    SELECT
        l.listing_id,
        l.stay_type,
        l.price_confidence,
        e.calendar_date,
        e.days_from_start,
        l.base_price,

        CASE
            WHEN l.stay_type = 'monthly stay' THEN 0.0   -- flat calendar, no adjustment
            ELSE GREATEST(-{MAX_ADJUSTMENT}, LEAST({MAX_ADJUSTMENT},
                     (e.excess_pct / 100.0) * {SENSITIVITY}))
        END                                                AS price_adjustment_pct,

        ROUND(
            l.base_price * (1 + CASE
                WHEN l.stay_type = 'monthly stay' THEN 0.0
                ELSE GREATEST(-{MAX_ADJUSTMENT}, LEAST({MAX_ADJUSTMENT},
                         (e.excess_pct / 100.0) * {SENSITIVITY}))
            END), 2
        )                                                  AS suggested_price,

        CASE WHEN l.stay_type = 'short stay' THEN e.used_date_specific
             ELSE NULL END                                 AS used_date_specific_excess
    FROM listings l
    JOIN excess e ON e.listing_id = l.listing_id
    """


def build_price_calendar(city: str) -> None:
    listings_path = (GOLD_DIR / "listings_prepared.parquet").as_posix()
    calendar_path = (SILVER_DIR / "calendar.parquet").as_posix()
    demand_curve_path = (GOLD_DIR / "demand_curve.parquet").as_posix()
    weekday_path = (GOLD_DIR / "weekday_adjustment.parquet").as_posix()
    date_adj_path = (GOLD_DIR / "date_adjustment.parquet").as_posix()
    target = (GOLD_DIR / "price_calendar.parquet").as_posix()

    con = duckdb.connect()
    con.execute(f"""
        COPY ({price_calendar_sql(listings_path, calendar_path, demand_curve_path,
                                   weekday_path, date_adj_path)})
        TO '{target}' (FORMAT parquet)
    """)

    summary = con.execute(f"""
        SELECT
            stay_type,
            COUNT(DISTINCT listing_id)              AS listings,
            COUNT(*)                                AS listing_nights,
            ROUND(MIN(price_adjustment_pct) * 100, 1) AS min_adj_pct,
            ROUND(MAX(price_adjustment_pct) * 100, 1) AS max_adj_pct,
            ROUND(AVG(suggested_price - base_price), 2) AS avg_dollar_change
        FROM read_parquet('{target}')
        GROUP BY stay_type
    """).df()
    con.close()

    print(summary.to_string(index=False))


if __name__ == "__main__":
    build_price_calendar("nyc")