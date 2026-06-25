from scrapers.common import (
    clean_article_soup,
    clean_article_text,
    clean_lines,
    cutoff_date,
    fetch_html,
    is_older_than_cutoff,
    normalize_date,
    records_to_df,
    scraped_at,
    write_articles_csv,
)


BASE_URL = "https://www.nusadaily.com/search"
SOURCE = "nusadaily"
OUTPUT_PATH = "csv/nusadaily_articles.csv"


def scrape_list(cutoff, max_pages=20):
    articles = []
    page_num = 1
    stop = False

    while not stop and page_num <= max_pages:
        url = f"{BASE_URL}?q=kabupaten+malang&page={page_num}"

        print(f"Scraping NusaDaily page {page_num}")

        try:
            soup = fetch_html(url)
        except Exception as error:
            print(f"Gagal buka NusaDaily page {page_num}: {error}")
            break

        cards = soup.select("div.post-item")

        if not cards:
            break

        for card in cards:
            title_tag = card.select_one("h3.title a")
            date_tag = card.select_one("p.post-meta span")

            if not title_tag:
                continue

            published_date = (
                date_tag.get_text(strip=True)
                if date_tag
                else None
            )

            if is_older_than_cutoff(published_date, cutoff):
                stop = True
                break

            articles.append(
                {
                    "title": title_tag.get_text(strip=True),
                    "url": title_tag["href"],
                    "published_date": published_date,
                }
            )

        page_num += 1

    return records_to_df(articles)


def extract_article(row):
    soup = fetch_html(row["url"])
    content_div = soup.select_one("div.post-text.mt-4")
    content = None

    if content_div:
        clean_article_soup(content_div)
        content = clean_article_text(clean_lines(
            content_div.get_text(
                "\n",
                strip=True,
            )
        ))

    return {
        "title": row["title"],
        "published_date": normalize_date(row["published_date"]),
        "scraped_at": scraped_at(),
        "author": None,
        "category": None,
        "content": content,
        "url": row["url"],
        "source": SOURCE,
    }


def scrape():
    cutoff = cutoff_date()
    urls_df = scrape_list(cutoff)
    articles = []

    for index, row in urls_df.iterrows():
        try:
            article = extract_article(row)
        except Exception as error:
            print(f"[{index + 1}/{len(urls_df)}] NusaDaily failed: {error}")
            continue

        articles.append(article)
        print(f"[{len(articles)}] {article['title']}")

    df = records_to_df(articles)

    write_articles_csv(df, OUTPUT_PATH)
    print(f"\nSaved {len(df)} NusaDaily articles")

    return df


if __name__ == "__main__":
    print(scrape().head())
