"""
Milestone 5 (part 3) - LightGBM
Trains a LightGBM model to predict log(base_price), using the same
train/test split saved in Step 5.1. A validation slice is carved out
of the training set only, to decide when to stop adding trees.

Output:
- data/gold/nyc/model_lgbm_predictions.parquet
- models/lgbm_model.joblib
"""
from pathlib import Path
import duckdb
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import GroupShuffleSplit
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


def as_lgbm_frame(df: pd.DataFrame) -> pd.DataFrame:
    """LightGBM wants categorical columns marked with dtype 'category'."""
    frame = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES].copy()
    for col in CATEGORICAL_FEATURES:
        frame[col] = frame[col].astype("category")
    return frame


def train_and_predict():
    train, test = load_split()

    # Carve a validation slice out of TRAINING data only, split by host
    # (same reason as the original train/test split: avoid a host's
    # listings appearing on both sides)
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=42)
    fit_idx, valid_idx = next(splitter.split(train, groups=train["host_id"]))
    fit_set = train.iloc[fit_idx].reset_index(drop=True)
    valid_set = train.iloc[valid_idx].reset_index(drop=True)

    model = lgb.LGBMRegressor(
        n_estimators=2000,       # an upper limit; early stopping will cut this short
        learning_rate=0.03,
        num_leaves=31,
        min_child_samples=20,    # avoids trees splitting on very small groups
        random_state=42,
        verbose=-1,
    )

    model.fit(
        as_lgbm_frame(fit_set), fit_set[TARGET],
        eval_set=[(as_lgbm_frame(valid_set), valid_set[TARGET])],
        callbacks=[lgb.early_stopping(stopping_rounds=50, verbose=False)],
    )

    print(f"Stopped after {model.best_iteration_} trees "
          f"(limit was {model.n_estimators})")

    # Predict on both sets: test tells us real performance,
    # train tells us whether the model is overfitting
    for name, subset in [("train", train), ("test", test)]:
        log_pred = model.predict(as_lgbm_frame(subset))
        subset["predicted_base_price"] = 10 ** log_pred

    MODEL_DIR.mkdir(exist_ok=True)
    joblib.dump(model, MODEL_DIR / "lgbm_model.joblib")

    predictions = pd.concat([
        train[["listing_id", "split", "base_price", "predicted_base_price"]],
        test[["listing_id", "split", "base_price", "predicted_base_price"]],
    ])
    predictions.to_parquet(GOLD_DIR / "model_lgbm_predictions.parquet", index=False)

    print(f"Fit rows: {len(fit_set):,}   Valid rows: {len(valid_set):,}   Test rows: {len(test):,}")
    return model, train, test


if __name__ == "__main__":
    train_and_predict()