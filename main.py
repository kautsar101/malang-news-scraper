import pandas as pd

from scrapers.beritamalang import scrape as scrape_beritamalang
from scrapers.kominfomalangkab import scrape as scrape_kominfomalangkab
from scrapers.malangposco import scrape as scrape_malangposco
from scrapers.malangtimes import scrape as scrape_malangtimes
from scrapers.nusadaily import scrape as scrape_nusadaily
from scrapers.radarmalang import scrape as scrape_radarmalang
from scrapers.seputarmalang import scrape as scrape_seputarmalang

from utils.normalize import normalize_news
from utils.tagging import tag_kecamatan
from utils.sentiment import predict_sentiment
from utils.supabase_loader import upload_news


SCRAPERS = [
    {
        "name": "beritamalang_media",
        "scraper": scrape_beritamalang,
    },
    {
        "name": "kominfo_malangkab",
        "scraper": scrape_kominfomalangkab,
    },
    {
        "name": "malangposco",
        "scraper": scrape_malangposco,
    },
    {
        "name": "malangtimes",
        "scraper": scrape_malangtimes,
    },
    {
        "name": "nusadaily",
        "scraper": scrape_nusadaily,
    },
    {
        "name": "radar_malang",
        "scraper": scrape_radarmalang,
    },
    {
        "name": "seputar_malang",
        "scraper": scrape_seputarmalang,
    },
]


TABLE_NAME = "raw_news_articles"


def process(df, source):

    df = normalize_news(
        df,
        source
    )

    df[
        [
            "all_kecamatan",
            "primary_kecamatan",
            "latitude",
            "longitude"
        ]
    ] = (
        df["content"]
        .apply(tag_kecamatan)
        .apply(pd.Series)
    )

    df[
        [
            "sentiment",
            "sentiment_score"
        ]
    ] = (
        df.apply(
            lambda row: predict_sentiment(
                row["title"],
                row["content"]
            ),
            axis=1
        )
        .apply(pd.Series)
    )

    return df


def main():

    for item in SCRAPERS:

        source = item["name"]

        scraper = item["scraper"]

        print(f"\nRunning {source}...")

        try:

            df = scraper()

            if df.empty:

                print("No data found.")
                continue

            df = process(
                df,
                source
            )

            df = df[
                df["content"]
                .fillna("")
                .astype(str)
                .str.strip()
                .ne("")
            ]

            if df.empty:

                print("No valid article content found.")
                continue

            upload_news(
                df,
                TABLE_NAME
            )

            print(
                f"{source}: uploaded {len(df)} articles"
            )

        except Exception as error:

            print(
                f"{source} failed: {error}"
            )


if __name__ == "__main__":

    main()
