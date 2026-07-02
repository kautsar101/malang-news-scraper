import argparse
import inspect
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

LOG_FILE = None


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
        "name": "malang_voice",
        "module": "scrapers.malangvoice",
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
    {
        "name": "times_indonesia",
        "module": "scrapers.timesindonesia",
    },
]


TABLE_NAME = "raw_news_articles"
TITLE_LIMIT = 90
FINAL_CSV_DIR = Path("csv/final")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run news scraping pipeline."
    )
    parser.add_argument(
        "--source",
        action="append",
        choices=[item["name"] for item in SCRAPERS],
        help=(
            "Run only selected source. "
            "Can be repeated. Default: run all sources."
        ),
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Save CSV outputs only; do not upload to Supabase.",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip final CSV output validation.",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help=(
            "Daily/update mode: scrape only early pages/clicks and skip "
            "existing URLs before tagging/upload."
        ),
    )
    parser.add_argument(
        "--incremental-pages",
        type=int,
        default=3,
        help="Max pages per source when --incremental is enabled.",
    )
    parser.add_argument(
        "--incremental-clicks",
        type=int,
        default=8,
        help="Max load-more clicks for click-based sources in --incremental mode.",
    )

    return parser.parse_args()


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


def normalized_url(value):
    if value is None or value != value:
        return None

    text = str(value).strip()
    return text or None


def filter_existing_urls(df, existing_urls, source):
    if "url" not in df.columns:
        print(f"{source}: URL column missing; cannot pre-filter duplicates", flush=True)
        return df

    existing_urls = {
        normalized_url(url)
        for url in existing_urls
        if normalized_url(url)
    }
    before = len(df)
    df = df.copy()
    df["_normalized_url"] = df["url"].apply(normalized_url)

    missing_url = df["_normalized_url"].isna().sum()
    duplicate_input = df["_normalized_url"].duplicated(keep="first").sum()
    existing_mask = df["_normalized_url"].isin(existing_urls)

    df = df[
        df["_normalized_url"].notna()
        & ~df["_normalized_url"].duplicated(keep="first")
        & ~existing_mask
    ].drop(columns=["_normalized_url"])

    print(
        f"{source}: pre-upload URL filter: incoming={before}, "
        f"existing_skipped={int(existing_mask.sum())}, "
        f"duplicate_input_skipped={int(duplicate_input)}, "
        f"missing_url_skipped={int(missing_url)}, new={len(df)}",
        flush=True,
    )

    return df


def run_scraper(scraper, args):
    if not args.incremental:
        return scraper()

    signature = inspect.signature(scraper)
    kwargs = {}

    if "max_pages" in signature.parameters:
        kwargs["max_pages"] = args.incremental_pages

    if "max_clicks" in signature.parameters:
        kwargs["max_clicks"] = args.incremental_clicks

    print(
        f"Incremental scraper args: {kwargs if kwargs else 'default'}",
        flush=True,
    )

    return scraper(**kwargs)


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
        f"{source}: Sentiment skipped in main pipeline; marked as pending",
        flush=True,
    )

    df["sentiment"] = "pending"
    df["sentiment_score"] = None

    return df


def main():
    global LOG_FILE

    args = parse_args()

    LOG_FILE = setup_run_logging()
    print("Startup ready. Heavy imports are lazy-loaded per step.", flush=True)

    started_at = datetime.now()
    uploaded_total = 0
    final_frames = []
    selected_sources = set(args.source or [])

    print(f"Pipeline started at: {started_at.isoformat()}", flush=True)
    print(f"Upload target table: {TABLE_NAME}", flush=True)
    print(f"Selected sources: {sorted(selected_sources) if selected_sources else 'ALL'}", flush=True)
    print(f"Upload enabled: {not args.no_upload}", flush=True)
    print(f"Incremental mode: {args.incremental}", flush=True)
    if args.incremental:
        print(
            f"Incremental limits: pages={args.incremental_pages}, "
            f"clicks={args.incremental_clicks}",
            flush=True,
        )

    for item in SCRAPERS:

        source = item["name"]

        if selected_sources and source not in selected_sources:
            continue

        print(f"\nRunning {source}...", flush=True)

        try:
            print(f"{source}: importing scraper module {item['module']}", flush=True)
            scraper = import_module(item["module"]).scrape

            df = run_scraper(scraper, args)

            if df.empty:

                print("No data found.", flush=True)
                continue

            print(f"{source}: scraped {len(df)} rows", flush=True)

            for index, row in df.iterrows():
                print_row_progress(source, "scraped", index, len(df), row)

            existing_urls = None

            if not args.no_upload:
                print(f"{source}: loading existing URLs before tagging", flush=True)

                from utils.supabase_loader import get_existing_urls

                existing_urls = get_existing_urls(TABLE_NAME)
                df = filter_existing_urls(df, existing_urls, source)

                if df.empty:
                    print(
                        f"{source}: no new URLs after pre-filter; "
                        "skip tagging/upload",
                        flush=True,
                    )
                    continue

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

            if args.no_upload:
                print(f"{source}: upload skipped because --no-upload was set", flush=True)
                continue

            print(f"{source}: uploading {len(df)} valid rows", flush=True)
            print(f"{source}: importing Supabase uploader", flush=True)

            from utils.supabase_loader import upload_news

            for index, row in df.iterrows():
                print_row_progress(source, "upload", index, len(df), row)

            uploaded_count = upload_news(
                df,
                TABLE_NAME,
                existing_urls=existing_urls,
            )

            uploaded_total += uploaded_count

            print(
                f"{source}: uploaded {uploaded_count} new articles "
                f"({len(df) - uploaded_count} skipped duplicates)",
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

    if args.skip_validation:
        print("CSV output validation skipped.", flush=True)
    else:
        run_output_validation()

    print(f"Pipeline finished at: {finished_at.isoformat()}", flush=True)
    print(f"Pipeline duration: {finished_at - started_at}", flush=True)
    print(f"Pipeline uploaded total: {uploaded_total}", flush=True)


if __name__ == "__main__":

    try:
        main()
    finally:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        if LOG_FILE:
            LOG_FILE.close()
