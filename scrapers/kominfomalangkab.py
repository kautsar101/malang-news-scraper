import urllib3

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


urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)

BASE_URL = "https://kominfo.malangkab.go.id/berita"
SOURCE = "kominfo_malangkab"
OUTPUT_PATH = "csv/kominfo_malangkab_articles.csv"
MAX_CONSECUTIVE_FETCH_ERRORS = 3


def normalize_url(url):
    if not url:
        return url

    return str(url).replace(
        "http://kominfo.malangkab.go.id",
        "https://kominfo.malangkab.go.id",
        1,
    )


def scrape_list(cutoff, max_pages=200):
    articles = []
    page_num = 1
    stop = False
    consecutive_fetch_errors = 0

    while not stop and page_num <= max_pages:
        if page_num == 1:
            url = BASE_URL
        else:
            url = f"{BASE_URL}?page={page_num}"

        print(f"Scraping Kominfo page {page_num}")

        try:
            soup = fetch_html(url, verify=False)
            consecutive_fetch_errors = 0
        except Exception as error:
            print(f"Gagal buka Kominfo page {page_num}: {error}")
            consecutive_fetch_errors += 1

            if consecutive_fetch_errors >= MAX_CONSECUTIVE_FETCH_ERRORS:
                break

            page_num += 1
            continue

        cards = soup.select("div.bg-white.rounded-xl.shadow-lg")

        if not cards:
            break

        page_dates = []

        for card in cards:
            title_tag = card.select_one("h3")
            link_tag = (
                card.select_one("a.block.flex-grow[href*='/berita/']")
                or card.select_one("a[href*='/berita/']")
            )
            date_tag = card.select_one("p.text-sm.text-gray-500")

            if not title_tag or not link_tag:
                continue

            published_date = (
                date_tag.get_text(" ", strip=True)
                if date_tag
                else None
            )

            if published_date:
                page_dates.append(published_date)

            if is_older_than_cutoff(published_date, cutoff):
                continue

            articles.append(
                {
                    "title": title_tag.get_text(strip=True),
                    "url": normalize_url(link_tag["href"]),
                    "published_date": published_date,
                }
            )

        if page_dates and all(
            is_older_than_cutoff(date_value, cutoff)
            for date_value in page_dates
        ):
            stop = True

        page_num += 1

    return records_to_df(articles)


def extract_article(row):
    article_url = normalize_url(row["url"])
    soup = fetch_html(article_url, verify=False)

    title_tag = soup.select_one("h1")
    date_tag = soup.select_one("p.text-sm.text-gray-500")
    image_tag = soup.select_one("div.mb-6 img")
    content_div = soup.select_one("div.prose")

    content = None

    if content_div:
        clean_article_soup(content_div)
        content = clean_article_text(
            content_div.get_text("\n", strip=True)
        )

    detail_date = (
        date_tag.get_text(" ", strip=True)
        if date_tag
        else None
    )

    return {
        "title": title_tag.get_text(strip=True) if title_tag else row["title"],
        "published_date": normalize_date(detail_date or row["published_date"]),
        "scraped_at": scraped_at(),
        "author": None,
        "category": None,
        "content": content,
        "url": article_url,
        "source": SOURCE,
        "image_url": image_tag["src"] if image_tag else None,
    }


def scrape(max_pages=200):
    cutoff = cutoff_date()
    urls_df = scrape_list(cutoff, max_pages=max_pages)
    articles = []

    for index, row in urls_df.iterrows():
        if is_older_than_cutoff(row["published_date"], cutoff):
            continue

        try:
            article = extract_article(row)
        except Exception as error:
            print(f"[{index + 1}/{len(urls_df)}] Kominfo failed: {error}")
            continue

        if is_older_than_cutoff(article["published_date"], cutoff):
            continue

        articles.append(article)
        print(f"[{len(articles)}] {article['title']}")

    df = records_to_df(articles)

    write_articles_csv(df, OUTPUT_PATH)
    print(f"\nSaved {len(df)} Kominfo articles")

    return df


if __name__ == "__main__":
    print(scrape().head())
