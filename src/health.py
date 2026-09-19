"""
Milestone 7 - Listing health score
Combines comparable-listing position (Milestone 4), price model flags
(Milestone 5), and raw listing signals into a transparent, rule-based
0-100 health score with named flags.

Benchmark groups here use a single borough + room_type + stay_type
grouping (simpler than Milestone 4's price comp fallback), since these
are directional signals, not precise price comparisons.

Output: data/gold/nyc/health_score.parquet
"""
from pathlib import Path
import duckdb

GOLD_DIR = Path("data/gold/nyc")

# How many times the segment average counts as "unusually high"
AVAILABILITY_RATIO_THRESHOLD = 1.5   # 50% more empty nights than typical
MIN_NIGHTS_RATIO_THRESHOLD = 1.5     # 50% higher minimum stay than typical
RATING_GAP_THRESHOLD = 0.3           # rating points below segment average

DEDUCTIONS = {
    "flag_overpriced": 20,
    "flag_underpriced": 10,
    "flag_high_availability": 20,
    "flag_gone_quiet": 15,
    "flag_rating_gap": 15,
    "flag_restrictive_stay": 10,
    "flag_price_outlier": 25,
}


def health_sql(listings_path: str, comps_path: str) -> str:
    return f"""
    WITH listings AS (
        SELECT
            listing_id, room_type, stay_type, borough, neighbourhood,
            base_price, price_outlier, price_confidence,
            availability_30, number_of_reviews, number_of_reviews_ltm,
            rating_overall, minimum_nights
        FROM read_parquet('{listings_path}')
        WHERE base_price IS NOT NULL
    ),

    -- simple benchmark groups: borough + room type + stay type
    segment_benchmark AS (
        SELECT
            borough, room_type, stay_type,
            AVG(availability_30)                              AS avg_availability_30,
            AVG(rating_overall)                                AS avg_rating,
            AVG(minimum_nights) FILTER (WHERE stay_type = 'short stay')
                                                                AS avg_min_nights_short
        FROM listings
        WHERE NOT price_outlier
        GROUP BY borough, room_type, stay_type
    ),

    flagged AS (
        SELECT
            l.*,
            c.comp_level, c.comp_count, c.comp_median,
            c.pct_comps_cheaper, c.gap_vs_median_pct,
            b.avg_availability_30, b.avg_rating, b.avg_min_nights_short,

            (c.pct_comps_cheaper >= 75)                        AS flag_overpriced,
            (c.pct_comps_cheaper <= 25)                         AS flag_underpriced,

            (l.availability_30 IS NOT NULL
             AND b.avg_availability_30 > 0
             AND l.availability_30 > b.avg_availability_30 * {AVAILABILITY_RATIO_THRESHOLD}
            )                                                   AS flag_high_availability,

            (l.number_of_reviews > 0
             AND l.number_of_reviews_ltm = 0
            )                                                   AS flag_gone_quiet,

            (l.rating_overall IS NOT NULL
             AND l.rating_overall < b.avg_rating - {RATING_GAP_THRESHOLD}
            )                                                   AS flag_rating_gap,

            (l.stay_type = 'short stay'
 AND COALESCE(b.avg_min_nights_short, 0) > 0
 AND COALESCE(l.minimum_nights, 0) > COALESCE(b.avg_min_nights_short, 0) * {MIN_NIGHTS_RATIO_THRESHOLD}
)                                                   AS flag_restrictive_stay,

            l.price_outlier                                    AS flag_price_outlier
        FROM listings l
        JOIN read_parquet('{comps_path}') c ON c.listing_id = l.listing_id
        LEFT JOIN segment_benchmark b
          ON b.borough = l.borough AND b.room_type = l.room_type AND b.stay_type = l.stay_type
    )

    SELECT
        *,
        GREATEST(0, 100
            - (COALESCE(flag_overpriced, FALSE)::INT          * {DEDUCTIONS['flag_overpriced']})
            - (COALESCE(flag_underpriced, FALSE)::INT         * {DEDUCTIONS['flag_underpriced']})
            - (COALESCE(flag_high_availability, FALSE)::INT   * {DEDUCTIONS['flag_high_availability']})
            - (COALESCE(flag_gone_quiet, FALSE)::INT          * {DEDUCTIONS['flag_gone_quiet']})
            - (COALESCE(flag_rating_gap, FALSE)::INT          * {DEDUCTIONS['flag_rating_gap']})
            - (COALESCE(flag_restrictive_stay, FALSE)::INT    * {DEDUCTIONS['flag_restrictive_stay']})
            - (COALESCE(flag_price_outlier, FALSE)::INT       * {DEDUCTIONS['flag_price_outlier']})
) AS health_score
    FROM flagged
    """


def build_health_score(city: str) -> None:
    listings_path = (GOLD_DIR / "listings_prepared.parquet").as_posix()
    comps_path = (GOLD_DIR / "comps.parquet").as_posix()
    target = (GOLD_DIR / "health_score.parquet").as_posix()

    con = duckdb.connect()
    con.execute(f"COPY ({health_sql(listings_path, comps_path)}) TO '{target}' (FORMAT parquet)")

    summary = con.execute(f"""
        SELECT
            COUNT(*)                                              AS listings,
            ROUND(AVG(health_score), 1)                           AS avg_score,
            COUNT(*) FILTER (WHERE flag_overpriced)                AS overpriced,
            COUNT(*) FILTER (WHERE flag_underpriced)               AS underpriced,
            COUNT(*) FILTER (WHERE flag_high_availability)         AS high_availability,
            COUNT(*) FILTER (WHERE flag_gone_quiet)                AS gone_quiet,
            COUNT(*) FILTER (WHERE flag_rating_gap)                AS rating_gap,
            COUNT(*) FILTER (WHERE flag_restrictive_stay)          AS restrictive_stay,
            COUNT(*) FILTER (WHERE flag_price_outlier)             AS price_outlier_flag,
            COUNT(*) FILTER (WHERE health_score < 50)              AS below_50
        FROM read_parquet('{target}')
    """).df()
    con.close()

    print(summary.T.to_string())


if __name__ == "__main__":
    build_health_score("nyc")