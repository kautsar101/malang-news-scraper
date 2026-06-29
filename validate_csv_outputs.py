import csv
from pathlib import Path
from datetime import datetime


SOURCES = {
    "antara_jatim": {
        "debug": "csv/antara_jatim_list_debug.csv",
        "articles": "csv/antara_jatim_articles.csv",
        "final": "csv/final/antara_jatim_supabase_ready.csv",
        "expected_url_contains": "jatim.antaranews.com",
    },
    "detik_jatim": {
        "debug": "csv/detik_jatim_list_debug.csv",
        "articles": "csv/detik_jatim_articles.csv",
        "final": "csv/final/detik_jatim_supabase_ready.csv",
        "expected_url_contains": "detik.com",
    },
    "memox": {
        "debug": "csv/memox_list_debug.csv",
        "articles": "csv/memox_articles.csv",
        "final": "csv/final/memox_supabase_ready.csv",
        "expected_url_contains": "memox.co.id",
    },
    "surya_malang": {
        "debug": "csv/surya_malang_list_debug.csv",
        "articles": "csv/surya_malang_articles.csv",
        "final": "csv/final/surya_malang_supabase_ready.csv",
        "expected_url_contains": "surabaya.tribunnews.com",
    },
    "beritamalang_media": {
        "debug": "csv/beritamalang_list_debug.csv",
        "articles": "csv/beritamalang_media_articles.csv",
        "final": "csv/final/beritamalang_media_supabase_ready.csv",
    },
    "kominfo_malangkab": {
        "debug": "csv/kominfomalangkab_list_debug.csv",
        "articles": "csv/kominfo_malangkab_articles.csv",
        "final": "csv/final/kominfo_malangkab_supabase_ready.csv",
    },
    "malangposco": {
        "debug": "csv/malangposco_list_debug.csv",
        "articles": "csv/malangposco_articles.csv",
        "final": "csv/final/malangposco_supabase_ready.csv",
    },
    "malangtimes": {
        "debug": "csv/malangtimes_list_debug.csv",
        "articles": "csv/malangtimes_articles.csv",
        "final": "csv/final/malangtimes_supabase_ready.csv",
    },
    "nusadaily": {
        "debug": "csv/nusadaily_list_debug.csv",
        "articles": "csv/nusadaily_articles.csv",
        "final": "csv/final/nusadaily_supabase_ready.csv",
    },
    "radar_malang": {
        "debug": "csv/radarmalang_list_debug.csv",
        "articles": "csv/radar_malang_articles.csv",
        "final": "csv/final/radar_malang_supabase_ready.csv",
        "expected_url_contains": "/kabupaten-malang/",
    },
    "seputar_malang": {
        "debug": "csv/seputarmalang_list_debug.csv",
        "articles": "csv/seputar_malang_articles.csv",
        "final": "csv/final/seputar_malang_supabase_ready.csv",
    },
}


REQUIRED_FINAL_COLUMNS = {
    "source",
    "title",
    "url",
    "published_date",
    "scraped_at",
    "author",
    "category",
    "content",
    "text",
    "all_kecamatan",
    "primary_kecamatan",
    "latitude",
    "longitude",
    "sentiment",
    "sentiment_score",
}


def read_csv(path):
    csv_path = Path(path)

    if not csv_path.exists():
        return None, []

    with csv_path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        return reader.fieldnames or [], list(reader)


def file_mtime(path):
    csv_path = Path(path)

    if not csv_path.exists():
        return None

    return datetime.fromtimestamp(csv_path.stat().st_mtime)


def norm_url(value):
    return (value or "").strip().rstrip("/")


def count_nonempty(rows, column):
    return sum(
        1
        for row in rows
        if str(row.get(column) or "").strip()
    )


def min_max(rows, column):
    values = sorted(
        str(row.get(column) or "").strip()
        for row in rows
        if str(row.get(column) or "").strip()
    )

    if not values:
        return None, None

    return values[0], values[-1]


def count_unexpected_urls(rows, expected_part):
    if not expected_part:
        return 0

    return sum(
        1
        for row in rows
        if expected_part not in norm_url(row.get("url"))
    )


def summarize_source(source, paths):
    debug_cols, debug_rows = read_csv(paths["debug"])
    article_cols, article_rows = read_csv(paths["articles"])
    final_cols, final_rows = read_csv(paths["final"])

    debug_urls = {
        norm_url(row.get("url"))
        for row in debug_rows
        if norm_url(row.get("url"))
    }
    article_urls = {
        norm_url(row.get("url"))
        for row in article_rows
        if norm_url(row.get("url"))
    }
    final_urls = {
        norm_url(row.get("url"))
        for row in final_rows
        if norm_url(row.get("url"))
    }

    missing_final_columns = (
        sorted(REQUIRED_FINAL_COLUMNS - set(final_cols or []))
        if final_cols is not None
        else sorted(REQUIRED_FINAL_COLUMNS)
    )

    print(f"\n== {source} ==")
    print(f"debug file: {paths['debug']} | exists={debug_cols is not None} | mtime={file_mtime(paths['debug'])} | rows={len(debug_rows)} | unique_url={len(debug_urls)}")
    print(f"articles file: {paths['articles']} | exists={article_cols is not None} | mtime={file_mtime(paths['articles'])} | rows={len(article_rows)} | unique_url={len(article_urls)}")
    print(f"final file: {paths['final']} | exists={final_cols is not None} | mtime={file_mtime(paths['final'])} | rows={len(final_rows)} | unique_url={len(final_urls)}")
    print(f"debug -> articles overlap: {len(debug_urls & article_urls)}")
    print(f"debug missing in articles: {len(debug_urls - article_urls)}")
    print(f"articles extra vs debug: {len(article_urls - debug_urls)}")
    print(f"articles -> final overlap: {len(article_urls & final_urls)}")
    print(f"final missing required columns: {missing_final_columns}")

    debug_min, debug_max = min_max(debug_rows, "published_date")
    article_min, article_max = min_max(article_rows, "published_date")
    final_min, final_max = min_max(final_rows, "published_date")
    print(f"debug date range: {debug_min} -> {debug_max}")
    print(f"articles date range: {article_min} -> {article_max}")
    print(f"final date range: {final_min} -> {final_max}")

    expected_part = paths.get("expected_url_contains")
    if expected_part:
        print(f"expected URL contains: {expected_part}")
        print(f"debug unexpected URLs: {count_unexpected_urls(debug_rows, expected_part)}/{len(debug_rows)}")
        print(f"articles unexpected URLs: {count_unexpected_urls(article_rows, expected_part)}/{len(article_rows)}")
        print(f"final unexpected URLs: {count_unexpected_urls(final_rows, expected_part)}/{len(final_rows)}")

    if article_rows:
        print(f"articles nonempty content: {count_nonempty(article_rows, 'content')}/{len(article_rows)}")
        print(f"articles non-null category values: {count_nonempty(article_rows, 'category')}/{len(article_rows)}")

    if final_rows:
        print(f"final nonempty content: {count_nonempty(final_rows, 'content')}/{len(final_rows)}")
        print(f"final nonempty text: {count_nonempty(final_rows, 'text')}/{len(final_rows)}")
        print(f"final nonempty scraped_at: {count_nonempty(final_rows, 'scraped_at')}/{len(final_rows)}")
        print(f"final nonempty sentiment: {count_nonempty(final_rows, 'sentiment')}/{len(final_rows)}")
        print(f"final non-null category values: {count_nonempty(final_rows, 'category')}/{len(final_rows)}")

    missing_examples = [
        row
        for row in debug_rows
        if norm_url(row.get("url")) in debug_urls - article_urls
    ][:5]

    if missing_examples:
        print("missing examples:")
        for row in missing_examples:
            print(
                " - "
                f"{row.get('published_date')} | "
                f"{str(row.get('title') or '')[:90]} | "
                f"{row.get('url')}"
            )


def main():
    for source, paths in SOURCES.items():
        summarize_source(source, paths)


if __name__ == "__main__":
    main()
