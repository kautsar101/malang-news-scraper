import asyncio
import csv
import importlib
import re
import sys
from pathlib import Path


SAMPLE_SIZE = 5

SOURCES = {
    "beritamalang": {
        "module": "scrapers.beritamalang",
        "list_csv": "csv/beritamalang_list_debug.csv",
        "article_csv": "csv/beritamalang_article_debug.csv",
        "mode": "extract_content",
    },
    "kominfo_malangkab": {
        "module": "scrapers.kominfomalangkab",
        "list_csv": "csv/kominfomalangkab_list_debug.csv",
        "article_csv": "csv/kominfo_malangkab_article_debug.csv",
        "mode": "extract_article",
        "max_failures": 1,
    },
    "malangposco": {
        "module": "scrapers.malangposco",
        "list_csv": "csv/malangposco_list_debug.csv",
        "article_csv": "csv/malangposco_article_debug.csv",
        "mode": "extract_article",
    },
    "malangtimes": {
        "module": "scrapers.malangtimes",
        "list_csv": "csv/malangtimes_list_debug.csv",
        "article_csv": "csv/malangtimes_article_debug.csv",
        "mode": "malangtimes_async",
    },
    "nusadaily": {
        "module": "scrapers.nusadaily",
        "list_csv": "csv/nusadaily_list_debug.csv",
        "article_csv": "csv/nusadaily_article_debug.csv",
        "mode": "extract_article",
    },
    "radar_malang": {
        "module": "scrapers.radarmalang",
        "list_csv": "csv/radarmalang_list_debug.csv",
        "article_csv": "csv/radar_malang_article_debug.csv",
        "mode": "extract_article",
    },
    "seputar_malang": {
        "module": "scrapers.seputarmalang",
        "list_csv": "csv/seputarmalang_list_debug.csv",
        "article_csv": "csv/seputar_malang_article_debug.csv",
        "mode": "extract_article",
    },
    "antara_jatim": {
        "module": "scrapers.antarajatim",
        "list_csv": "csv/antara_jatim_list_debug.csv",
        "article_csv": "csv/antara_jatim_article_debug.csv",
        "mode": "extract_article",
    },
    "detik_jatim": {
        "module": "scrapers.detikjatim",
        "list_csv": "csv/detik_jatim_list_debug.csv",
        "article_csv": "csv/detik_jatim_article_debug.csv",
        "mode": "extract_article",
    },
    "memox": {
        "module": "scrapers.memox",
        "list_csv": "csv/memox_list_debug.csv",
        "article_csv": "csv/memox_article_debug.csv",
        "mode": "extract_article",
    },
    "surya_malang": {
        "module": "scrapers.suryamalang",
        "list_csv": "csv/surya_malang_list_debug.csv",
        "article_csv": "csv/surya_malang_article_debug.csv",
        "mode": "extract_article",
    },
}


def read_csv(path):
    csv_path = Path(path)

    if not csv_path.exists():
        return []

    with csv_path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def write_csv(path, rows):
    csv_path = Path(path)
    csv_path.parent.mkdir(exist_ok=True)

    fieldnames = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def sample_rows(rows):
    valid_rows = [
        row
        for row in rows
        if str(row.get("url") or "").strip()
    ]

    return valid_rows


def short_text(value, limit=90):
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def content_metrics(content):
    text = str(content or "")
    return {
        "content_len": len(text),
        "has_literal_backslash_n": "\\n" in text,
        "has_actual_double_blank_line": bool(re.search(r"\n\s*\n", text)),
        "has_carriage_return": "\r" in text,
        "has_literal_backslash_r": "\\r" in text,
        "has_replacement_char": "�" in text,
    }


def normalize_row_url(module, row):
    normalized = dict(row)

    if hasattr(module, "normalize_url"):
        normalized["url"] = module.normalize_url(normalized.get("url"))

    return normalized


def extract_sync(source, config, module, rows):
    articles = []
    consecutive_failures = 0

    for index, row in enumerate(sample_rows(rows), 1):
        if len(articles) >= SAMPLE_SIZE:
            break

        row = normalize_row_url(module, row)

        try:
            if config["mode"] == "extract_content":
                content = module.extract_content(row["url"])
                article = {
                    "title": row.get("title"),
                    "published_date": row.get("published_date"),
                    "content": content,
                    "url": row.get("url"),
                    "source": getattr(module, "SOURCE", source),
                }
            else:
                article = module.extract_article(row)

            article.update(content_metrics(article.get("content")))

            if not article.get("content"):
                print(
                    f"{source} sample empty content [{index}], skip: "
                    f"{row.get('url')}",
                    flush=True,
                )
                continue

            articles.append(article)
            consecutive_failures = 0
            print(
                f"{source} article sample [{len(articles)}] "
                f"content_len={article['content_len']} | "
                f"title={short_text(article.get('title'))}",
                flush=True,
            )
        except Exception as error:
            print(
                f"{source} sample failed [{index}]: "
                f"{row.get('url')} | {error}",
                flush=True,
            )
            consecutive_failures += 1

            if consecutive_failures >= config.get("max_failures", 3):
                print(
                    f"{source}: stop sample extraction after "
                    f"{consecutive_failures} consecutive failures",
                    flush=True,
                )
                break

    return articles


async def extract_malangtimes(source, config, module, rows):
    from playwright.async_api import async_playwright

    articles = []
    consecutive_failures = 0

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            for index, row in enumerate(sample_rows(rows), 1):
                if len(articles) >= SAMPLE_SIZE:
                    break

                row = normalize_row_url(module, row)

                try:
                    article = await module.extract_article(page, row)
                    article.update(content_metrics(article.get("content")))

                    if not article.get("content"):
                        print(
                            f"{source} sample empty content [{index}], skip: "
                            f"{row.get('url')}",
                            flush=True,
                        )
                        continue

                    articles.append(article)
                    consecutive_failures = 0
                    print(
                        f"{source} article sample [{len(articles)}] "
                        f"content_len={article['content_len']} | "
                        f"title={short_text(article.get('title'))}",
                        flush=True,
                    )
                except Exception as error:
                    print(
                        f"{source} sample failed [{index}]: "
                        f"{row.get('url')} | {error}",
                        flush=True,
                    )
                    consecutive_failures += 1

                    if consecutive_failures >= config.get("max_failures", 3):
                        print(
                            f"{source}: stop sample extraction after "
                            f"{consecutive_failures} consecutive failures",
                            flush=True,
                        )
                        break
        finally:
            await browser.close()

    return articles


async def run_source(source, config):
    rows = read_csv(config["list_csv"])

    if not rows:
        print(f"{source}: list debug CSV not found/empty, skip: {config['list_csv']}", flush=True)
        return []

    module = importlib.import_module(config["module"])

    if config["mode"] == "malangtimes_async":
        articles = await extract_malangtimes(source, config, module, rows)
    else:
        articles = extract_sync(source, config, module, rows)

    write_csv(config["article_csv"], articles)
    print(f"{source}: saved {len(articles)} rows -> {config['article_csv']}", flush=True)
    return articles


async def main():
    selected_sources = sys.argv[1:] or list(SOURCES)
    unknown_sources = [source for source in selected_sources if source not in SOURCES]

    if unknown_sources:
        raise SystemExit(f"Unknown source(s): {', '.join(unknown_sources)}")

    for source in selected_sources:
        config = SOURCES[source]
        print(f"\nRunning article debug samples: {source}", flush=True)
        await run_source(source, config)


if __name__ == "__main__":
    asyncio.run(main())
