import asyncio
import html
import re
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

from scrapers.common import (
    clean_article_text,
    cutoff_date,
    fetch_text,
    is_older_than_cutoff,
    normalize_date,
    records_to_df,
    scraped_at,
    write_articles_csv,
)


BASE_URL = "https://timesindonesia.co.id/search?q=kabupaten%20malang"
API_URL = "https://timesindonesia.co.id/api/news/all"
API_KEY = "VT926Xevq9juBMyR2Iddjm5OZRLP"
SEARCH_KEYWORD = "kabupaten malang"
API_LIMIT = 9
SITE_URL = "https://timesindonesia.co.id"
SOURCE = "times_indonesia"
OUTPUT_PATH = "csv/times_indonesia_articles.csv"


def page_url(page_num):
    if page_num == 1:
        return BASE_URL

    return f"{BASE_URL}&page={page_num}"


def api_url(offset=0, limit=API_LIMIT):
    keyword = quote_plus(SEARCH_KEYWORD)
    return (
        f"{API_URL}?news_type=search&offset={offset}"
        f"&title={keyword}&limit={limit}"
    )


def clean_text(value):
    if value is None:
        return None

    text = re.sub(r"\s+", " ", str(value)).strip()

    return text or None


def normalize_image_url(value):
    if not value:
        return None

    url = urljoin(SITE_URL, value)
    parsed = urlparse(url)

    if parsed.path == "/_next/image":
        original_urls = parse_qs(parsed.query).get("url")

        if original_urls:
            return unquote(original_urls[0])

    return url


def date_from_image_url(value):
    if not value:
        return None

    match = re.search(r"/(20\d{2})/(\d{2})/(\d{2})/", value)

    if not match:
        return None

    return "-".join(match.groups())


def strip_tags(value):
    if value is None:
        return None

    return clean_text(
        html.unescape(
            re.sub(r"<[^>]+>", " ", value)
        )
    )


def fetch_api_items(offset=0, limit=API_LIMIT):
    import requests

    url = api_url(offset=offset, limit=limit)
    print(f"Times Indonesia API GET offset={offset}: {url}", flush=True)

    response = requests.get(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
            "Referer": BASE_URL,
        },
        timeout=20,
    )
    response.raise_for_status()

    payload = response.json()
    items = payload.get("data") or []

    print(
        f"Times Indonesia API OK offset={offset}: rows={len(items)}",
        flush=True,
    )

    return items


def api_item_to_row(item, offset=0, index=0):
    url_path = item.get("url_ci4") or item.get("url_ci")
    published_date = normalize_date(item.get("news_datepub"))

    return {
        "title": clean_text(item.get("news_title")),
        "url": urljoin(SITE_URL, url_path or ""),
        "published_date": published_date,
        "relative_date": None,
        "date_source": "api",
        "page_num": (offset // API_LIMIT) + 1,
        "offset": offset,
        "offset_index": index,
        "list_page_url": api_url(offset=offset, limit=API_LIMIT),
        "source_category": clean_text(item.get("cat_title")),
        "excerpt": clean_text(
            item.get("news_description")
            or item.get("news_subtitle")
        ),
        "image_url": item.get("news_image_new"),
        "news_id": item.get("news_id"),
        "author": clean_text(
            item.get("news_writer")
            or item.get("publisher_name")
        ),
    }


def find_relative_date_text_from_text(text):
    match = re.search(
        r"\b\d+\s+(?:menit|jam|hari|minggu|bulan|tahun)\s+(?:yang\s+)?lalu\b",
        text or "",
        re.IGNORECASE,
    )

    return match.group(0) if match else None


def find_relative_date_text(card):
    text = card.get_text(" ", strip=True)
    return find_relative_date_text_from_text(text)


def parse_list_html(page_html, cutoff=None, page_num=1, list_page_url=None):
    rows = []
    card_pattern = re.compile(
        r'<a class="block group" href="([^"]+)">(.*?)'
        r'(?=<a class="block group" href=|</main>|$)',
        re.DOTALL,
    )

    for href, block in card_pattern.findall(page_html):
        if not href or href.startswith("/tag/") or href.startswith("/ekoran"):
            continue

        title_match = re.search(r"<h3[^>]*>(.*?)</h3>", block, re.DOTALL)

        if not title_match:
            continue

        excerpt_match = re.search(
            r'<p class="text-muted-foreground[^"]*"[^>]*>(.*?)</p>',
            block,
            re.DOTALL,
        )
        category_match = re.search(
            r'<span class="bg-\[#7a0f1f\][^"]*"[^>]*>(.*?)</span>',
            block,
            re.DOTALL,
        )
        image_match = re.search(
            r'<img[^>]+(?:src|data-src)="([^"]+)"',
            block,
            re.DOTALL,
        )
        image_url = (
            normalize_image_url(html.unescape(image_match.group(1)))
            if image_match
            else None
        )
        relative_date = find_relative_date_text_from_text(strip_tags(block))
        published_date = (
            normalize_date(relative_date)
            if relative_date
            else date_from_image_url(image_url)
        )
        date_source = "relative_text" if relative_date else "image_url"

        if cutoff and is_older_than_cutoff(published_date, cutoff):
            continue

        rows.append(
            {
                "title": strip_tags(title_match.group(1)),
                "url": urljoin(SITE_URL, html.unescape(href)),
                "published_date": published_date,
                "relative_date": relative_date,
                "date_source": date_source,
                "page_num": page_num,
                "list_page_url": list_page_url,
                "source_category": (
                    strip_tags(category_match.group(1))
                    if category_match
                    else None
                ),
                "excerpt": (
                    strip_tags(excerpt_match.group(1))
                    if excerpt_match
                    else None
                ),
                "image_url": image_url,
            }
        )

    return rows


def parse_list_soup(soup, cutoff=None, page_num=1, list_page_url=None):
    rows = []
    cards = soup.select("a.block.group[href]")

    for card in cards:
        href = card.get("href")

        if not href or href.startswith("/tag/") or href.startswith("/ekoran"):
            continue

        title_tag = card.select_one("h3")
        excerpt_tag = card.select_one("p.text-muted-foreground")
        category_tag = card.select_one("span.bg-\\[\\#7a0f1f\\]")
        image_tag = card.select_one("img")

        if not title_tag:
            continue

        image_url = (
            normalize_image_url(
                image_tag.get("src")
                or image_tag.get("data-src")
            )
            if image_tag
            else None
        )
        relative_date = find_relative_date_text(card)
        published_date = (
            normalize_date(relative_date)
            if relative_date
            else date_from_image_url(image_url)
        )
        date_source = "relative_text" if relative_date else "image_url"

        if cutoff and is_older_than_cutoff(published_date, cutoff):
            continue

        rows.append(
            {
                "title": clean_text(title_tag.get_text(" ", strip=True)),
                "url": urljoin(SITE_URL, href),
                "published_date": published_date,
                "relative_date": relative_date,
                "date_source": date_source,
                "page_num": page_num,
                "list_page_url": list_page_url,
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
                "image_url": image_url,
            }
        )

    return rows


def scrape_list(cutoff, max_pages=200):
    rows = []
    seen_urls = set()

    for page_num in range(1, max_pages + 1):
        url = page_url(page_num)
        print(f"Scraping Times Indonesia page {page_num}: {url}", flush=True)

        try:
            page_html = fetch_text(url)
        except Exception as error:
            print(f"Gagal buka Times Indonesia page {page_num}: {error}", flush=True)
            break

        page_rows = parse_list_html(
            page_html,
            cutoff=cutoff,
            page_num=page_num,
            list_page_url=url,
        )

        if not page_rows:
            break

        new_rows = []

        for row in page_rows:
            if row["url"] in seen_urls:
                continue

            seen_urls.add(row["url"])
            new_rows.append(row)

        if not new_rows:
            break

        rows.extend(new_rows)

        page_dates = [
            row["published_date"]
            for row in page_rows
            if row.get("published_date")
        ]

        if page_dates and all(
            is_older_than_cutoff(date_value, cutoff)
            for date_value in page_dates
        ):
            break

    return records_to_df(rows)


def scrape_list_api(cutoff, max_pages=200, include_older=False, limit=API_LIMIT):
    rows = []
    seen_urls = set()
    max_offsets = max_pages

    for page_index in range(max_offsets):
        offset = page_index * limit

        try:
            items = fetch_api_items(offset=offset, limit=limit)
        except Exception as error:
            print(
                f"Times Indonesia API failed offset={offset}: {error}",
                flush=True,
            )
            break

        if not items:
            print(
                f"Times Indonesia API empty offset={offset}; stop",
                flush=True,
            )
            break

        raw_new_rows = []
        new_rows = []

        for item_index, item in enumerate(items):
            row = api_item_to_row(
                item,
                offset=offset,
                index=item_index,
            )

            if not row.get("url") or row["url"] in seen_urls:
                continue

            seen_urls.add(row["url"])
            raw_new_rows.append(row)

            if (
                not include_older
                and is_older_than_cutoff(row.get("published_date"), cutoff)
            ):
                continue

            new_rows.append(row)

        rows.extend(new_rows)

        page_dates = [
            row["published_date"]
            for row in raw_new_rows
            if row.get("published_date")
        ]
        newest_date = max(page_dates) if page_dates else None
        oldest_date = min(page_dates) if page_dates else None

        print(
            f"Times Indonesia API page={page_index + 1:03d} "
            f"offset={offset} raw_new={len(raw_new_rows)} "
            f"new={len(new_rows)} total={len(rows)} "
            f"newest={newest_date} oldest={oldest_date}",
            flush=True,
        )

        for row in raw_new_rows:
            title = row.get("title") or ""
            short = title if len(title) <= 90 else title[:87] + "..."
            print(
                f"Times Indonesia list "
                f"page={row['page_num']:03d} "
                f"date={row.get('published_date')} "
                f"title={short}",
                flush=True,
            )

        if page_dates and all(
            is_older_than_cutoff(date_value, cutoff)
            for date_value in page_dates
        ):
            print(
                "Times Indonesia API reached cutoff from newly loaded rows",
                flush=True,
            )
            break

        if len(items) < limit:
            print(
                f"Times Indonesia API returned less than limit at offset={offset}; stop",
                flush=True,
            )
            break

        if not raw_new_rows:
            print(
                f"Times Indonesia API no new unique rows at offset={offset}; stop",
                flush=True,
            )
            break

    return records_to_df(rows)


async def debug_load_more_candidates(page):
    return await page.evaluate(
        """
        () => [...document.querySelectorAll('button,a,[role="button"],div,span')]
            .map((el) => ({
                tag: el.tagName.toLowerCase(),
                text: (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim(),
                visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                className: typeof el.className === 'string' ? el.className : '',
            }))
            .filter((item) => item.visible && item.text.includes('Berita Lainnya'))
            .sort((a, b) => a.text.length - b.text.length)
            .slice(0, 8)
        """
    )


async def click_load_more(page, click_num):
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(1500)

    candidates = await debug_load_more_candidates(page)
    print(
        f"Times Indonesia load-more candidates {click_num}: "
        f"{len(candidates)} {candidates}",
        flush=True,
    )

    for selector in [
        "button:has-text('Berita Lainnya')",
        "a:has-text('Berita Lainnya')",
        "[role='button']:has-text('Berita Lainnya')",
    ]:
        candidate = page.locator(selector)

        if await candidate.count() == 0:
            continue

        button = candidate.last
        await button.scroll_into_view_if_needed(timeout=5000)
        await page.wait_for_timeout(500)
        await button.click(timeout=15000, force=True)
        print(
            f"Times Indonesia clicked load-more via selector: {selector}",
            flush=True,
        )
        return True

    clicked = await page.evaluate(
        """
        () => {
            const candidates = [...document.querySelectorAll('button,a,[role="button"],div,span')]
                .filter((el) => {
                    const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                    const visible = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    return visible && text.includes('Berita Lainnya');
                })
                .sort((a, b) => {
                    const aText = (a.innerText || a.textContent || '').trim();
                    const bText = (b.innerText || b.textContent || '').trim();
                    return aText.length - bText.length;
                });

            const element = candidates[0];

            if (!element) {
                return null;
            }

            const clickable = element.closest('button,a,[role="button"]') || element;
            clickable.scrollIntoView({block: 'center'});
            clickable.click();

            return {
                tag: clickable.tagName.toLowerCase(),
                text: (clickable.innerText || clickable.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 120),
            };
        }
        """
    )

    if clicked:
        print(
            f"Times Indonesia clicked load-more via JS: {clicked}",
            flush=True,
        )
        return True

    return False


async def scrape_list_playwright(cutoff, max_pages=200, include_older=False):
    print("Times Indonesia: importing Playwright...", flush=True)
    from playwright.async_api import async_playwright

    rows = []
    seen_urls = set()
    unchanged_clicks = 0

    async with async_playwright() as playwright:
        print("Times Indonesia: launching Chromium...", flush=True)
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            print(f"Scraping Times Indonesia page 1: {BASE_URL}", flush=True)
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            for click_num in range(0, max_pages + 1):
                chunk_num = click_num + 1
                print(
                    f"Parsing Times Indonesia loaded chunk {chunk_num}",
                    flush=True,
                )
                await page.wait_for_timeout(2000)

                raw_page_rows = parse_list_html(
                    await page.content(),
                    cutoff=None,
                    page_num=chunk_num,
                    list_page_url=BASE_URL,
                )

                if not raw_page_rows:
                    break

                raw_new_rows = []
                new_rows = []

                for row in raw_page_rows:
                    if row["url"] in seen_urls:
                        continue

                    seen_urls.add(row["url"])
                    raw_new_rows.append(row)

                    if (
                        not include_older
                        and is_older_than_cutoff(row.get("published_date"), cutoff)
                    ):
                        continue

                    new_rows.append(row)

                rows.extend(new_rows)

                page_dates = [
                    row["published_date"]
                    for row in raw_page_rows
                    if row.get("published_date")
                ]
                new_dates = [
                    row["published_date"]
                    for row in raw_new_rows
                    if row.get("published_date")
                ]
                oldest_date = min(page_dates) if page_dates else None
                newest_date = max(page_dates) if page_dates else None
                oldest_new_date = min(new_dates) if new_dates else None
                newest_new_date = max(new_dates) if new_dates else None

                print(
                    f"Times Indonesia chunk {chunk_num}: "
                    f"cards={len(raw_page_rows)} raw_new={len(raw_new_rows)} "
                    f"new={len(new_rows)} total={len(rows)} "
                    f"newest={newest_date} oldest={oldest_date} "
                    f"newest_new={newest_new_date} oldest_new={oldest_new_date}",
                    flush=True,
                )

                if new_dates and all(
                    is_older_than_cutoff(date_value, cutoff)
                    for date_value in new_dates
                ):
                    print(
                        "Times Indonesia reached cutoff from newly loaded rows",
                        flush=True,
                    )
                    break

                if click_num >= max_pages:
                    break

                previous_card_count = len(raw_page_rows)

                try:
                    print(
                        f"Times Indonesia click Berita Lainnya {click_num + 1}: "
                        f"before_count={previous_card_count}",
                        flush=True,
                    )

                    if not await click_load_more(page, click_num + 1):
                        print("Times Indonesia load-more button not found", flush=True)
                        break

                    grew = False

                    for wait_index in range(1, 21):
                        await page.wait_for_timeout(1000)
                        current_rows = parse_list_html(
                            await page.content(),
                            cutoff=None,
                            page_num=chunk_num,
                            list_page_url=BASE_URL,
                        )
                        current_count = len(current_rows)
                        print(
                            f"Times Indonesia wait after click "
                            f"{click_num + 1}.{wait_index}: "
                            f"after_count={current_count}",
                            flush=True,
                        )

                        if current_count > previous_card_count:
                            grew = True
                            break

                    if not grew:
                        unchanged_clicks += 1
                        print(
                            f"Times Indonesia load-more did not add rows "
                            f"(unchanged_clicks={unchanged_clicks})",
                            flush=True,
                        )

                        if unchanged_clicks >= 2:
                            break
                    else:
                        unchanged_clicks = 0
                except Exception as error:
                    print(
                        f"Times Indonesia load-more stopped: {error}",
                        flush=True,
                    )
                    break
        finally:
            await browser.close()

    return records_to_df(rows)


def scrape_list_auto(cutoff, max_pages=200, include_older=False):
    try:
        return scrape_list_api(
            cutoff,
            max_pages=max_pages,
            include_older=include_older,
        )
    except Exception as error:
        print(
            f"Times Indonesia API list failed, fallback Playwright: {error}",
            flush=True,
        )

    try:
        df = asyncio.run(
            scrape_list_playwright(
                cutoff,
                max_pages=max_pages,
                include_older=include_older,
            )
        )
    except Exception as error:
        print(
            f"Times Indonesia Playwright list failed, fallback static: {error}",
            flush=True,
        )
        df = scrape_list(cutoff, max_pages=max_pages)

    if not df.empty:
        return df

    return df


def article_html(page_html):
    match = re.search(r"<article\b.*?</article>", page_html, re.DOTALL)
    return match.group(0) if match else page_html


def extract_content_from_html(page_html):
    article = article_html(page_html)
    paragraphs = []

    for paragraph_html in re.findall(
        r'<p class="text-foreground[^"]*"[^>]*>(.*?)</p>',
        article,
        re.DOTALL,
    ):
        if "whatsapp.com" in paragraph_html.lower():
            continue

        paragraph = strip_tags(paragraph_html)

        if not paragraph:
            continue

        lower = paragraph.lower()

        if lower.startswith("simak breaking news"):
            continue

        paragraphs.append(paragraph)

    if not paragraphs:
        for paragraph_html in re.findall(r"<p\b[^>]*>(.*?)</p>", article, re.DOTALL):
            if "whatsapp.com" in paragraph_html.lower():
                continue

            paragraph = strip_tags(paragraph_html)

            if paragraph:
                paragraphs.append(paragraph)

    return clean_article_text("\n".join(paragraphs))


def extract_article(row):
    page_html = fetch_text(row["url"])
    article = article_html(page_html)
    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", article, re.DOTALL)
    date_text = None
    author = None
    article_text = strip_tags(article)
    date_match = re.search(
        r"\b\d{1,2}\s+"
        r"(?:Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|"
        r"September|Oktober|November|Desember)\s+"
        r"\d{4},\s+\d{1,2}:\d{2}\s+WIB\b",
        article_text or "",
        re.IGNORECASE,
    )

    if date_match:
        date_text = date_match.group(0)

    author_match = re.search(
        r"Tim Redaksi\s+(.*?)\s+-\s+Editor",
        article_text or "",
    )

    if author_match:
        author = clean_text(author_match.group(1))

    return {
        "title": (
            strip_tags(title_match.group(1))
            if title_match
            else row["title"]
        ),
        "published_date": normalize_date(date_text or row.get("published_date")),
        "scraped_at": scraped_at(),
        "author": author or row.get("author"),
        "category": None,
        "content": extract_content_from_html(page_html),
        "url": row["url"],
        "source": SOURCE,
        "image_url": row.get("image_url"),
        "excerpt": row.get("excerpt"),
        "source_category": row.get("source_category"),
        "relative_date": row.get("relative_date"),
    }


def scrape(max_pages=200):
    cutoff = cutoff_date()
    urls_df = scrape_list_auto(cutoff, max_pages=max_pages)
    articles = []

    for index, row in urls_df.iterrows():
        try:
            article = extract_article(row)
        except Exception as error:
            print(
                f"[{index + 1}/{len(urls_df)}] Times Indonesia failed: {error}",
                flush=True,
            )
            continue

        if is_older_than_cutoff(article["published_date"], cutoff):
            continue

        if not article.get("content"):
            print(f"Times Indonesia content kosong, skip: {row['url']}", flush=True)
            continue

        articles.append(article)
        print(f"[{len(articles)}] {article['title']}", flush=True)

    df = records_to_df(articles)
    write_articles_csv(df, OUTPUT_PATH)
    print(f"\nSaved {len(df)} Times Indonesia articles", flush=True)
    return df


if __name__ == "__main__":
    print(scrape().head())
