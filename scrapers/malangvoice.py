from datetime import datetime
import re
from urllib.parse import urljoin

from scrapers.common import (
    clean_article_soup,
    clean_article_text,
    cutoff_date,
    fetch_html,
    is_older_than_cutoff,
    records_to_df,
    scraped_at,
    write_articles_csv,
)


BASE_URL = "https://malangvoice.com/kanal/malang-raya/kabupaten-malang/"
SITE_URL = "https://malangvoice.com"
SOURCE = "malang_voice"
OUTPUT_PATH = "csv/malang_voice_articles.csv"


def page_url(page_num):
    if page_num == 1:
        return BASE_URL

    return f"{BASE_URL}page/{page_num}/"


def clean_text(value):
    if value is None:
        return None

    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def parse_malangvoice_date(value):
    text = clean_text(value)

    if not text:
        return None

    patterns = [
        "%d %B %Y %I:%M %p",
        "%d %B %Y",
    ]

    for pattern in patterns:
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue

    return text


def scrape_list(cutoff, max_pages=200, include_older=False):
    rows = []
    seen_urls = set()

    for page_num in range(1, max_pages + 1):
        url = page_url(page_num)
        print(f"Scraping Malang Voice page {page_num}: {url}", flush=True)

        try:
            soup = fetch_html(url)
        except Exception as error:
            print(f"Gagal buka Malang Voice page {page_num}: {error}", flush=True)
            break

        cards = soup.select("div.td_module_wrap")

        if not cards:
            print(f"Malang Voice page {page_num}: no cards found", flush=True)
            break

        page_dates = []
        page_new_rows = 0

        for card in cards:
            title_tag = card.select_one(".td-module-title a, h3.entry-title a")
            date_tag = card.select_one("time, .td-post-date, .td-module-date")
            category_tag = card.select_one(".td-post-category")
            excerpt_tag = card.select_one(".td-excerpt")
            image_tag = card.select_one("img")

            if not title_tag:
                continue

            published_raw = (
                date_tag.get_text(" ", strip=True)
                if date_tag
                else None
            )
            published_date = parse_malangvoice_date(published_raw)

            if published_date:
                page_dates.append(published_date)

            article_url = urljoin(SITE_URL, title_tag.get("href"))

            if article_url in seen_urls:
                continue

            seen_urls.add(article_url)

            if (
                not include_older
                and is_older_than_cutoff(published_date, cutoff)
            ):
                continue

            row = {
                "title": clean_text(title_tag.get_text(" ", strip=True)),
                "url": article_url,
                "published_date": published_date,
                "published_raw": published_raw,
                "page_num": page_num,
                "list_page_url": url,
                "source_category": (
                    clean_text(category_tag.get_text(" ", strip=True))
                    if category_tag
                    else None
                ),
                "excerpt": (
                    clean_text(excerpt_tag.get_text(" ", strip=True))
                    if excerpt_tag
                    else None
                ),
                "image_url": (
                    image_tag.get("data-img-url")
                    or image_tag.get("data-src")
                    or image_tag.get("src")
                    if image_tag
                    else None
                ),
            }
            rows.append(row)
            page_new_rows += 1

            print(
                f"Malang Voice list page={page_num:03d} "
                f"date={published_date} | title={row['title'][:90]}",
                flush=True,
            )

        print(
            f"Malang Voice page {page_num}: cards={len(cards)} "
            f"new={page_new_rows} total={len(rows)}",
            flush=True,
        )

        if page_dates and all(
            is_older_than_cutoff(date_value, cutoff)
            for date_value in page_dates
        ):
            print("Malang Voice reached cutoff from list page", flush=True)
            break

    return records_to_df(rows)


def remove_article_noise(content):
    clean_article_soup(content)

    for selector in [
        "blockquote",
        ".wp-embedded-content",
        ".td-a-rec",
        ".td-adspot-title",
        ".td_block_related_posts",
        ".td-related-title",
        ".td-post-sharing",
        ".sharedaddy",
        ".jp-relatedposts",
        ".yarpp-related",
        ".crp_related",
    ]:
        for tag in content.select(selector):
            tag.decompose()

    for tag in list(content.find_all(["p", "div", "span", "a"])):
        text = clean_text(tag.get_text(" ", strip=True))
        lower = (text or "").lower()

        if not text:
            continue

        if lower.startswith(("baca juga", "simak juga", "artikel terkait")):
            tag.decompose()
            continue

        if lower in {"share", "facebook", "x", "whatsapp", "telegram"}:
            tag.decompose()
            continue


def extract_content(soup):
    content = (
        soup.select_one(".td-post-content .tdb-block-inner")
        or soup.select_one(".td-post-content")
        or soup.select_one(".tdb_single_content .tdb-block-inner")
        or soup.select_one(".tdb_single_content")
        or soup.select_one("article")
    )

    if not content:
        return None

    remove_article_noise(content)
    text = content.get_text("\n", strip=True)
    text = re.sub(r"^MALANGVOICE\s*[–-]\s*", "", text.strip())

    return clean_article_text(text)


def extract_article(row):
    soup = fetch_html(row["url"])
    title_tag = soup.select_one("h1")
    date_tag = soup.select_one("article time, time")
    author_tag = soup.select_one("article .td-post-author-name a, .td-post-author-name a")

    published_raw = (
        date_tag.get_text(" ", strip=True)
        if date_tag
        else row.get("published_raw") or row.get("published_date")
    )

    return {
        "title": (
            clean_text(title_tag.get_text(" ", strip=True))
            if title_tag
            else row["title"]
        ),
        "published_date": parse_malangvoice_date(published_raw),
        "scraped_at": scraped_at(),
        "author": (
            clean_text(author_tag.get_text(" ", strip=True))
            if author_tag
            else None
        ),
        "category": None,
        "content": extract_content(soup),
        "url": row["url"],
        "source": SOURCE,
        "image_url": row.get("image_url"),
        "excerpt": row.get("excerpt"),
        "source_category": row.get("source_category"),
    }


def scrape(max_pages=200):
    cutoff = cutoff_date()
    urls_df = scrape_list(cutoff, max_pages=max_pages)
    articles = []

    for index, row in urls_df.iterrows():
        try:
            article = extract_article(row)
        except Exception as error:
            print(
                f"[{index + 1}/{len(urls_df)}] Malang Voice failed: {error}",
                flush=True,
            )
            continue

        if is_older_than_cutoff(article["published_date"], cutoff):
            continue

        if not article.get("content"):
            print(f"Malang Voice content kosong, skip: {row['url']}", flush=True)
            continue

        articles.append(article)
        print(
            f"[{len(articles)}] Malang Voice date={article['published_date']} "
            f"| title={article['title'][:90]}",
            flush=True,
        )

    df = records_to_df(articles)
    write_articles_csv(df, OUTPUT_PATH)
    print(f"\nSaved {len(df)} Malang Voice articles", flush=True)
    return df


if __name__ == "__main__":
    print(scrape().head())
