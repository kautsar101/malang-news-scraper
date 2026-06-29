from scrapers.common import (
    cutoff_date,
    clean_article_soup,
    clean_article_text,
    fetch_html,
    is_older_than_cutoff,
    normalize_date,
    records_to_df,
    scraped_at,
    write_articles_csv,
)
import random
import time


BASE_URL = "https://beritamalang.media/category/berita"
SOURCE = "beritamalang_media"
OUTPUT_PATH = "csv/beritamalang_media_articles.csv"
FETCH_RETRIES = 2
MAX_CONSECUTIVE_FETCH_ERRORS = 3
BASE_RETRY_DELAY_SECONDS = 1
REQUEST_DELAY_SECONDS = 0


def page_url(page_num):
    if page_num == 1:
        return f"{BASE_URL}/"

    return f"{BASE_URL}/page/{page_num}/"


def fetch_page_with_retry(
    url,
    retries=FETCH_RETRIES,
    delay_seconds=BASE_RETRY_DELAY_SECONDS,
):
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            return fetch_html(url)
        except Exception as error:
            last_error = error

            if attempt < retries:
                wait_seconds = delay_seconds * attempt + random.uniform(0, 2)
                print(
                    f"Retry Berita Malang {attempt}/{retries}: "
                    f"{url} | wait {wait_seconds:.1f}s"
                )
                time.sleep(wait_seconds)

    raise last_error


def extract_content(url):
    soup = fetch_page_with_retry(url)
    content_div = soup.select_one("div.main-single-content")

    if content_div:
        clean_article_soup(content_div)
        return clean_article_text(
            content_div.get_text("\n", strip=True)
        )

    text = soup.get_text("\n", strip=True)

    start = text.find("Oleh Penulis")
    end = text.find("Share:")

    if start == -1 or end == -1:
        return None

    return clean_article_text(
        text[start:end]
        .replace("Oleh Penulis\nComment: 0", "")
        .strip()
    )


def scrape(max_pages=200):
    cutoff = cutoff_date()
    page_num = 1
    articles = []
    consecutive_fetch_errors = 0

    while page_num <= max_pages:
        url = page_url(page_num)

        print(f"Scraping Berita Malang page {page_num}")
        time.sleep(REQUEST_DELAY_SECONDS)

        try:
            soup = fetch_page_with_retry(url)
            consecutive_fetch_errors = 0
        except Exception as error:
            print(f"Gagal buka Berita Malang page {page_num}: {error}")
            consecutive_fetch_errors += 1

            if consecutive_fetch_errors >= MAX_CONSECUTIVE_FETCH_ERRORS:
                break

            page_num += 1
            continue

        cards = soup.select("article.post-main")

        if not cards:
            break

        page_dates = []

        for card in cards:
            title_tag = card.select_one("h2.post-main-title a")
            date_tag = card.select_one(".post-main-datapost span")

            if not title_tag:
                continue

            published_date = (
                date_tag.get_text(strip=True)
                if date_tag
                else None
            )

            parsed_date = normalize_date(published_date)

            if published_date:
                page_dates.append(published_date)

            if is_older_than_cutoff(published_date, cutoff):
                continue

            article_url = title_tag["href"]

            try:
                content = extract_content(article_url)
            except Exception as error:
                print(
                    "Skip Berita Malang article after retry: "
                    f"{article_url} | {error}"
                )
                continue

            if not content:
                print(f"Konten Berita Malang kosong, skip: {article_url}")
                continue

            articles.append(
                {
                    "title": title_tag.get_text(strip=True),
                    "published_date": parsed_date,
                    "scraped_at": scraped_at(),
                    "author": None,
                    "category": None,
                    "content": content,
                    "url": article_url,
                    "source": SOURCE,
                }
            )

            print(f"[{len(articles)}] {title_tag.get_text(strip=True)}")

        if page_dates and all(
            is_older_than_cutoff(date_value, cutoff)
            for date_value in page_dates
        ):
            break

        page_num += 1

    df = records_to_df(articles)
    write_articles_csv(df, OUTPUT_PATH)

    print(f"\nSaved {len(df)} Berita Malang articles")

    return df


if __name__ == "__main__":
    print(scrape().head())
