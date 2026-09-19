"""
Milestone 5 (part 2) - Linear regression
Trains a linear regression model to predict log(base_price),
using the same train/test split saved in Step 5.1.

Output:
- data/gold/nyc/model_linear_predictions.parquet
- models/linear_model.joblib
"""
from pathlib import Path
import duckdb
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
import joblib

GOLD_DIR = Path("data/gold/nyc")
MODEL_DIR = Path("models")

NUMERIC_FEATURES = [
    "accommodates", "bedrooms", "beds", "bathrooms",
    "amenities_count", "minimum_nights", "rating_overall",
    "number_of_reviews", "reviews_per_month",
    "host_listings_count", "host_years",
    "latitude", "longitude",
]
CATEGORICAL_FEATURES = [
    "room_type", "stay_type", "license_status",
    "borough", "host_is_superhost", "shared_bath",
]
TARGET = "log_base_price"


def build_pipeline() -> Pipeline:
    """Defines how raw features become model-ready numbers."""

    # Numeric columns: fill empty values with the median,
    # and add a column marking which values were empty
    numeric_steps = SimpleImputer(strategy="median", add_indicator=True)

    # Categorical columns: turn each category into its own 0/1 column.
    # handle_unknown="ignore" means a category never seen in training
    # (for example, in a future city) becomes all zeros instead of crashing.
    categorical_steps = OneHotEncoder(handle_unknown="ignore")

    # ColumnTransformer applies the right steps to the right columns
    preprocessing = ColumnTransformer([
        ("numeric", numeric_steps, NUMERIC_FEATURES),
        ("categorical", categorical_steps, CATEGORICAL_FEATURES),
    ])

    # Chain preprocessing and the model together as one object
    return Pipeline([
        ("preprocessing", preprocessing),
        ("model", LinearRegression()),
    ])


def load_split():
    """Loads the model table and re-applies the saved train/test split."""
    data = duckdb.sql(f"""
        SELECT m.*, s.split
        FROM read_parquet('{(GOLD_DIR / "model_table.parquet").as_posix()}') m
        JOIN read_parquet('{(GOLD_DIR / "split.parquet").as_posix()}') s
          ON m.listing_id = s.listing_id
    """).df()

    train = data[data["split"] == "train"].reset_index(drop=True)
    test = data[data["split"] == "test"].reset_index(drop=True)
    return train, test


def train_and_predict():
    train, test = load_split()

    pipeline = build_pipeline()
    pipeline.fit(train[NUMERIC_FEATURES + CATEGORICAL_FEATURES], train[TARGET])

    # Predict on both sets: test tells us real performance,
    # train tells us whether the model is overfitting
    for name, subset in [("train", train), ("test", test)]:
        log_pred = pipeline.predict(subset[NUMERIC_FEATURES + CATEGORICAL_FEATURES])
        subset["predicted_base_price"] = 10 ** log_pred   # undo log10

    MODEL_DIR.mkdir(exist_ok=True)
    joblib.dump(pipeline, MODEL_DIR / "linear_model.joblib")

    predictions = pd.concat([
        train[["listing_id", "split", "base_price", "predicted_base_price"]],
        test[["listing_id", "split", "base_price", "predicted_base_price"]],
    ])
    predictions.to_parquet(GOLD_DIR / "model_linear_predictions.parquet", index=False)

    print(f"Train rows: {len(train):,}   Test rows: {len(test):,}")
    return pipeline, train, test


if __name__ == "__main__":
    train_and_predict()