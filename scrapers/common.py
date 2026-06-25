import re
from datetime import datetime, timezone

import requests
import pandas as pd
from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta


HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

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
    return datetime.now() - relativedelta(months=months)


def scraped_at():
    return datetime.now(timezone.utc).isoformat()


def fetch_html(url, verify=True):
    return BeautifulSoup(
        fetch_text(url, verify=verify),
        "html.parser",
    )


def fetch_text(url, verify=True):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
        verify=verify,
    )
    response.raise_for_status()

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

    return "\n".join(cleaned) if cleaned else None


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

    for line in lines:
        normalized = re.sub(r"\s+", " ", line).strip()
        lower = normalized.lower()

        if skip_next:
            skip_next -= 1
            continue

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

    return "\n".join(cleaned) if cleaned else None


def parse_date(value):
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    normalized = re.sub(r"\s+", " ", text)

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
