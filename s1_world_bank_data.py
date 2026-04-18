"""
s1_world_bank_data.py
Reads config.json, fetches the requested World Bank indicator for every
country, and outputs:
  - FINAL_BAR_CHART_RACE.csv  (Year x Country, raw annual values)
  - country_codes.json        (country name => 2-letter ISO code for s2)

Run: python s1_world_bank_data.py
Requires: pip install wbgapi pycountry pandas
"""

import json
import sys
import warnings
import pandas as pd
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    import wbgapi as wb
except ImportError:
    sys.exit("Missing dependency. Run: pip install wbgapi")

# Patch wbgapi's underlying requests session to skip SSL verification.
# Required on some networks/Python versions where api.worldbank.org gives
# SSLEOFError (TLS handshake terminated unexpectedly).
import requests
_orig_get = requests.get
def _no_verify_get(url, **kwargs):
    kwargs.setdefault('verify', False)
    return _orig_get(url, **kwargs)
requests.get = _no_verify_get

try:
    import pycountry
except ImportError:
    sys.exit("Missing dependency. Run: pip install pycountry")

# ── Config ────────────────────────────────────────────────────────────────────
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

INDICATOR  = config['wb_indicator']
START, END = config['timeframe']

print(f"Indicator : {INDICATOR}")
print(f"Timeframe : {START}-{END}")

# ── Step 1: Economy metadata ──────────────────────────────────────────────────
# wb.economy.info().items is a list of dicts with keys:
#   'id' (iso3), 'value' (display name), 'aggregate' (bool), 'capitalCity', …
# We use pycountry to convert iso3 => iso2 (not available in the WB API response).
print("\nBuilding economy metadata...")

iso3_to_name = {}   # 'USA' -> 'United States'
iso3_to_iso2 = {}   # 'USA' -> 'us'

for e in wb.economy.info().items:
    if e.get('aggregate', True):          # skip World, regions, income groups
        continue

    iso3    = e['id']
    name    = e['value']
    capital = e.get('capitalCity', '').strip()

    if not capital:                       # second guard: no capital = aggregate
        continue

    # Convert iso3 -> iso2 via pycountry
    pc = pycountry.countries.get(alpha_3=iso3)
    iso2 = pc.alpha_2.lower() if pc else ''

    iso3_to_name[iso3] = name
    iso3_to_iso2[iso3] = iso2

print(f"  {len(iso3_to_name)} actual countries found.")

# Save name -> iso2 mapping for s2_get_flags.py
name_to_iso2 = {
    iso3_to_name[c]: iso3_to_iso2[c]
    for c in iso3_to_name
    if iso3_to_iso2.get(c)
}
with open('country_codes.json', 'w', encoding='utf-8') as f:
    json.dump(name_to_iso2, f, indent=2, ensure_ascii=False)
print("  Saved country_codes.json")

# ── Step 2: Fetch indicator data ──────────────────────────────────────────────
print(f"\nFetching {INDICATOR} ({START}-{END}) from World Bank API...")
print("  This may take 30-90 seconds…")

raw = wb.data.DataFrame(INDICATOR, economy='all', time=range(START, END + 1))


print(f"  Raw shape: {raw.shape}")

# wbgapi may return either orientation depending on version:
#   A) index=iso3 codes, columns='YR{year}' strings  (older)
#   B) index='YR{year}' strings, columns=iso3 codes  (newer)
# Detect by checking whether columns look like year strings or iso3 codes.
col_sample = str(raw.columns[0])
if col_sample.startswith('YR') or (col_sample.isdigit() and len(col_sample) == 4):
    # Layout A: columns are years
    raw.columns = pd.Index([str(c).replace('YR', '') for c in raw.columns]).astype(int)
    raw.index.name = 'iso3'
else:
    # Layout B: columns are economy codes, index are years — transpose
    raw.index = pd.Index([str(i).replace('YR', '') for i in raw.index]).astype(int)
    raw = raw.T
    raw.index.name = 'iso3'
    raw.columns = raw.columns.astype(int)

# ── Step 3: Filter to actual countries and rename to full names ───────────────
raw = raw[raw.index.isin(iso3_to_name)]
raw.index = [iso3_to_name[c] for c in raw.index]
raw.index.name = 'Country'
raw = raw.dropna(how='all')             # drop countries with zero data
print(f"  {len(raw)} countries have at least some data.")

# ── Step 4: Transpose => Year as rows ─────────────────────────────────────────
# NOTE: No .cumsum() — GDP, military spend, population are absolute annual
# snapshots, not cumulative totals.
df = raw.T
df.index.name = 'Year'
df = df.sort_index()

# ── Step 5: Fill data gaps ────────────────────────────────────────────────────
df = df.ffill().bfill()
df = df.dropna(axis=1, how='all')

# ── Step 6: Export ────────────────────────────────────────────────────────────
df.to_csv('FINAL_BAR_CHART_RACE.csv')

print(f"\nSUCCESS!")
print(f"  {len(df.columns)} countries x {len(df)} years => FINAL_BAR_CHART_RACE.csv")

print(f"\nTop 10 by {END}:")
for country, val in df.iloc[-1].sort_values(ascending=False).head(10).items():
    print(f"  {country:<40} {val:>20,.0f}")
