"""
Milestone 8 - Plain-English diagnosis generator
Turns each listing's health flags (Milestone 7) into 2-4 hedged,
number-backed sentences a host could read directly. Template-based
(not an LLM), so every sentence is guaranteed to trace back to a real
calculated value.

Output: data/gold/nyc/diagnosis.parquet
"""
from pathlib import Path
import duckdb
import pandas as pd

GOLD_DIR = Path("data/gold/nyc")
MAX_ISSUES_SHOWN = 3

# Ordered by deduction size (Milestone 7), most serious first.
# Each entry: (flag_column, deduction, sentence_function)

def sentence_price_outlier(row) -> str:
    return (f"Your price of ${row.base_price:,.0f} is far outside the normal "
            f"range for similar listings — worth double-checking it's set correctly.")

def sentence_overpriced(row) -> str:
    comparison = "every comparable listing nearby" if row.pct_comps_cheaper >= 99.5 \
        else f"{row.pct_comps_cheaper:.0f}% of comparable listings nearby"
    return (f"Your price of ${row.base_price:,.0f} is higher than {comparison} "
            f"(median ${row.comp_median:,.0f}) — worth checking if that's intentional.")

def sentence_high_availability(row) -> str:
    pct_open = 100 * row.availability_30 / 30
    pct_open_typical = 100 * row.avg_availability_30 / 30
    return (f"Your calendar is {pct_open:.0f}% open in the next 30 days, versus "
            f"{pct_open_typical:.0f}% for similar listings — this could mean the "
            f"price or listing needs a closer look.")

def sentence_gone_quiet(row) -> str:
    return (f"You have {row.number_of_reviews:.0f} reviews total, but none in the "
            f"last 12 months — worth checking if something has changed with "
            f"visibility or pricing.")

def sentence_rating_gap(row) -> str:
    return (f"Your rating ({row.rating_overall:.2f}) sits below similar listings "
            f"nearby ({row.avg_rating:.2f}) — worth reviewing recent guest feedback.")

def sentence_restrictive_stay(row) -> str:
    return (f"Your minimum stay of {row.minimum_nights:.0f} nights is well above "
            f"similar listings ({row.avg_min_nights_short:.1f}) — this may be "
            f"excluding short-stay guests.")

def sentence_underpriced(row) -> str:
    return (f"Your price of ${row.base_price:,.0f} is lower than "
            f"{100 - row.pct_comps_cheaper:.0f}% of comparable listings "
            f"(median ${row.comp_median:,.0f}) — there may be room to raise it.")


ISSUE_ORDER = [
    ("flag_price_outlier",      25, sentence_price_outlier),
    ("flag_overpriced",         20, sentence_overpriced),
    ("flag_high_availability",  20, sentence_high_availability),
    ("flag_gone_quiet",         15, sentence_gone_quiet),
    ("flag_rating_gap",         15, sentence_rating_gap),
    ("flag_underpriced",        10, sentence_underpriced),
    ("flag_restrictive_stay",   10, sentence_restrictive_stay),
]


def build_diagnosis_row(row) -> dict:
    sentences = []
    for flag_col, _deduction, sentence_fn in ISSUE_ORDER:
        if getattr(row, flag_col):
            try:
                sentences.append(sentence_fn(row))
            except (TypeError, ValueError):
                # A required number was missing (e.g. no rating) -> skip
                # this sentence rather than crash or print "nan"
                continue
        if len(sentences) >= MAX_ISSUES_SHOWN:
            break

    if not sentences:
        summary = (f"Your listing looks healthy overall (score {row.health_score}/100) "
                   f"— priced in line with similar listings, with a reasonably "
                   f"full calendar and no major warning signs.")
    else:
        intro = f"Health score: {row.health_score}/100. "
        summary = intro + " ".join(sentences)

    if row.price_confidence == "low":
        summary = ("Note: there aren't many similar listings to compare against, "
                   "so treat this assessment as a rough guide. ") + summary

    return {
        "listing_id": row.listing_id,
        "diagnosis": summary,
        "issues_shown": len(sentences),
    }


def build_diagnoses(city: str) -> None:
    health_path = (GOLD_DIR / "health_score.parquet").as_posix()
    target = (GOLD_DIR / "diagnosis.parquet").as_posix()

    health = duckdb.sql(f"SELECT * FROM read_parquet('{health_path}')").df()

    results = [build_diagnosis_row(row) for row in health.itertuples(index=False)]
    diagnoses = pd.DataFrame(results)
    diagnoses.to_parquet(target, index=False)

    print(f"Listings processed: {len(diagnoses):,}")
    print(f"Healthy (no issues shown): {(diagnoses['issues_shown'] == 0).sum():,}")
    print(f"With 1 issue: {(diagnoses['issues_shown'] == 1).sum():,}")
    print(f"With 2 issues: {(diagnoses['issues_shown'] == 2).sum():,}")
    print(f"With 3 issues: {(diagnoses['issues_shown'] == 3).sum():,}")


if __name__ == "__main__":
    build_diagnoses("nyc")