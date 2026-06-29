from datetime import datetime, timezone

from utils.supabase_loader import upload_news


TABLE_NAME = "raw_news_articles_test"


def main():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    url = f"https://example.com/test-insert-manual-{timestamp}"

    records = [
        {
            "source": "test_manual",
            "title": "Test insert manual dari Python",
            "url": url,
            "published_date": "2026-06-29",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "author": None,
            "category": None,
            "content": "Ini hanya test insert satu row ke Supabase.",
            "text": (
                "Test insert manual dari Python "
                "Ini hanya test insert satu row ke Supabase."
            ),
            "all_kecamatan": [],
            "primary_kecamatan": None,
            "latitude": None,
            "longitude": None,
            "sentiment": "neutral",
            "sentiment_score": 1.0,
        }
    ]

    print(f"trying insert: {TABLE_NAME} | {url}", flush=True)
    upload_news(records, TABLE_NAME)
    print(f"insert test ok: {TABLE_NAME} | {url}")


if __name__ == "__main__":
    main()
