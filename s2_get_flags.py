"""
s2_get_flags.py
Reads FINAL_BAR_CHART_RACE.csv and country_codes.json (both produced by s1),
then downloads country flag images from flagcdn.com into the flags/ folder.

Filenames match the country name column in the CSV so s4 can load them
without any extra mapping (e.g. "United States.png").

Run: python s2_get_flags.py
Requires: pip install requests pandas
"""

import os
import re
import json
import time
import requests
import urllib3
import pandas as pd

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Config ────────────────────────────────────────────────────────────────────
FLAG_CDN       = "https://flagcdn.com/w320/{iso2}.png"
OUTPUT_FOLDER  = "flags"
TOP_N_TO_FETCH = 60      # Fetch top 60 by final-year value -covers any screen size

# ── Load CSV columns (country names) ─────────────────────────────────────────
print("Reading FINAL_BAR_CHART_RACE.csv...")
df = pd.read_csv('FINAL_BAR_CHART_RACE.csv', index_col='Year')
print(f"  {len(df.columns)} countries in the dataset.")

# Find top N countries by their final-year value (most relevant for the video)
top_countries = (
    df.iloc[-1]
    .sort_values(ascending=False)
    .dropna()
    .head(TOP_N_TO_FETCH)
    .index.tolist()
)
print(f"  Downloading flags for top {len(top_countries)} countries.")

# ── Load ISO2 code map ────────────────────────────────────────────────────────
with open('country_codes.json', 'r', encoding='utf-8') as f:
    name_to_iso2 = json.load(f)

# ── Helper: make a safe filename from a country name ─────────────────────────
def safe_filename(name: str) -> str:
    """
    Strips characters that are invalid in Windows filenames.
    The renderer will call this same function when loading flags, so the
    mapping is consistent on both sides.
    """
    return re.sub(r'[<>:"/\\|?*]', '_', name)

# ── Download ──────────────────────────────────────────────────────────────────
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
headers = {"User-Agent": "WorldBankRacePipeline/1.0"}

downloaded, skipped, failed = 0, 0, []

for country in top_countries:
    iso2 = name_to_iso2.get(country, '').strip().lower()
    if not iso2:
        print(f"  !  No ISO2 code for: {country}")
        failed.append(country)
        continue

    fname     = safe_filename(country) + ".png"
    save_path = os.path.join(OUTPUT_FOLDER, fname)

    if os.path.exists(save_path):
        print(f"  OK  (cached) {country}")
        skipped += 1
        continue

    url = FLAG_CDN.format(iso2=iso2)
    try:
        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        if resp.status_code == 200:
            with open(save_path, 'wb') as fh:
                fh.write(resp.content)
            print(f"  DL  {country}  [{iso2}]")
            downloaded += 1
        else:
            print(f"  FAIL  HTTP {resp.status_code} -{country}  [{iso2}]")
            failed.append(country)
    except Exception as exc:
        print(f"  FAIL  Error -{country}: {exc}")
        failed.append(country)

    time.sleep(0.25)   # polite pacing -flagcdn.com is a free service

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\nDone.  {downloaded} downloaded, {skipped} already cached, {len(failed)} failed.")
if failed:
    print(f"Missing flags (you may need to add these manually):")
    for name in failed:
        print(f"  {name}")
