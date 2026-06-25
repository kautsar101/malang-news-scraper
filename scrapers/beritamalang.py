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


BASE_URL = "https://beritamalang.media"
SOURCE = "beritamalang_media"
OUTPUT_PATH = "csv/beritamalang_media_articles.csv"


def page_url(page_num):
    if page_num == 1:
        return BASE_URL

    return f"{BASE_URL}/page/{page_num}/"


def extract_content(url):
    soup = fetch_html(url)
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


def scrape(max_pages=20):
    cutoff = cutoff_date()
    page_num = 1
    articles = []
    stop = False

    while not stop and page_num <= max_pages:
        url = page_url(page_num)

        print(f"Scraping Berita Malang page {page_num}")

        try:
            soup = fetch_html(url)
        except Exception as error:
            print(f"Gagal buka Berita Malang page {page_num}: {error}")
            break

        cards = soup.select("article.post-main")

        if not cards:
            break

        for card in cards:
            title_tag = card.select_one("h2.post-main-title a")
            date_tag = card.select_one(".post-main-datapost span")
            category_tag = card.select_one(".post-main-category")

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

            article_url = title_tag["href"]

            try:
                content = extract_content(article_url)
            except Exception as error:
                print(f"Gagal scrape artikel Berita Malang: {article_url}")
                print(error)
                continue

            if not content:
                print(f"Konten Berita Malang kosong, skip: {article_url}")
                continue

            articles.append(
                {
                    "title": title_tag.get_text(strip=True),
                    "published_date": normalize_date(published_date),
                    "scraped_at": scraped_at(),
                    "author": None,
                    "category": (
                        category_tag.get_text(",", strip=True)
                        if category_tag
                        else None
                    ),
                    "content": content,
                    "url": article_url,
                    "source": SOURCE,
                }
            )

            print(f"[{len(articles)}] {title_tag.get_text(strip=True)}")

        page_num += 1

    df = records_to_df(articles)
    write_articles_csv(df, OUTPUT_PATH)

    print(f"\nSaved {len(df)} Berita Malang articles")

    return df


if __name__ == "__main__":
    print(scrape().head())
