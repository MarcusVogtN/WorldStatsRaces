"""Generic CSV data source.

Reads any tidy CSV (one row per entity-year-value), filters and pivots it to
the Year-indexed wide frame the renderer expects, and resolves country names
to ISO2 codes via pycountry so the flag asset provider can find icons.

Config keys (under `source` in the channel config):
  type: "csv"                       # registry key
  path: "<relative path to csv>"    # required
  country_col: "Country"            # default
  year_col: "Year"                  # default
  value_col: "<value column>"       # required
  filters: {col: value, ...}        # optional pre-pivot equality filters
  timeframe: [start, end]           # required (inclusive)
  source_credit: "Source: ..."      # required (footer credit)
  name_overrides: {raw: pretty}     # optional display-name remap
"""

import sys
from pathlib import Path

import pandas as pd

from .base import DataSource, SourceResult


_DEFAULT_OVERRIDES = {
    "Bolivia (Plurinational State of)": "Bolivia",
    "Bosnia and Herzegovina": "Bosnia",
    "Czech Republic": "Czechia",
    "Iran (Islamic Republic of)": "Iran",
    "Lao People's Democratic Republic": "Laos",
    "Lao PDR": "Laos",
    "Micronesia (Federated States of)": "Micronesia",
    "Republic of Korea": "South Korea",
    "Korea, Republic of": "South Korea",
    "Democratic People's Republic of Korea": "North Korea",
    "Korea, Democratic People's Republic of": "North Korea",
    "Republic of Moldova": "Moldova",
    "Russian Federation": "Russia",
    "Syrian Arab Republic": "Syria",
    "United Republic of Tanzania": "Tanzania",
    "United States of America": "United States",
    "United Kingdom of Great Britain and Northern Ireland": "United Kingdom",
    "Venezuela (Bolivarian Republic of)": "Venezuela",
    "Viet Nam": "Vietnam",
    "Cabo Verde": "Cape Verde",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "TFYR Macedonia": "North Macedonia",
    "Macedonia": "North Macedonia",
    "Brunei Darussalam": "Brunei",
    "Eswatini": "Eswatini",
    "Swaziland": "Eswatini",
    "Timor-Leste": "Timor-Leste",
    "State of Palestine": "Palestine",
    "Occupied Palestinian Territory": "Palestine",
    "Taiwan, Province of China": "Taiwan",
}


def _resolve_iso2(raw_name: str):
    """Return (display_name, iso2_lower) or (display_name, None) if unmatched."""
    try:
        import pycountry
    except ImportError:
        sys.exit("Missing dependency. Run: pip install pycountry")

    pretty = _DEFAULT_OVERRIDES.get(raw_name, raw_name)
    pc = None
    for candidate in (pretty, raw_name):
        try:
            pc = pycountry.countries.lookup(candidate)
            break
        except LookupError:
            pass
    if pc is None:
        try:
            results = pycountry.countries.search_fuzzy(raw_name)
            pc = results[0] if results else None
        except LookupError:
            pc = None
    if pc is None:
        return pretty, None
    iso2 = pc.alpha_2.lower()
    # Prefer common_name when present (e.g., "South Korea" over "Korea, Republic of")
    common = getattr(pc, 'common_name', None)
    if raw_name not in _DEFAULT_OVERRIDES:
        pretty = common or pretty
    return pretty, iso2


class CsvSource(DataSource):
    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self._credit = cfg.get('source_credit', 'Source: CSV')

    @property
    def source_credit(self) -> str:
        return self._credit

    def fetch(self) -> SourceResult:
        path = Path(self.cfg['path'])
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            sys.exit(f"CSV source: file not found at {path}")

        country_col = self.cfg.get('country_col', 'Country')
        year_col = self.cfg.get('year_col', 'Year')
        value_col = self.cfg['value_col']
        start, end = self.cfg['timeframe']

        print(f"CSV source : {path.name}")
        print(f"Filters    : {self.cfg.get('filters') or {}}")
        print(f"Timeframe  : {start}-{end}")

        df = pd.read_csv(path)
        for col, val in (self.cfg.get('filters') or {}).items():
            df = df[df[col] == val]
        df = df[(df[year_col] >= start) & (df[year_col] <= end)]
        if df.empty:
            sys.exit("CSV source: no rows survived filtering.")

        # Apply user name_overrides on top of defaults before grouping so two
        # raw names mapping to the same display name get averaged sanely.
        overrides = dict(_DEFAULT_OVERRIDES)
        overrides.update(self.cfg.get('name_overrides') or {})
        df = df.copy()
        df['_display'] = df[country_col].map(lambda n: overrides.get(n, n))

        # Resolve ISO2 per raw name (one lookup per unique name).
        raw_to_pretty_iso = {}
        for raw in df[country_col].unique():
            pretty, iso2 = _resolve_iso2(raw)
            raw_to_pretty_iso[raw] = (overrides.get(raw, pretty), iso2)

        # Re-derive display from the resolution table so common_name kicks in
        # for names not in the overrides dict.
        df['_display'] = df[country_col].map(lambda n: raw_to_pretty_iso[n][0])

        pivot = df.pivot_table(index=year_col, columns='_display',
                               values=value_col, aggfunc='mean')
        pivot.index = pivot.index.astype(int)
        pivot.index.name = 'Year'
        pivot.columns.name = None
        pivot = pivot.sort_index().ffill().bfill().dropna(axis=1, how='all')

        icon_ids = {}
        for raw, (pretty, iso2) in raw_to_pretty_iso.items():
            if iso2 and pretty in pivot.columns:
                icon_ids[pretty] = iso2

        unmatched = [raw for raw, (_, iso2) in raw_to_pretty_iso.items() if not iso2]
        if unmatched:
            print(f"  [csv] {len(unmatched)} country/countries without ISO2:")
            for n in unmatched[:20]:
                print(f"    - {n}")

        print(f"  {len(pivot.columns)} entities × {len(pivot)} years.")
        return SourceResult(data=pivot, icon_ids=icon_ids,
                            source_credit=self._credit, population=None)
