"""US baby-names data source (SSA national data via the dxdc mirror).

The SSA's own names.zip is Akamai-blocked to programmatic clients, so this
pulls per-year files from a mirror that tracks SSA releases — one `yob<YEAR>.txt`
(`Name,Sex,Count`) per year, currently 1880-2024 (SSA publishes each year's
names ~12 months later, so the latest year lags).

We race the *share of births* (count / that year's total for the sex), not raw
counts, so the race reflects true dominance instead of population growth — Mary
was ~7.8% of all US girls in 1880; the top name in 2024 is barely 1%. That
collapse is the story.

Config keys (under `source`):
  type: "ssa_names"
  url_template: "...yob{year}.txt"  # optional; defaults to the dxdc mirror
  sex:  "F" | "M"                  # required
  timeframe: [start, end]          # inclusive; missing years are skipped
  top_keep: 15                     # keep names that reach this rank in any year
  source_credit: "Source: ..."     # footer credit
"""

import io
import sys

import pandas as pd
import requests
import urllib3

from .base import DataSource, SourceResult

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_DEFAULT_URL_TEMPLATE = ("https://raw.githubusercontent.com/dxdc/babynames/"
                         "master/raw/yob{year}.txt")


class SsaNamesSource(DataSource):
    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self._credit = cfg.get('source_credit',
                               'Source: US Social Security Administration')

    @property
    def source_credit(self) -> str:
        return self._credit

    def fetch(self) -> SourceResult:
        tmpl = self.cfg.get('url_template', _DEFAULT_URL_TEMPLATE)
        sex = self.cfg['sex']
        start, end = self.cfg['timeframe']
        top_keep = int(self.cfg.get('top_keep', 15))

        print(f"SSA names  : {tmpl}")
        print(f"Sex        : {sex}")
        print(f"Timeframe  : {start}-{end}, keep names ever in top {top_keep}")

        frames, missing = [], []
        for year in range(start, end + 1):
            resp = requests.get(tmpl.format(year=year), timeout=30, verify=False)
            if resp.status_code != 200:
                missing.append(year)
                continue
            f = pd.read_csv(io.StringIO(resp.text),
                            names=['name', 'sex', 'count'])
            f['year'] = year
            frames.append(f)
        if missing:
            print(f"  [skip] no data for {len(missing)} year(s): "
                  f"{missing[0]}…{missing[-1]}")
        if not frames:
            sys.exit("SSA names source: no year files downloaded.")
        df = pd.concat(frames, ignore_index=True)

        df = df[df['sex'] == sex]
        if df.empty:
            sys.exit(f"SSA names source: no rows for sex='{sex}'.")

        # Share of births that year for the sex — denominator uses ALL names
        # (before the top-N filter) so it reflects the true national total.
        year_total = df.groupby('year')['count'].transform('sum')
        df = df.assign(share=df['count'] / year_total)

        # Names that reach the top `top_keep` in any single year — everything
        # else is permanent filler that never shows on screen.
        keep = set()
        for _, sub in df.groupby('year'):
            keep |= set(sub.nlargest(top_keep, 'share')['name'])
        df = df[df['name'].isin(keep)]

        pivot = df.pivot_table(index='year', columns='name',
                               values='share', aggfunc='mean')
        pivot.index = pivot.index.astype(int)
        pivot.index.name = 'Year'
        pivot.columns.name = None
        # A name absent in a year held 0 share that year (not missing data).
        pivot = pivot.sort_index().fillna(0.0)

        # Letter-avatar provider keys off the display name itself.
        icon_ids = {name: name for name in pivot.columns}

        print(f"  {len(pivot.columns)} names × {len(pivot)} years "
              f"({pivot.index.min()}-{pivot.index.max()}).")
        return SourceResult(data=pivot, icon_ids=icon_ids,
                            source_credit=self._credit, population=None)
