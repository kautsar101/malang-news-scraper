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


BASE_URL = "https://malangposcomedia.id/category/kabupaten-malang"
SOURCE = "malangposco"
OUTPUT_PATH = "csv/malangposco_articles.csv"


def page_url(page_num):
    if page_num == 1:
        return f"{BASE_URL}/"

    return f"{BASE_URL}/page/{page_num}/"


def scrape_list(cutoff, max_pages=20):
    articles = []
    page_num = 1
    stop = False

    while not stop and page_num <= max_pages:
        url = page_url(page_num)

        print(f"Scraping Malang Posco page {page_num}")

        try:
            soup = fetch_html(url)
        except Exception as error:
            print(f"Gagal buka Malang Posco page {page_num}: {error}")
            break

        cards = soup.select("div.tdb_module_loop")

        if not cards:
            break

        for card in cards:
            title_tag = card.select_one("p.entry-title a")
            date_tag = card.select_one("time.entry-date")
            image_tag = card.select_one("span.entry-thumb")
            excerpt_tag = card.select_one("div.td-excerpt")

            if not title_tag:
                continue

            published_date = date_tag.get("datetime") if date_tag else None

            if is_older_than_cutoff(published_date, cutoff):
                stop = True
                break

            image_url = None

            if image_tag:
                style = image_tag.get("style", "")

                if "url(" in style:
                    image_url = style.split("url(")[1].split(")")[0]

            articles.append(
                {
                    "title": title_tag.get_text(strip=True),
                    "url": title_tag["href"],
                    "published_date": published_date,
                    "image_url": image_url,
                    "excerpt": (
                        excerpt_tag.get_text(" ", strip=True)
                        if excerpt_tag
                        else None
                    ),
                }
            )

        page_num += 1

    return records_to_df(articles)


def extract_article(row):
    soup = fetch_html(row["url"])
    content_div = soup.select_one("div.td-post-content")

    content = None

    if content_div:
        clean_article_soup(content_div)
        content = clean_article_text(
            content_div.get_text("\n", strip=True)
        )
    else:
        paragraphs = soup.select("p.wp-block-paragraph")

        if paragraphs:
            content = clean_article_text("\n".join(
                paragraph.get_text(" ", strip=True)
                for paragraph in paragraphs
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
        "image_url": row.get("image_url"),
        "excerpt": row.get("excerpt"),
    }


def scrape():
    cutoff = cutoff_date()
    urls_df = scrape_list(cutoff)
    articles = []

    for index, row in urls_df.iterrows():
        try:
            article = extract_article(row)
        except Exception as error:
            print(f"[{index + 1}/{len(urls_df)}] Malang Posco failed: {error}")
            continue

        articles.append(article)
        print(f"[{len(articles)}] {article['title']}")

    df = records_to_df(articles)

    write_articles_csv(df, OUTPUT_PATH)
    print(f"\nSaved {len(df)} Malang Posco articles")

    return df


if __name__ == "__main__":
    print(scrape().head())
