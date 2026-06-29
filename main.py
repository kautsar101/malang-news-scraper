import sys
import traceback
from datetime import datetime
from importlib import import_module
from pathlib import Path


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
        "scrape_log_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    )
    log_file = log_path.open("w", encoding="utf-8")

    sys.stdout = TeeStream(sys.__stdout__, log_file)
    sys.stderr = TeeStream(sys.__stderr__, log_file)

    print(f"Scrape log file: {log_path}", flush=True)

    return log_file


LOG_FILE = setup_run_logging()

print("Startup ready. Heavy imports are lazy-loaded per step.", flush=True)


SCRAPERS = [
    {
        "name": "beritamalang_media",
        "module": "scrapers.beritamalang",
    },
    {
        "name": "antara_jatim",
        "module": "scrapers.antarajatim",
    },
    {
        "name": "detik_jatim",
        "module": "scrapers.detikjatim",
    },
    {
        "name": "kominfo_malangkab",
        "module": "scrapers.kominfomalangkab",
    },
    {
        "name": "malangposco",
        "module": "scrapers.malangposco",
    },
    {
        "name": "malangtimes",
        "module": "scrapers.malangtimes",
    },
    {
        "name": "memox",
        "module": "scrapers.memox",
    },
    {
        "name": "nusadaily",
        "module": "scrapers.nusadaily",
    },
    {
        "name": "radar_malang",
        "module": "scrapers.radarmalang",
    },
    {
        "name": "seputar_malang",
        "module": "scrapers.seputarmalang",
    },
    {
        "name": "surya_malang",
        "module": "scrapers.suryamalang",
    },
]


TABLE_NAME = "raw_news_articles_test"
TITLE_LIMIT = 90
FINAL_CSV_DIR = Path("csv/final")


def is_missing(value):
    return value is None or value != value


def short_text(value, limit=TITLE_LIMIT):
    text = "" if is_missing(value) else str(value).strip()

    if len(text) <= limit:
        return text

    return text[:limit - 3] + "..."


def print_row_progress(source, stage, index, total, row):
    print(
        f"{source} {stage} "
        f"[{index + 1}/{total}] "
        f"date={row.get('published_date')} | "
        f"title={short_text(row.get('title'))}",
        flush=True,
    )


def save_supabase_ready_csv(df, source):
    FINAL_CSV_DIR.mkdir(parents=True, exist_ok=True)
    output_path = FINAL_CSV_DIR / f"{source}_supabase_ready.csv"
    df.to_csv(output_path, index=False)
    print(
        f"{source}: saved supabase-ready CSV -> {output_path} ({len(df)} rows)",
        flush=True,
    )
    return output_path


def run_output_validation():
    print("\nRunning CSV output validation...", flush=True)

    try:
        from validate_csv_outputs import main as validate_outputs

        validate_outputs()
    except Exception:
        print("CSV output validation failed.", flush=True)
        traceback.print_exc()


def dataframe(*args, **kwargs):
    print("Importing pandas for DataFrame operation...", flush=True)
    import pandas as pd

    return pd.DataFrame(*args, **kwargs)


def concat_dataframes(*args, **kwargs):
    print("Importing pandas for concat operation...", flush=True)
    import pandas as pd

    return pd.concat(*args, **kwargs)


def process(df, source):

    print(f"{source}: normalizing {len(df)} rows", flush=True)
    print(f"{source}: importing normalize/tagging utils", flush=True)

    from utils.normalize import normalize_news
    from utils.tagging import tag_kecamatan

    df = normalize_news(
        df,
        source
    )

    kecamatan_rows = []

    for index, row in df.iterrows():
        print_row_progress(source, "tagging", index, len(df), row)
        kecamatan_rows.append(tag_kecamatan(row["content"]))

    df[
        [
            "all_kecamatan",
            "primary_kecamatan",
            "latitude",
            "longitude"
        ]
    ] = dataframe(kecamatan_rows, index=df.index)

    print(
        f"{source}: loading sentiment model "
        "(set SENTIMENT_MODE=fast to skip HuggingFace)",
        flush=True,
    )

    from utils.sentiment import predict_sentiment

    sentiment_rows = []

    for index, row in df.iterrows():
        print_row_progress(source, "sentiment", index, len(df), row)
        sentiment_rows.append(
            predict_sentiment(
                row["title"],
                row["content"]
            )
        )

    df[
        [
            "sentiment",
            "sentiment_score"
        ]
    ] = dataframe(sentiment_rows, index=df.index)

    return df


def main():
    started_at = datetime.now()
    uploaded_total = 0
    final_frames = []

    print(f"Pipeline started at: {started_at.isoformat()}", flush=True)
    print(f"Upload target table: {TABLE_NAME}", flush=True)

    for item in SCRAPERS:

        source = item["name"]

        print(f"\nRunning {source}...", flush=True)

        try:
            print(f"{source}: importing scraper module {item['module']}", flush=True)
            scraper = import_module(item["module"]).scrape

            df = scraper()

            if df.empty:

                print("No data found.", flush=True)
                continue

            print(f"{source}: scraped {len(df)} rows", flush=True)

            for index, row in df.iterrows():
                print_row_progress(source, "scraped", index, len(df), row)

            df = process(
                df,
                source
            )

            df = df[
                df["content"]
                .fillna("")
                .astype(str)
                .str.strip()
                .ne("")
            ]

            if df.empty:

                print("No valid article content found.", flush=True)
                continue

            save_supabase_ready_csv(df, source)
            final_frames.append(df.copy())

            print(f"{source}: uploading {len(df)} valid rows", flush=True)
            print(f"{source}: importing Supabase uploader", flush=True)

            from utils.supabase_loader import upload_news

            for index, row in df.iterrows():
                print_row_progress(source, "upload", index, len(df), row)

            upload_news(
                df,
                TABLE_NAME
            )

            uploaded_total += len(df)

            print(
                f"{source}: uploaded {len(df)} articles",
                flush=True,
            )

        except Exception as error:

            print(
                f"{source} failed: {error}",
                flush=True,
            )
            traceback.print_exc()

    finished_at = datetime.now()

    if final_frames:
        combined_df = concat_dataframes(final_frames)
        combined_path = FINAL_CSV_DIR / "all_sources_supabase_ready.csv"
        combined_df.to_csv(combined_path, index=False)
        print(
            f"Pipeline saved combined supabase-ready CSV -> "
            f"{combined_path} ({len(combined_df)} rows)",
            flush=True,
        )

    run_output_validation()

    print(f"Pipeline finished at: {finished_at.isoformat()}", flush=True)
    print(f"Pipeline duration: {finished_at - started_at}", flush=True)
    print(f"Pipeline uploaded total: {uploaded_total}", flush=True)


if __name__ == "__main__":

    try:
        main()
    finally:
        LOG_FILE.close()
