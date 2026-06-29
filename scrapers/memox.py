from urllib.parse import urljoin

from scrapers.common import (
    clean_article_soup,
    clean_article_text,
    cutoff_date,
    fetch_html,
    is_older_than_cutoff,
    normalize_date,
    records_to_df,
    scraped_at,
    write_articles_csv,
)


BASE_URL = "https://memox.co.id/tag/kabupaten-malang"
SOURCE = "memox"
OUTPUT_PATH = "csv/memox_articles.csv"


def page_url(page_num):
    if page_num == 1:
        return f"{BASE_URL}/"

    return f"{BASE_URL}/page/{page_num}/"


def scrape_list(cutoff, max_pages=200):
    rows = []

    for page_num in range(1, max_pages + 1):
        url = page_url(page_num)
        print(f"Scraping Memox page {page_num}: {url}", flush=True)

        try:
            soup = fetch_html(url)
        except Exception as error:
            print(f"Gagal buka Memox page {page_num}: {error}", flush=True)
            break

        cards = soup.select("article")

        if not cards:
            break

        page_dates = []

        for card in cards:
            title_tag = card.select_one("h2.entry-title a[href], h3 a[href]")
            link_tag = title_tag or card.select_one("a.post-thumbnail[href]")
            date_tag = card.select_one("time.entry-date.published, time.entry-date")
            excerpt_tag = card.select_one(".entry-content, .entry-summary")
            image_tag = card.select_one("img")

            if not title_tag or not link_tag:
                continue

            published_date = (
                date_tag.get("datetime")
                or date_tag.get_text(" ", strip=True)
                if date_tag
                else None
            )

            if published_date:
                page_dates.append(published_date)

            if is_older_than_cutoff(published_date, cutoff):
                continue

            rows.append(
                {
                    "title": title_tag.get_text(" ", strip=True),
                    "url": urljoin(BASE_URL, link_tag["href"]),
                    "published_date": published_date,
                    "page_num": page_num,
                    "list_page_url": url,
                    "excerpt": (
                        excerpt_tag.get_text(" ", strip=True)
                        if excerpt_tag
                        else None
                    ),
                    "image_url": (
                        image_tag.get("data-src")
                        or image_tag.get("src")
                        if image_tag
                        else None
                    ),
                }
            )

        if page_dates and all(
            is_older_than_cutoff(date_value, cutoff)
            for date_value in page_dates
        ):
            break

    return records_to_df(rows)


def extract_content(soup):
    content = (
        soup.select_one(".entry-content")
        or soup.select_one(".gmr-box-content")
        or soup.select_one("article")
    )

    if not content:
        return None

    clean_article_soup(content)
    return clean_article_text(content.get_text("\n", strip=True))


def extract_article(row):
    soup = fetch_html(row["url"])
    title_tag = soup.select_one("h1.entry-title, h1")
    date_tag = soup.select_one("time.entry-date.published, time.entry-date")
    author_tag = soup.select_one(".author a, .byline a")

    return {
        "title": title_tag.get_text(" ", strip=True) if title_tag else row["title"],
        "published_date": normalize_date(
            date_tag.get("datetime")
            or date_tag.get_text(" ", strip=True)
            if date_tag
            else row["published_date"]
        ),
        "scraped_at": scraped_at(),
        "author": author_tag.get_text(" ", strip=True) if author_tag else None,
        "category": None,
        "content": extract_content(soup),
        "url": row["url"],
        "source": SOURCE,
        "image_url": row.get("image_url"),
        "excerpt": row.get("excerpt"),
    }


def scrape(max_pages=200):
    cutoff = cutoff_date()
    urls_df = scrape_list(cutoff, max_pages=max_pages)
    articles = []

    for index, row in urls_df.iterrows():
        try:
            article = extract_article(row)
        except Exception as error:
            print(f"[{index + 1}/{len(urls_df)}] Memox failed: {error}", flush=True)
            continue

        if is_older_than_cutoff(article["published_date"], cutoff):
            continue

        if not article.get("content"):
            print(f"Memox content kosong, skip: {row['url']}", flush=True)
            continue

        articles.append(article)
        print(f"[{len(articles)}] {article['title']}", flush=True)

    df = records_to_df(articles)
    write_articles_csv(df, OUTPUT_PATH)
    print(f"\nSaved {len(df)} Memox articles", flush=True)
    return df


if __name__ == "__main__":
    print(scrape().head())
