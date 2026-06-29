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


BASE_URL = "https://seputarmalang.com/lokasi/kabupaten-malang/"
SOURCE = "seputar_malang"
OUTPUT_PATH = "csv/seputar_malang_articles.csv"


def scrape_list():
    articles = []

    print("Scraping Seputar Malang list")

    soup = fetch_html(BASE_URL)

    for card in soup.select("article.jeg_post"):
        title_tag = card.select_one("h3.jeg_post_title a")

        if not title_tag:
            continue

        articles.append(
            {
                "title": title_tag.get_text(strip=True),
                "url": title_tag["href"],
            }
        )

    return records_to_df(articles)


def extract_article(row):
    soup = fetch_html(row["url"])
    content_div = soup.select_one("div.content-inner")
    content = None

    if content_div:
        clean_article_soup(content_div)
        content = clean_article_text(
            content_div.get_text("\n", strip=True)
        )

    title_tag = soup.select_one("h1.jeg_post_title")
    subtitle_tag = soup.select_one("h2.jeg_post_subtitle")
    author_tag = soup.select_one(".jeg_meta_author a")
    date_tag = soup.select_one(".jeg_meta_date a")

    return {
        "title": title_tag.get_text(strip=True) if title_tag else row["title"],
        "published_date": normalize_date(
            date_tag.get_text(strip=True)
            if date_tag
            else None
        ),
        "scraped_at": scraped_at(),
        "author": author_tag.get_text(strip=True) if author_tag else None,
        "category": None,
        "content": content,
        "url": row["url"],
        "source": SOURCE,
        "subtitle": subtitle_tag.get_text(strip=True) if subtitle_tag else None,
    }


def scrape():
    cutoff = cutoff_date()
    urls_df = scrape_list()
    articles = []

    for index, row in urls_df.iterrows():
        try:
            article = extract_article(row)
        except Exception as error:
            print(f"[{index + 1}/{len(urls_df)}] Seputar Malang failed: {error}")
            continue

        if is_older_than_cutoff(article["published_date"], cutoff):
            continue

        articles.append(article)
        print(f"[{len(articles)}] {article['title']}")

    df = records_to_df(articles)

    write_articles_csv(df, OUTPUT_PATH)
    print(f"\nSaved {len(df)} Seputar Malang articles")

    return df


if __name__ == "__main__":
    print(scrape().head())
