from supabase import create_client
from dotenv import load_dotenv

import os
import numpy as np

load_dotenv()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

def upload_news(
    df,
    table_name
):

    df = df.replace(
        {
            np.nan: None
        }
    )

    records = df.to_dict(
        "records"
    )

    supabase.table(
        table_name
    ).upsert(
        records,
        on_conflict="url"
    ).execute()