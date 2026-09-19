"""
Milestone 1 - Ingest
Converts raw Inside Airbnb CSV files into Parquet files.
All columns are kept as text; cleaning happens in Milestone 2.

Data source: Inside Airbnb - New York City, snapshot dated 14 June 2026
"""
from pathlib import Path
import duckdb

# Folder paths (relative to the rateright/ project folder)
RAW_DIR = Path("data/raw")          # where the downloaded CSV files are
BRONZE_DIR = Path("data/bronze")    # where the Parquet copies will be saved
DATASETS = ["listings", "calendar", "reviews"]


def convert_to_parquet(city: str, dataset: str) -> int:
    """Convert one CSV file to Parquet and return its row count."""

    # 1. Build the input and output file paths
    source_path = RAW_DIR / city / f"{dataset}.csv"
    target_path = BRONZE_DIR / city / f"{dataset}.parquet"

    # 2. Stop early with a clear message if the input file is missing
    if not source_path.exists():
        raise FileNotFoundError(f"File not found: {source_path}")

    # 3. Create the output folder if it does not exist yet
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # 4. Convert paths to forward-slash text so they are safe inside SQL
    source = source_path.as_posix()
    target = target_path.as_posix()

    # 5. Open a temporary in-memory DuckDB database (nothing is saved)
    con = duckdb.connect()

    # 6. Read the CSV with every column as text, then write it as Parquet
    con.execute(f"""
        COPY (
            SELECT *
            FROM read_csv('{source}', header = true, all_varchar = true)
        ) TO '{target}' (FORMAT parquet)
    """)

    # 7. Count rows in the new Parquet file to check nothing was lost
    rows = con.execute(
        f"SELECT COUNT(*) FROM read_parquet('{target}')"
    ).fetchone()[0]

    con.close()
    return rows


if __name__ == "__main__":
    city = "nyc"

    for dataset in DATASETS:
        rows = convert_to_parquet(city, dataset)

        # File size in megabytes (1 MB = 1,000,000 bytes)
        size_mb = (BRONZE_DIR / city / f"{dataset}.parquet").stat().st_size / 1e6

        # :<10 pads the name to 10 characters, :>12, right-aligns with commas
        print(f"{dataset:<10} rows = {rows:>12,}   parquet size = {size_mb:,.1f} MB")