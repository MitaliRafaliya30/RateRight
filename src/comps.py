"""
Milestone 4 (part 2) - Comparable listings
For each priced listing, finds a group of similar listings using a
fallback chain, then compares the listing's base price with that group.

Output: data/gold/nyc/comps.parquet
"""
from pathlib import Path
import duckdb

GOLD_DIR = Path("data/gold")
MIN_COMPS = 10   # minimum number of OTHER listings in a comparison group

# Narrowest group first (eda_decisions.md, section 4)
LEVELS = {
    1: ["neighbourhood", "room_type", "stay_type", "bedrooms_key"],
    2: ["neighbourhood", "room_type", "stay_type"],
    3: ["borough", "room_type", "stay_type"],
    4: ["room_type", "stay_type"],
}


def key_sql(columns: list[str]) -> str:
    """Join several columns into one text key, e.g. 'Chelsea|Private room|short stay'."""
    parts = ", ".join(f"CAST({col} AS VARCHAR)" for col in columns)
    return f"CONCAT_WS('|', {parts})"


def comps_sql(source: str) -> str:
    # One SELECT per level, stacked together with UNION ALL
    keys_per_level = "\n        UNION ALL\n".join(
        f"""        SELECT listing_id, base_price, price_outlier,
               {level} AS level,
               {key_sql(columns)} AS group_key
        FROM listings"""
        for level, columns in LEVELS.items()
    )

    return f"""
    WITH listings AS (
        SELECT
            listing_id, base_price, price_outlier,
            neighbourhood, borough, room_type, stay_type,
            COALESCE(CAST(bedrooms_filled AS VARCHAR), 'unknown') AS bedrooms_key
        FROM read_parquet('{source}')
        WHERE base_price IS NOT NULL
          AND stay_type IS NOT NULL
    ),

    -- each listing's group key at every level (4 rows per listing)
    keys AS (
{keys_per_level}
    ),

    -- listings allowed to act as comps (outliers excluded)
    pool AS (
        SELECT * FROM keys WHERE NOT price_outlier
    ),

    pool_counts AS (
        SELECT level, group_key, COUNT(*) AS pool_size
        FROM pool
        GROUP BY level, group_key
    ),

    -- number of OTHER comps each listing would get at each level
    candidates AS (
        SELECT
            k.listing_id,
            k.level,
            k.group_key,
            COALESCE(c.pool_size, 0)
              - CASE WHEN k.price_outlier THEN 0 ELSE 1 END AS other_listings
        FROM keys k
        LEFT JOIN pool_counts c
          ON c.level = k.level
         AND c.group_key = k.group_key
    ),

    -- first level with enough comps (level 4 is always accepted)
    chosen AS (
        SELECT listing_id, level, group_key
        FROM candidates
        WHERE other_listings >= {MIN_COMPS} OR level = 4
        QUALIFY ROW_NUMBER() OVER (PARTITION BY listing_id ORDER BY level) = 1
    ),

    stats AS (
        SELECT
            ch.listing_id,
            ch.level                                            AS comp_level,
            COUNT(*)                                            AS comp_count,
            QUANTILE_CONT(p.base_price, 0.25)                   AS comp_p25,
            MEDIAN(p.base_price)                                AS comp_median,
            QUANTILE_CONT(p.base_price, 0.75)                   AS comp_p75,
            AVG(CASE WHEN p.base_price < l.base_price
                     THEN 100.0 ELSE 0.0 END)                   AS pct_comps_cheaper
        FROM chosen ch
        JOIN listings l
          ON l.listing_id = ch.listing_id
        JOIN pool p
          ON p.level = ch.level
         AND p.group_key = ch.group_key
         AND p.listing_id <> ch.listing_id      -- never compare with itself
        GROUP BY ch.listing_id, ch.level
    )

    SELECT
        s.listing_id,
        l.base_price,
        l.price_outlier,
        s.comp_level,
        s.comp_count,
        s.comp_p25,
        s.comp_median,
        s.comp_p75,
        s.pct_comps_cheaper,
        100.0 * (l.base_price - s.comp_median) / s.comp_median AS gap_vs_median_pct
    FROM stats s
    JOIN listings l ON l.listing_id = s.listing_id
    """


def build_comps(city: str) -> None:
    source = (GOLD_DIR / city / "listings_prepared.parquet").as_posix()
    target = (GOLD_DIR / city / "comps.parquet").as_posix()

    con = duckdb.connect()
    con.execute(f"COPY ({comps_sql(source)}) TO '{target}' (FORMAT parquet)")

    print(con.execute(f"""
        SELECT comp_level,
               COUNT(*)                                          AS listings,
               ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct,
               MIN(comp_count)                                   AS smallest_group
        FROM read_parquet('{target}')
        GROUP BY comp_level
        ORDER BY comp_level
    """).df().to_string(index=False))
    con.close()


if __name__ == "__main__":
    build_comps("nyc")