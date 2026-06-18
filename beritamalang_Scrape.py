#!/usr/bin/env python
# coding: utf-8

# # scrape judul dan url
# 

# In[2]:
from datetime import datetime, timezone

import requests
import pandas as pd
from bs4 import BeautifulSoup

def scrape_berita_malang():

    urls = [
        "https://beritamalang.media/",
        "https://beritamalang.media/page/2/",
        "https://beritamalang.media/page/3/"
    ]

    data = []

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    for page_url in urls:

        print(f"scraping: {page_url}")

        html = requests.get(
            page_url,
            headers=headers,
            timeout=30
        ).text

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        for article in soup.select("article.post-main"):

            title_tag = article.select_one(
                "h2.post-main-title a"
            )

            date_tag = article.select_one(
                ".post-main-datapost span"
            )

            category_tag = article.select_one(
                ".post-main-category"
            )

            if not title_tag:
                continue

            data.append({
                "title": title_tag.get_text(strip=True),
                "url": title_tag["href"],
                "published_date": (
                    date_tag.get_text(strip=True)
                    if date_tag else None
                ),
                "category": (
                    category_tag.get_text(
                        ",",
                        strip=True
                    )
                    if category_tag else None
                ),
                "source": "beritamalang_media"
            })

    df = (
        pd.DataFrame(data)
        .drop_duplicates(subset=["url"])
        .reset_index(drop=True)
    )

    df.to_csv(
        "beritamalang_media.csv",
        index=False
    )

    print(
        f"saved {len(df)} articles"
    )

    return df

df_berita_malang = scrape_berita_malang()

df_berita_malang.head()


# # scrape isi url 

# In[11]:


import requests
import pandas as pd
from bs4 import BeautifulSoup

df = pd.read_csv("beritamalang_media.csv")

articles = []

for i, row in df.iterrows():

    try:

        html = requests.get(
            row["url"],
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30
        ).text

        soup = BeautifulSoup(html, "html.parser")

        text = soup.get_text(
            "\n",
            strip=True
        )

        start = text.find("Oleh Penulis")
        end = text.find("Share:")

        content = None

        if start != -1 and end != -1:

            content = text[start:end]

            content = content.replace(
                "Oleh Penulis\nComment: 0",
                ""
            ).strip()

        articles.append({
            "title": row["title"],
            "published_date": row["published_date"],
            "category": row["category"],
            "content": content,
            "url": row["url"],
            "source": "beritamalang_media"
        })

        print(f"[{i+1}/{len(df)}] success")

    except Exception as e:

        print(f"[{i+1}/{len(df)}] failed: {e}")

result = pd.DataFrame(articles)

result.to_csv(
    "beritamalang_media_articles.csv",
    index=False
)

print(result.head())


# In[ ]:

from supabase import create_client
import os
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

records = result.to_dict("records")

supabase.table(
    "news_articles"
).upsert(
    records,
    on_conflict="url"
).execute()

print(f"uploaded {len(records)} records to supabase")


