"""
Milestone 9 - RateRight Streamlit app
A pricing and health-check assistant for short-term rental hosts,
built entirely on the Gold-layer outputs from Milestones 4-8.
"""
import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

GOLD = "data/gold/nyc"

st.set_page_config(page_title="RateRight", page_icon="🏠", layout="wide")


@st.cache_data
def load_data():
    listings = duckdb.sql(f"""
        SELECT * FROM read_parquet('{GOLD}/listings_prepared.parquet')
        WHERE base_price IS NOT NULL
    """).df()
    comps = duckdb.sql(f"SELECT * FROM read_parquet('{GOLD}/comps.parquet')").df()
    health = duckdb.sql(f"SELECT * FROM read_parquet('{GOLD}/health_score.parquet')").df()
    diagnosis = duckdb.sql(f"SELECT * FROM read_parquet('{GOLD}/diagnosis.parquet')").df()
    calendar = duckdb.sql(f"SELECT * FROM read_parquet('{GOLD}/price_calendar.parquet')").df()
    demand_curve = duckdb.sql(f"SELECT * FROM read_parquet('{GOLD}/demand_curve.parquet')").df()
    weekday = duckdb.sql(f"SELECT * FROM read_parquet('{GOLD}/weekday_adjustment.parquet')").df()

    listings = listings.merge(comps, on="listing_id", suffixes=("", "_comp"))
    listings = listings.merge(
        health[["listing_id", "health_score"] + [c for c in health.columns if c.startswith("flag_")]],
        on="listing_id"
    )
    listings = listings.merge(diagnosis[["listing_id", "diagnosis"]], on="listing_id")

    return listings, calendar, demand_curve, weekday


listings, calendar, demand_curve, weekday = load_data()

st.sidebar.title("🏠 RateRight")
page = st.sidebar.radio("View", ["Listing Lookup", "Market Overview"])


# ---------------------------------------------------------------------------
# PAGE 1: Listing Lookup
# ---------------------------------------------------------------------------
if page == "Listing Lookup":
    st.title("Listing Pricing & Health Check")

    def _pick_random_listing():
        st.session_state["listing_id_input"] = str(listings.sample(1).iloc[0]["listing_id"])

    if "listing_id_input" not in st.session_state:
        st.session_state["listing_id_input"] = ""

    col1, col2 = st.columns([3, 1])
    with col1:
        listing_id_input = st.text_input(
            "Enter a listing ID", key="listing_id_input"
        )
    with col2:
        st.write("")
        st.write("")
        st.button("🎲 Surprise me", on_click=_pick_random_listing)
    if listing_id_input:
        try:
            listing_id = int(listing_id_input.strip())
            match = listings[listings["listing_id"] == listing_id]
        except ValueError:
            match = pd.DataFrame()

        if match.empty:
            st.warning("Listing not found. Try 'Surprise me' for a valid ID.")
        else:
            if len(match) > 1:
                st.error(f"⚠️ {len(match)} rows matched this ID — data integrity issue, showing the first.")
            row = match.iloc[0]
            st.caption(f"Showing listing ID: {row['listing_id']}")

            # --- Overview ---
            st.subheader(f"{row['room_type']} in {row['neighbourhood']}, {row['borough']}")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Base price", f"${row['base_price']:,.0f}/night")
            c2.metric("Health score", f"{row['health_score']:.0f}/100")
            c3.metric("Stay type", row["stay_type"].title())
            c4.metric("Comp position", f"{row['pct_comps_cheaper']:.0f}th percentile")

            if row["price_confidence"] == "low":
                st.info("⚠️ Too few similar listings to give a highly confident "
                        "price estimate for this segment — treat numbers here as "
                        "a rough guide.")

            # --- Price comparison ---
            st.subheader("How your price compares")
            comp_fig = go.Figure()
            comp_fig.add_trace(go.Bar(
                x=["25th percentile", "Median", "Your price", "75th percentile"],
                y=[row["comp_p25"], row["comp_median"], row["base_price"], row["comp_p75"]],
                marker_color=["lightgray", "gray", "steelblue", "lightgray"],
            ))
            comp_fig.update_layout(yaxis_title="Price ($/night)", height=350)
            st.plotly_chart(comp_fig, use_container_width=True)
            st.caption(f"Compared against {row['comp_count']} similar listings "
                       f"(comparison level {row['comp_level']} of 4, where 1 is "
                       f"most specific).")

            # --- Price calendar ---
            st.subheader("90-day suggested price calendar")
            listing_cal = calendar[calendar["listing_id"] == listing_id].sort_values("calendar_date")
            if row["stay_type"] == "monthly stay":
                st.info("This listing is quoted as a monthly stay, so it has one "
                        "flat suggested price rather than a nightly calendar.")
            else:
                cal_fig = px.line(listing_cal, x="calendar_date", y="suggested_price",
                                   title=None)
                cal_fig.add_hline(y=row["base_price"], line_dash="dot",
                                   annotation_text="Base price")
                cal_fig.update_layout(yaxis_title="Suggested price ($)",
                                       xaxis_title="Date", height=350)
                st.plotly_chart(cal_fig, use_container_width=True)

            # --- Diagnosis ---
            st.subheader("Diagnosis")
            st.text(row["diagnosis"])


# ---------------------------------------------------------------------------
# PAGE 2: Market Overview
# ---------------------------------------------------------------------------
else:
    st.title("NYC Short-Term Rental Market Overview")

    st.subheader("Demand baseline: how far ahead guests book")
    curve_fig = px.line(demand_curve, x="days_ahead", y="pct_unavailable_smoothed",
                         color="stay_type",
                         labels={"pct_unavailable_smoothed": "% unavailable",
                                 "days_ahead": "Days ahead"})
    st.plotly_chart(curve_fig, use_container_width=True)
    st.caption("Based on open-calendar, active listings only — see docs/eda_decisions.md.")

    st.subheader("Which nights run hotter than usual (short stays)")
    weekday_fig = px.bar(weekday.sort_values("day_number"), x="day_name", y="avg_excess_pct",
                         labels={"avg_excess_pct": "Excess % unavailable vs. baseline",
                                 "day_name": ""})
    st.plotly_chart(weekday_fig, use_container_width=True)

    st.subheader("How comparable-listing groups are built")
    level_counts = listings["comp_level"].value_counts().sort_index()
    level_fig = px.bar(x=level_counts.index, y=level_counts.values,
                       labels={"x": "Comparison level (1 = most specific)", "y": "Listings"})
    st.plotly_chart(level_fig, use_container_width=True)