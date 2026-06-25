import html as html_lib
import json
import re

from bs4 import BeautifulSoup

from scrapers.common import (
    clean_article_soup,
    clean_article_text,
    cutoff_date,
    fetch_html,
    fetch_text,
    is_older_than_cutoff,
    normalize_date,
    records_to_df,
    scraped_at,
    write_articles_csv,
)


BASE_URL = "https://radarmalang.jawapos.com/pendidikan"
SOURCE = "radar_malang"
OUTPUT_PATH = "csv/radar_malang_articles.csv"


def extract_data_page(html_text):
    match = re.search(
        r'data-page="(.*?)"',
        html_text,
        re.DOTALL,
    )

    if not match:
        return None

    return json.loads(
        html_lib.unescape(
            match.group(1)
        )
    )


def page_url(page_num):
    if page_num == 1:
        return BASE_URL

    return f"{BASE_URL}?page={page_num}"


def scrape_list(cutoff, max_pages=20):
    articles = []
    page_num = 1
    stop = False

    while not stop and page_num <= max_pages:
        url = page_url(page_num)

        print(f"Scraping Radar Malang page {page_num}")

        try:
            html_text = fetch_text(url)
        except Exception as error:
            print(f"Gagal buka Radar Malang page {page_num}: {error}")
            break

        page_data = extract_data_page(html_text)

        if not page_data:
            print("Radar Malang data-page not found")
            break

        article_items = (
            page_data["props"]
            ["category"]
            ["articles"]
            ["data"]
        )

        if not article_items:
            break

        for article in article_items:
            published_date = article.get("date")

            if is_older_than_cutoff(published_date, cutoff):
                stop = True
                break

            article_url = (
                "https://radarmalang.jawapos.com/pendidikan/"
                f"{article['article_id']}/"
                f"{article['slug']}"
            )

            articles.append(
                {
                    "title": article.get("title"),
                    "url": article_url,
                    "published_date": published_date,
                }
            )

        page_num += 1

    return records_to_df(articles)


def extract_article(row):
    html_text = fetch_text(row["url"])
    page_data = extract_data_page(html_text)

    if not page_data:
        return extract_article_from_dom(html_text, row)

    article = page_data["props"]["article"]
    author = None
    editor = None

    authors = article.get("authors")

    if isinstance(authors, list) and authors:
        first_author = authors[0]

        if isinstance(first_author, dict):
            author = first_author.get("name")

    article_editor = article.get("editor")

    if isinstance(article_editor, dict):
        editor = article_editor.get("name")

    content_soup = BeautifulSoup(
        article.get("content") or "",
        "html.parser",
    )

    clean_article_soup(content_soup)

    category = article.get("category")

    return {
        "title": article.get("title") or row["title"],
        "published_date": normalize_date(article.get("date") or row["published_date"]),
        "scraped_at": scraped_at(),
        "author": author,
        "category": category.get("name") if isinstance(category, dict) else None,
        "content": clean_article_text(
            content_soup.get_text(separator="\n", strip=True)
        ),
        "url": row["url"],
        "source": SOURCE,
        "editor": editor,
        "image_url": article.get("image"),
    }


def extract_article_from_dom(html_text, row):
    soup = BeautifulSoup(html_text, "html.parser")
    title_tag = soup.select_one("h1")
    content_box = soup.select_one(".rt-Box.konten")

    if not content_box:
        boxes = soup.select(".rt-Box")
        content_box = max(
            boxes,
            key=lambda tag: len(tag.get_text(" ", strip=True)),
            default=None,
        )

    if not content_box:
        raise ValueError("Radar Malang content container not found")

    clean_article_soup(content_box)

    return {
        "title": title_tag.get_text(" ", strip=True) if title_tag else row["title"],
        "published_date": normalize_date(row["published_date"]),
        "scraped_at": scraped_at(),
        "author": None,
        "category": "Pendidikan",
        "content": clean_article_text(
            content_box.get_text(separator="\n", strip=True)
        ),
        "url": row["url"],
        "source": SOURCE,
        "editor": None,
        "image_url": None,
    }


def scrape():
    cutoff = cutoff_date()
    urls_df = scrape_list(cutoff)
    articles = []

    for index, row in urls_df.iterrows():
        try:
            article = extract_article(row)
        except Exception as error:
            print(f"[{index + 1}/{len(urls_df)}] Radar Malang failed: {error}")
            continue

        if is_older_than_cutoff(article["published_date"], cutoff):
            continue

        articles.append(article)
        print(f"[{len(articles)}] {article['title']}")

    df = records_to_df(articles)

    write_articles_csv(df, OUTPUT_PATH)
    print(f"\nSaved {len(df)} Radar Malang articles")

    return df


if __name__ == "__main__":
    print(scrape().head())
