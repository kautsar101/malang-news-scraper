import argparse
import sys
from datetime import datetime
from pathlib import Path


TABLE_NAME = "raw_news_articles_test"
DEFAULT_INPUT_CSV = "csv/final/all_sources_supabase_ready.csv"
DEFAULT_OUTPUT_DIR = Path("csv/final")
TITLE_LIMIT = 90


class TeeStream:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, value):
        for stream in self.streams:
            stream.write(value)
            stream.flush()

    def flush(self):
        for stream in self.streams:
            stream.flush()


def setup_run_logging():
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    log_path = log_dir / (
        "sentiment_backfill_log_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    )
    log_file = log_path.open("w", encoding="utf-8")

    sys.stdout = TeeStream(sys.__stdout__, log_file)
    sys.stderr = TeeStream(sys.__stderr__, log_file)

    print(f"Sentiment backfill log file: {log_path}", flush=True)

    return log_file


def parse_args():
    parser = argparse.ArgumentParser(
        description="Backfill sentiment for scraped news rows."
    )
    parser.add_argument(
        "--csv",
        default=DEFAULT_INPUT_CSV,
        help=f"Input CSV path. Default: {DEFAULT_INPUT_CSV}",
    )
    parser.add_argument(
        "--from-supabase",
        action="store_true",
        help="Read rows from Supabase instead of --csv.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output CSV path. Default: csv/final/sentiment_backfill_<timestamp>.csv",
    )
    parser.add_argument(
        "--table",
        default=TABLE_NAME,
        help=f"Supabase table name. Default: {TABLE_NAME}",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Only save output CSV, do not update Supabase.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max rows to process for testing.",
    )
    parser.add_argument(
        "--only-pending",
        action="store_true",
        help="Process only rows where sentiment is blank or pending.",
    )
    return parser.parse_args()


def short_text(value, limit=TITLE_LIMIT):
    text = "" if value is None or value != value else str(value).strip()

    if len(text) <= limit:
        return text

    return text[:limit - 3] + "..."


def default_output_path():
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_OUTPUT_DIR / (
        "sentiment_backfill_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )


def load_input_rows(csv_path, only_pending, limit):
    print("Importing pandas for sentiment backfill CSV read...", flush=True)
    import pandas as pd

    df = pd.read_csv(csv_path)
    print(f"Loaded input CSV: {csv_path} ({len(df)} rows)", flush=True)

    required_columns = ["url", "title", "content"]
    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise RuntimeError(
            "Input CSV missing required column(s): "
            + ", ".join(missing_columns)
        )

    if only_pending and "sentiment" in df.columns:
        sentiment_values = df["sentiment"].fillna("").astype(str).str.strip().str.lower()
        df = df[
            sentiment_values.eq("")
            | sentiment_values.eq("pending")
        ].reset_index(drop=True)
        print(f"Filtered pending rows: {len(df)}", flush=True)

    if limit is not None:
        df = df.head(limit).reset_index(drop=True)
        print(f"Limited rows: {len(df)}", flush=True)

    return df


def load_supabase_rows(table_name, only_pending, limit):
    print("Fetching sentiment rows from Supabase...", flush=True)
    from utils.supabase_loader import fetch_news

    records = fetch_news(
        table_name,
        only_pending=only_pending,
        limit=limit,
    )

    print("Importing pandas for Supabase rows...", flush=True)
    import pandas as pd

    df = pd.DataFrame(records)
    print(f"Loaded Supabase rows: {len(df)}", flush=True)

    return df


def predict_rows(df):
    print("Loading sentiment model", flush=True)
    from utils.sentiment import predict_sentiment

    print("Sentiment model import ready", flush=True)

    sentiment_rows = []

    for index, row in df.iterrows():
        print(
            f"sentiment [{index + 1}/{len(df)}] "
            f"date={row.get('published_date')} | "
            f"title={short_text(row.get('title'))}",
            flush=True,
        )
        sentiment_rows.append(
            predict_sentiment(
                row.get("title"),
                row.get("content"),
            )
        )

    print("Sentiment prediction complete", flush=True)
    return sentiment_rows


def attach_sentiment(df, sentiment_rows):
    print("Importing pandas for sentiment result attach...", flush=True)
    import pandas as pd

    df = df.copy()
    df[
        [
            "sentiment",
            "sentiment_score",
        ]
    ] = pd.DataFrame(sentiment_rows, index=df.index)

    return df


def save_output(df, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Saved sentiment backfill CSV -> {output_path} ({len(df)} rows)", flush=True)
    return output_path


def upload_backfill(df, table_name):
    from utils.supabase_loader import update_news

    update_df = df[
        [
            "url",
            "sentiment",
            "sentiment_score",
        ]
    ].copy()

    pending_count = int(
        update_df["sentiment"]
        .fillna("")
        .astype(str)
        .str.lower()
        .eq("pending")
        .sum()
    )

    if pending_count:
        raise RuntimeError(
            f"Backfill still has {pending_count} pending sentiment rows; upload aborted."
        )

    update_news(update_df, table_name, match_column="url")


def main():
    args = parse_args()
    csv_path = Path(args.csv)

    if not args.from_supabase and not csv_path.exists():
        raise RuntimeError(f"Input CSV not found: {csv_path}")

    output_path = Path(args.output) if args.output else default_output_path()
    if args.from_supabase:
        df = load_supabase_rows(args.table, args.only_pending, args.limit)
    else:
        df = load_input_rows(csv_path, args.only_pending, args.limit)

    if df.empty:
        print("No rows to process.", flush=True)
        save_output(df, output_path)
        return

    sentiment_rows = predict_rows(df)
    result_df = attach_sentiment(df, sentiment_rows)
    save_output(result_df, output_path)

    if args.no_upload:
        print("Supabase update skipped because --no-upload was set.", flush=True)
        return

    upload_backfill(result_df, args.table)


if __name__ == "__main__":
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        main()
        raise SystemExit

    log_file = setup_run_logging()

    try:
        main()
    finally:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        log_file.close()
