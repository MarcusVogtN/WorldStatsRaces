"""Generic player-race CSV source.

Reads a tidy CSV (one row per entity-period-value), pivots it to the
period-indexed wide frame the renderer expects. Unlike `csv_source`, it does
NO country/ISO resolution — entities are players (or anything), and the
icon-id map (name -> asset id) is passed straight through from config, or
left empty for the letter-avatar provider.

Config keys (under `source`):
  type: "players_csv"
  path: "<relative path to csv>"     # required
  entity_col: "player"               # default
  period_col: "age"                  # default (becomes the race ticker)
  value_col: "goals"                 # default
  source_credit: "Source: ..."       # footer credit
  icon_ids: {name: id, ...}          # optional name -> asset id
"""

import sys
from pathlib import Path

import pandas as pd

from .base import DataSource, SourceResult


class PlayersCsvSource(DataSource):
    def fetch(self) -> SourceResult:
        path = Path(self.cfg['path'])
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            sys.exit(f"players_csv: file not found at {path}")

        entity_col = self.cfg.get('entity_col', 'player')
        period_col = self.cfg.get('period_col', 'age')
        value_col = self.cfg.get('value_col', 'goals')

        df = pd.read_csv(path)
        pivot = df.pivot_table(index=period_col, columns=entity_col,
                               values=value_col, aggfunc='mean')
        pivot.index = pivot.index.astype(int)
        pivot.index.name = 'Year'
        pivot.columns.name = None
        pivot = pivot.sort_index()

        # Optional inclusive period window (e.g. cap ages at 15..18). Absent =
        # use the full range in the CSV.
        timeframe = self.cfg.get('timeframe')
        if timeframe:
            y0, y1 = int(timeframe[0]), int(timeframe[1])
            pivot = pivot.loc[(pivot.index >= y0) & (pivot.index <= y1)]

        icon_ids = dict(self.cfg.get('icon_ids') or {})
        credit = self.cfg.get('source_credit', 'Source: CSV')
        print(f"players_csv: {len(pivot.columns)} entities × {len(pivot)} periods.")
        return SourceResult(data=pivot, icon_ids=icon_ids,
                            source_credit=credit, population=None)
