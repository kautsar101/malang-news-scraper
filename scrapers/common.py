import re
from calendar import monthrange
from datetime import datetime, timedelta, timezone


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

RELATIVE_DATE_PATTERN = re.compile(
    r"\b(\d+)\s+(menit|jam|hari|minggu|bulan|tahun)\s+(?:yang\s+)?lalu\b",
    re.IGNORECASE,
)

ARTICLE_NOISE_SELECTORS = [
    "script",
    "style",
    "iframe",
    "noscript",
    "figure",
    "figcaption",
    "img",
    ".google-auto-placed",
    ".adsbygoogle",
    ".google-aiuf",
    ".goog-rentries",
    ".goog-rtopics",
    ".google-anno-skip",
    "[id^='aswift_']",
    "[id*='ads']",
    "[class*='ads']",
    "[class*='advert']",
    ".ray-inline-related",
    ".ray-inline-related-posts",
    ".baca-juga",
    ".readmore",
    ".addtoany_share_save_container",
    ".td-a-ad",
    ".td-adspot-title",
    ".post-share-buttons",
    ".btn-share",
    ".section-related-posts",
    ".sharedaddy",
    ".wp-caption",
    ".jeg_share_top_container",
    ".jeg_share_bottom_container",
    ".jeg_share_button",
    ".jeg_share_float_container",
    ".jnews_related_post_container",
    ".jeg_ad",
]

INDONESIAN_MONTHS = {
    "januari": "January",
    "februari": "February",
    "maret": "March",
    "april": "April",
    "mei": "May",
    "juni": "June",
    "juli": "July",
    "agustus": "August",
    "september": "September",
    "oktober": "October",
    "november": "November",
    "desember": "December",
}


def cutoff_date(months=4):
    return shift_datetime(datetime.now(), months=-months)


def shift_datetime(value, years=0, months=0, weeks=0, days=0, hours=0, minutes=0):
    shifted = value + timedelta(
        weeks=weeks,
        days=days,
        hours=hours,
        minutes=minutes,
    )

    month_index = shifted.month - 1 + months + (years * 12)
    year = shifted.year + month_index // 12
    month = month_index % 12 + 1
    day = min(shifted.day, monthrange(year, month)[1])

    return shifted.replace(year=year, month=month, day=day)


def scraped_at():
    return datetime.now(timezone.utc).isoformat()


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
        return shift_datetime(now, minutes=-amount)

    if unit == "jam":
        return shift_datetime(now, hours=-amount)

    if unit == "hari":
        return shift_datetime(now, days=-amount)

    if unit == "minggu":
        return shift_datetime(now, weeks=-amount)

    if unit == "bulan":
        return shift_datetime(now, months=-amount)

    if unit == "tahun":
        return shift_datetime(now, years=-amount)

    return None


def fetch_html(url, verify=True, timeout=15):
    from bs4 import BeautifulSoup

    return BeautifulSoup(
        fetch_text(url, verify=verify, timeout=timeout),
        "html.parser",
    )


def fetch_text(url, verify=True, timeout=15):
    print(f"HTTP GET start: {url}", flush=True)

    import requests

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=timeout,
        verify=verify,
    )
    response.raise_for_status()
    print(
        f"HTTP GET ok: {url} | status={response.status_code} | "
        f"bytes={len(response.text)}",
        flush=True,
    )

    return response.text


def clean_lines(text):
    if not text:
        return None

    lines = [
        line.strip()
        for line in str(text).split("\n")
        if line.strip()
    ]

    seen = set()
    cleaned = []

    for line in lines:
        if line in seen:
            continue

        seen.add(line)
        cleaned.append(line)

    if not cleaned:
        return None

    result = " ".join(cleaned)
    result = re.sub(r"\s+([,.;:!?])", r"\1", result)
    result = re.sub(r"([\(\{\[])\s+", r"\1", result)

    return result


def clean_article_soup(container):
    if not container:
        return None

    for selector in ARTICLE_NOISE_SELECTORS:
        for tag in container.select(selector):
            tag.decompose()

    for tag in list(container.find_all(True)):
        text = tag.get_text(" ", strip=True)
        lower = text.lower()

        if not text:
            continue

        if re.match(r"^(baca|simak)\s+juga\s*:?", lower):
            tag.decompose()
            continue

        if lower in {
            "temukan lebih banyak",
            "berita hari ini",
            "artikel terkait",
            "related posts",
            "bagikan:",
            "bagikan",
            "share",
            "share:",
            "-advertisement-",
            "advertisement",
            "iklan",
        }:
            tag.decompose()

    return container


def clean_article_text(text):
    if not text:
        return None

    lines = [
        line.strip()
        for line in str(text).replace("\r", "\n").split("\n")
        if line.strip()
    ]

    cleaned = []
    seen = set()
    skip_next = 0
    skip_table_of_contents = False

    for line in lines:
        normalized = re.sub(r"\s+", " ", line).strip()
        normalized = re.sub(r"\s+([,.;:!?])", r"\1", normalized)
        normalized = re.sub(r"([\(\{\[])\s+", r"\1", normalized)
        lower = normalized.lower()

        if skip_next:
            skip_next -= 1
            continue

        if skip_table_of_contents:
            if normalized == "-":
                skip_table_of_contents = False
                continue

            if len(normalized) <= 80 and not re.search(r"[.!?]$", normalized):
                continue

            skip_table_of_contents = False

        if re.match(r"^baca\s+juga\s*:?\s*$", lower):
            skip_next = 1
            continue

        if re.match(r"^baca\s+juga\s*:", lower):
            continue

        if re.match(r"^simak\s+juga\s*:?\s*$", lower):
            skip_next = 1
            continue

        if re.match(r"^simak\s+juga\s*:", lower):
            continue

        if lower == "temukan lebih banyak":
            skip_next = 3
            continue

        if lower == "daftar isi":
            skip_table_of_contents = True
            continue

        if lower in {
            "berita hari ini",
            "artikel terkait",
            "rekomendasi",
            "recommended",
            "advertisement",
            "iklan",
            "bagikan",
            "share",
            "share:",
            "komentar",
            "tags",
        }:
            continue

        if re.match(r"^(ikuti|follow)\s+.+", lower):
            continue

        if re.match(r"^(halaman|page)\s+\d+", lower):
            continue

        if lower in seen:
            continue

        seen.add(lower)
        cleaned.append(normalized)

    if not cleaned:
        return None

    result = " ".join(cleaned)
    result = re.sub(r"\s+([,.;:!?])", r"\1", result)
    result = re.sub(r"([\(\{\[])\s+", r"\1", result)

    return result


def parse_date(value):
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    relative_date = parse_relative_date(text)

    if relative_date:
        return relative_date.replace(tzinfo=None)

    normalized = re.sub(r"\s+", " ", text)
    normalized = re.sub(r"^[A-Za-zÀ-ž]+,\s*", "", normalized)
    normalized = re.sub(r"\bWIB\b", "", normalized, flags=re.IGNORECASE).strip()

    for indonesian_month, english_month in INDONESIAN_MONTHS.items():
        normalized = re.sub(
            rf"\b{indonesian_month}\b",
            english_month,
            normalized,
            flags=re.IGNORECASE,
        )

    patterns = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B %Y",
        "%d %B %Y %H:%M",
        "%d %b %Y %H:%M",
        "%d %B %y, %H:%M",
        "%d %B %Y, %H:%M",
        "%d - %b - %Y, %H:%M",
        "%d - %B - %Y, %H:%M",
    ]

    for pattern in patterns:
        try:
            return datetime.strptime(normalized, pattern).replace(tzinfo=None)
        except ValueError:
            continue

    match = re.search(r"(\d{8})/\d{6}", normalized)

    if match:
        try:
            return datetime.strptime(match.group(1), "%Y%m%d")
        except ValueError:
            return None

    return None


def normalize_date(value):
    parsed_date = parse_date(value)

    if parsed_date:
        return parsed_date.date().isoformat()

    return value


def is_older_than_cutoff(value, cutoff):
    parsed_date = parse_date(value)

    return bool(parsed_date and parsed_date < cutoff)


def records_to_df(records, subset="url"):
    import pandas as pd

    df = pd.DataFrame(records)

    if df.empty:
        return df

    if subset in df.columns:
        df = df.drop_duplicates(subset=subset)
    else:
        df = df.drop_duplicates()

    return df.reset_index(drop=True)


def write_articles_csv(df, path):
    columns = [
        "title",
        "published_date",
        "scraped_at",
        "author",
        "category",
        "content",
        "url",
        "source",
    ]

    for col in columns:
        if col not in df.columns:
            df[col] = None

    extra_columns = [
        col
        for col in df.columns
        if col not in columns
    ]

    df[columns + extra_columns].to_csv(path, index=False)
