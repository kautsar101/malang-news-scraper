import asyncio
import re

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from scrapers.common import (
    clean_article_soup,
    clean_article_text,
    cutoff_date,
    is_older_than_cutoff,
    normalize_date,
    records_to_df,
    scraped_at,
    write_articles_csv,
)


BASE_URL = "https://malangtimes.com/kanal/pendidikan"
SOURCE = "malangtimes"
OUTPUT_PATH = "csv/malangtimes_articles.csv"


async def scrape_list(page, max_clicks=8):
    await page.goto(
        BASE_URL,
        wait_until="networkidle",
    )

    for click_num in range(max_clicks):
        load_more = page.locator("#load-more")

        if await load_more.count() == 0:
            break

        try:
            await load_more.click(timeout=5000)
            await page.wait_for_timeout(2000)
        except Exception:
            break

        print(f"Loaded Malang Times page chunk {click_num + 1}")

    soup = BeautifulSoup(
        await page.content(),
        "html.parser",
    )

    articles = []

    for link_tag in soup.select("a[href*='/baca/']"):
        url = link_tag.get("href")
        title_tag = link_tag.select_one("h3")

        if not url or not title_tag:
            continue

        articles.append(
            {
                "title": title_tag.get_text(strip=True),
                "url": url,
            }
        )

    return records_to_df(articles)


async def extract_article(page, row):
    await page.goto(
        row["url"],
        wait_until="networkidle",
    )

    soup = BeautifulSoup(
        await page.content(),
        "html.parser",
    )

    title_tag = soup.select_one("h1")
    date_tag = soup.select_one("p.float-right.text-muted")
    content_tag = soup.select_one(
        "#appCapsule > div:nth-child(6) > div.col-12.col-lg-8 "
        "> div.blog-post.mt-1 > div.post-body"
    )

    if content_tag:
        clean_article_soup(content_tag)

    text = soup.get_text(" ", strip=True)
    author = None
    editor = None

    author_match = re.search(
        r"Penulis\s*:\s*(.*?)\s*-\s*Editor",
        text,
    )
    editor_match = re.search(
        r"Editor\s*:\s*(.*?)(?:Baca Juga|$)",
        text,
    )

    if author_match:
        author = author_match.group(1).strip()

    if editor_match:
        editor = editor_match.group(1).strip()

    return {
        "title": title_tag.get_text(strip=True) if title_tag else row["title"],
        "published_date": normalize_date(
            date_tag.get_text(strip=True)
            if date_tag
            else None
        ),
        "scraped_at": scraped_at(),
        "author": author,
        "category": "Pendidikan",
        "content": clean_article_text(
            content_tag.get_text(separator="\n", strip=True)
            if content_tag
            else None
        ),
        "url": row["url"],
        "source": SOURCE,
        "editor": editor,
    }


async def scrape_async():
    cutoff = cutoff_date()
    articles = []

    async with async_playwright() as playwright_instance:
        browser = await playwright_instance.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            urls_df = await scrape_list(page)

            for index, row in urls_df.iterrows():
                try:
                    article = await extract_article(page, row)
                except Exception as error:
                    print(
                        f"[{index + 1}/{len(urls_df)}] "
                        f"Malang Times failed: {error}"
                    )
                    continue

                if is_older_than_cutoff(article["published_date"], cutoff):
                    continue

                articles.append(article)
                print(f"[{len(articles)}] {article['title']}")
        finally:
            await browser.close()

    df = records_to_df(articles)

    write_articles_csv(df, OUTPUT_PATH)
    print(f"\nSaved {len(df)} Malang Times articles")

    return df


def scrape():
    return asyncio.run(scrape_async())


if __name__ == "__main__":
    print(scrape().head())
