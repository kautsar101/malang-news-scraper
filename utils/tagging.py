import re
import pandas as pd

KECAMATAN = {
    "Ampelgading": (-8.2583, 112.7667),
    "Bantur": (-8.3167, 112.5167),
    "Bululawang": (-8.1333, 112.6833),
    "Dampit": (-8.2333, 112.7833),
    "Dau": (-7.9833, 112.5667),
    "Donomulyo": (-8.2833, 112.4167),
    "Gedangan": (-8.3333, 112.6667),
    "Gondanglegi": (-8.1667, 112.6333),
    "Jabung": (-7.9667, 112.7167),
    "Kalipare": (-8.2167, 112.4667),
    "Karangploso": (-7.9333, 112.6167),
    "Kasembon": (-7.8167, 112.3667),
    "Kepanjen": (-8.1333, 112.5667),
    "Kromengan": (-8.1000, 112.5167),
    "Lawang": (-7.8333, 112.6833),
    "Ngajum": (-8.0833, 112.5000),
    "Ngantang": (-7.8833, 112.3833),
    "Pagak": (-8.2000, 112.5167),
    "Pagelaran": (-8.1500, 112.5833),
    "Pakis": (-7.9833, 112.7000),
    "Pakisaji": (-8.1000, 112.6000),
    "Poncokusumo": (-8.0167, 112.7667),
    "Pujon": (-7.9000, 112.4167),
    "Singosari": (-7.9000, 112.6667),
    "Sumbermanjing Wetan": (-8.3667, 112.6833),
    "Sumberpucung": (-8.1667, 112.5333),
    "Tajinan": (-8.1000, 112.6667),
    "Tirtoyudo": (-8.2833, 112.7167),
    "Tumpang": (-8.0000, 112.7333),
    "Turen": (-8.1667, 112.6833),
    "Wagir": (-8.0333, 112.5500),
    "Wajak": (-8.0833, 112.7167),
    "Wonosari": (-8.1500, 112.5167),
}

def tag_kecamatan(text):

    if pd.isna(text):

        return None, None, None, None

    found = []

    lower = text.lower()

    for kec in KECAMATAN:

        if re.search(
            rf"\b{kec.lower()}\b",
            lower
        ):
            found.append(kec)

    primary = found[0] if found else None

    lat = None
    lon = None

    if primary:

        lat, lon = KECAMATAN[primary]

    return (
        "|".join(found),
        primary,
        lat,
        lon
    )