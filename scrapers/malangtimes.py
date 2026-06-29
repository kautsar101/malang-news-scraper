import asyncio
import re
from datetime import datetime
from urllib.parse import urljoin

from scrapers.common import (
    clean_article_soup,
    clean_article_text,
    cutoff_date,
    is_older_than_cutoff,
    normalize_date,
    parse_date,
    records_to_df,
    scraped_at,
    shift_datetime,
    write_articles_csv,
)


BASE_URL = "https://malangtimes.com/search?keyword=kabupaten+malang"
SOURCE = "malangtimes"
OUTPUT_PATH = "csv/malangtimes_articles.csv"
RELATIVE_DATE_PATTERN = re.compile(
    r"\b(\d+)\s+(menit|jam|hari|minggu|bulan|tahun)\s+(?:yang\s+)?lalu\b",
    re.IGNORECASE,
)


def parse_relative_date(value, now=None):
    if not value:
        return None

    match = RELATIVE_DATE_PATTERN.search(str(value))

    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2).lower()
    now = now or datetime.now()

    if unit == "menit":
        parsed = shift_datetime(now, minutes=-amount)
    elif unit == "jam":
        parsed = shift_datetime(now, hours=-amount)
    elif unit == "hari":
        parsed = shift_datetime(now, days=-amount)
    elif unit == "minggu":
        parsed = shift_datetime(now, weeks=-amount)
    elif unit == "bulan":
        parsed = shift_datetime(now, months=-amount)
    elif unit == "tahun":
        parsed = shift_datetime(now, years=-amount)
    else:
        return None

    return parsed.date().isoformat()


def find_relative_date_text(tag):
    candidates = []

    for current_tag in [
        tag,
        tag.parent,
        tag.parent.parent if tag.parent else None,
        tag.parent.parent.parent if tag.parent and tag.parent.parent else None,
    ]:
        if current_tag:
            candidates.append(current_tag.get_text(" ", strip=True))

    for text in candidates:
        match = RELATIVE_DATE_PATTERN.search(text)

        if match:
            return match.group(0)

    return None


async def scrape_list(page, max_clicks=40):
    from bs4 import BeautifulSoup

    print(f"Malang Times list goto: {BASE_URL}", flush=True)
    await page.goto(
        BASE_URL,
        wait_until="domcontentloaded",
        timeout=30000,
    )

    articles = []
    seen_urls = set()

    for click_num in range(max_clicks + 1):
        soup = BeautifulSoup(
            await page.content(),
            "html.parser",
        )

        for link_tag in soup.select("a[href*='/baca/']"):
            url = urljoin(BASE_URL, link_tag.get("href") or "")
            title_tag = link_tag.select_one("h3")

            if not url or url in seen_urls:
                continue

            title = (
                title_tag.get_text(strip=True)
                if title_tag
                else link_tag.get_text(" ", strip=True)
            )
            relative_date = find_relative_date_text(link_tag)
            published_date = parse_relative_date(relative_date)

            seen_urls.add(url)

            articles.append(
                {
                    "title": title,
                    "url": url,
                    "published_date": published_date,
                    "relative_date": relative_date,
                }
            )

        load_more = page.locator("#load-more")

        if await load_more.count() == 0:
            break

        try:
            await load_more.click(timeout=5000)
            await page.wait_for_timeout(2000)
        except Exception as error:
            print(f"Load more Malang Times stopped: {error}")
            break

        print(f"Loaded Malang Times page chunk {click_num + 1}")

    return records_to_df(articles)


async def extract_article(page, row):
    from bs4 import BeautifulSoup

    print(f"Malang Times article goto: {row['url']}", flush=True)
    await page.goto(
        row["url"],
        wait_until="domcontentloaded",
        timeout=30000,
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

    detail_date = (
        date_tag.get_text(strip=True)
        if date_tag
        else None
    )
    published_date = (
        normalize_date(detail_date)
        if parse_date(detail_date)
        else row.get("published_date")
    )

    return {
        "title": title_tag.get_text(strip=True) if title_tag else row["title"],
        "published_date": published_date,
        "scraped_at": scraped_at(),
        "author": author,
        "category": None,
        "content": clean_article_text(
            content_tag.get_text(separator="\n", strip=True)
            if content_tag
            else None
        ),
        "url": row["url"],
        "source": SOURCE,
        "editor": editor,
    }


async def scrape_async(max_clicks=40):
    print("Malang Times: importing Playwright...", flush=True)
    from playwright.async_api import async_playwright

    cutoff = cutoff_date()
    articles = []

    async with async_playwright() as playwright_instance:
        print("Malang Times: launching Chromium...", flush=True)
        browser = await playwright_instance.chromium.launch(headless=True)
        print("Malang Times: Chromium ready.", flush=True)
        page = await browser.new_page()

        try:
            urls_df = await scrape_list(page, max_clicks=max_clicks)
            if "published_date" in urls_df.columns:
                urls_df = urls_df[
                    urls_df["published_date"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .ne("")
                ].reset_index(drop=True)
                urls_df = urls_df[
                    ~urls_df["published_date"].apply(
                        lambda value: is_older_than_cutoff(value, cutoff)
                    )
                ].reset_index(drop=True)

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


def scrape(max_clicks=40):
    return asyncio.run(scrape_async(max_clicks=max_clicks))


if __name__ == "__main__":
    print(scrape().head())
