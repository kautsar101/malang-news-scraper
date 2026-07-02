import os
import math
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATHS = [
    PROJECT_ROOT / ".env",
    PROJECT_ROOT.parent / ".env",
]


def load_project_env():
    for env_path in ENV_PATHS:
        if not env_path.exists():
            continue

        for line in env_path.read_text(errors="replace").splitlines():
            stripped = line.strip()

            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue

            key, value = stripped.split("=", 1)
            key = key.strip().removeprefix("export ").strip()
            value = value.strip().strip("\"'")

            if key and key not in os.environ:
                os.environ[key] = value

        return env_path

    return None


def get_supabase_credentials():
    env_path = load_project_env()
    print(f"Supabase env path: {env_path}", flush=True)

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "SUPABASE_URL dan SUPABASE_KEY belum tersedia. "
            "Tambahkan ke file .env di root project atau export di terminal."
        )

    return supabase_url.rstrip("/"), supabase_key


def upload_news(
    data,
    table_name,
    existing_urls=None,
):
    supabase_url, supabase_key = get_supabase_credentials()

    if hasattr(data, "to_dict"):
        records = data.to_dict("records")
    else:
        records = list(data)

    records = [
        clean_record(record)
        for record in records
    ]
    records = dedupe_records_by_url(records)

    if not records:
        print(f"Supabase upload skipped: {table_name} has 0 records", flush=True)
        return 0

    if existing_urls is None:
        existing_urls = fetch_existing_urls(table_name, supabase_url, supabase_key)
    else:
        existing_urls = {
            normalize_url(url)
            for url in existing_urls
            if normalize_url(url)
        }
        print(
            f"Supabase upload using preloaded existing URLs: "
            f"table={table_name}, urls={len(existing_urls)}",
            flush=True,
        )
    new_records = []
    skipped_existing = 0
    skipped_missing_url = 0

    for record in records:
        url = normalize_url(record.get("url"))

        if not url:
            skipped_missing_url += 1
            continue

        if url in existing_urls:
            skipped_existing += 1
            continue

        record["url"] = url
        new_records.append(record)

    print(
        f"Supabase upload dedupe: table={table_name}, incoming={len(records)}, "
        f"existing_skipped={skipped_existing}, "
        f"missing_url_skipped={skipped_missing_url}, new={len(new_records)}",
        flush=True,
    )

    if not new_records:
        print(
            f"Supabase upload skipped: table={table_name}, no new URLs",
            flush=True,
        )
        return 0

    print(
        f"Supabase upload start: table={table_name}, records={len(new_records)}",
        flush=True,
    )

    response = requests.post(
        f"{supabase_url}/rest/v1/{table_name}",
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=ignore-duplicates,return=minimal",
        },
        params={
            "on_conflict": "url",
        },
        json=new_records,
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            "Supabase upload failed: "
            f"{response.status_code} {response.reason} | {response.text}"
        )

    print(
        f"Supabase upload success: table={table_name}, records={len(new_records)}, "
        f"status={response.status_code}",
        flush=True,
    )

    return len(new_records)


def get_existing_urls(table_name):
    supabase_url, supabase_key = get_supabase_credentials()
    return fetch_existing_urls(table_name, supabase_url, supabase_key)


def fetch_existing_urls(
    table_name,
    supabase_url,
    supabase_key,
    page_size=1000,
):
    existing_urls = set()
    start = 0

    print(
        f"Supabase existing URL fetch start: table={table_name}",
        flush=True,
    )

    while True:
        end = start + page_size - 1
        response = requests.get(
            f"{supabase_url}/rest/v1/{table_name}",
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
                "Range-Unit": "items",
                "Range": f"{start}-{end}",
            },
            params={
                "select": "url",
                "url": "not.is.null",
            },
            timeout=60,
        )

        if not response.ok:
            raise RuntimeError(
                "Supabase existing URL fetch failed: "
                f"{response.status_code} {response.reason} | {response.text}"
            )

        rows = response.json()

        for row in rows:
            url = normalize_url(row.get("url"))

            if url:
                existing_urls.add(url)

        print(
            f"Supabase existing URL fetch page: table={table_name}, "
            f"range={start}-{end}, rows={len(rows)}, total_seen={len(existing_urls)}",
            flush=True,
        )

        if len(rows) < page_size:
            break

        start += page_size

    print(
        f"Supabase existing URL fetch success: table={table_name}, "
        f"urls={len(existing_urls)}",
        flush=True,
    )

    return existing_urls


def dedupe_records_by_url(records):
    deduped = []
    seen_urls = set()
    skipped_duplicate_input = 0

    for record in records:
        url = normalize_url(record.get("url"))

        if url and url in seen_urls:
            skipped_duplicate_input += 1
            continue

        if url:
            record["url"] = url
            seen_urls.add(url)

        deduped.append(record)

    if skipped_duplicate_input:
        print(
            f"Supabase upload input dedupe: skipped_duplicate_input="
            f"{skipped_duplicate_input}",
            flush=True,
        )

    return deduped


def normalize_url(value):
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def update_news(
    data,
    table_name,
    match_column="url",
):
    supabase_url, supabase_key = get_supabase_credentials()

    if hasattr(data, "to_dict"):
        records = data.to_dict("records")
    else:
        records = list(data)

    records = [
        clean_record(record)
        for record in records
    ]

    if not records:
        print(f"Supabase update skipped: {table_name} has 0 records", flush=True)
        return

    print(
        f"Supabase update start: table={table_name}, records={len(records)}",
        flush=True,
    )

    for index, record in enumerate(records, 1):
        match_value = record.get(match_column)

        if not match_value:
            print(
                f"Supabase update skip [{index}/{len(records)}]: "
                f"missing {match_column}",
                flush=True,
            )
            continue

        payload = {
            key: value
            for key, value in record.items()
            if key != match_column
        }

        response = requests.patch(
            f"{supabase_url}/rest/v1/{table_name}",
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            params={
                match_column: f"eq.{match_value}",
            },
            json=payload,
            timeout=60,
        )

        if not response.ok:
            raise RuntimeError(
                "Supabase update failed: "
                f"{response.status_code} {response.reason} | {response.text}"
            )

        print(
            f"Supabase update [{index}/{len(records)}] ok: {match_value}",
            flush=True,
        )


def fetch_news(
    table_name,
    columns=None,
    only_pending=False,
    limit=None,
):
    supabase_url, supabase_key = get_supabase_credentials()
    selected_columns = columns or [
        "source",
        "title",
        "url",
        "published_date",
        "content",
        "primary_kecamatan",
        "sentiment",
        "sentiment_score",
    ]

    params = {
        "select": ",".join(selected_columns),
    }

    if only_pending:
        params["or"] = "(sentiment.is.null,sentiment.eq.pending)"
        params["primary_kecamatan"] = "not.is.null"

    if limit is not None:
        params["limit"] = str(limit)

    print(
        f"Supabase fetch start: table={table_name}, "
        f"only_pending={only_pending}, limit={limit}",
        flush=True,
    )

    response = requests.get(
        f"{supabase_url}/rest/v1/{table_name}",
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
        },
        params=params,
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            "Supabase fetch failed: "
            f"{response.status_code} {response.reason} | {response.text}"
        )

    records = response.json()
    print(
        f"Supabase fetch success: table={table_name}, records={len(records)}",
        flush=True,
    )

    return records


def clean_record(record):
    return {
        key: clean_value(value)
        for key, value in record.items()
    }


def clean_value(value):
    if isinstance(value, float) and math.isnan(value):
        return None

    if isinstance(value, dict):
        return {
            key: clean_value(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            clean_value(item)
            for item in value
        ]

    return value
