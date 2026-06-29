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
    table_name
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
        print(f"Supabase upload skipped: {table_name} has 0 records", flush=True)
        return

    print(
        f"Supabase upload start: table={table_name}, records={len(records)}",
        flush=True,
    )

    response = requests.post(
        f"{supabase_url}/rest/v1/{table_name}",
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        params={
            "on_conflict": "url",
        },
        json=records,
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            "Supabase upload failed: "
            f"{response.status_code} {response.reason} | {response.text}"
        )

    print(
        f"Supabase upload success: table={table_name}, records={len(records)}, "
        f"status={response.status_code}",
        flush=True,
    )


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
