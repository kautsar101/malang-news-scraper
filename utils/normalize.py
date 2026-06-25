import pandas as pd
from datetime import datetime, timezone

from scrapers.common import clean_article_text


def normalize_category_from_url(url):
    if pd.isna(url):
        return None

    if "/pendidikan" in str(url).lower():
        return "pendidikan"

    return None


def normalize_news(
    df,
    source
):

    cols = [
        "title",
        "url",
        "published_date",
        "scraped_at",
        "content"
    ]

    for col in cols:

        if col not in df.columns:
            df[col] = None

    df["scraped_at"] = df["scraped_at"].fillna(
        datetime.now(timezone.utc).isoformat()
    )

    df["content"] = df["content"].apply(clean_article_text)

    if "author" not in df.columns:
        df["author"] = None

    if "category" not in df.columns:
        df["category"] = None

    df["category"] = df["url"].apply(normalize_category_from_url)

    df["source"] = source
    df["text"] = (
        df["title"].fillna("").astype(str)
        + " "
        + df["content"].fillna("").astype(str)
    ).str.strip()

    return df[
        [
            "source",
            "title",
            "url",
            "published_date",
            "scraped_at",
            "author",
            "category",
            "content",
            "text"
        ]
    ]
