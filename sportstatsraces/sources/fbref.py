"""Fbref PL all-time goals source.

Reads the prototype's pre-scraped parquet (year × fbref_id, cumulative goals)
and the player-meta json, returns a year × display_name DataFrame plus an
icon_ids map keyed by display_name → fbref_id.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from races.sources.base import DataSource, SourceResult


class FbrefPLSource(DataSource):
    def fetch(self) -> SourceResult:
        parquet_path = Path(self.cfg['parquet_path'])
        meta_path = Path(self.cfg['meta_path'])
        timeframe = self.cfg.get('timeframe')
        top_n_keep = int(self.cfg.get('top_n_keep', 200))

        df = pd.read_parquet(parquet_path)
        df.index = df.index.astype(int)
        meta = json.loads(meta_path.read_text(encoding='utf-8'))

        if timeframe:
            y0, y1 = int(timeframe[0]), int(timeframe[1])
            df = df.loc[(df.index >= y0) & (df.index <= y1)]

        # Trim to the most career-prolific players to keep rank-smoothing cheap.
        # The renderer only ever shows top_n_on_screen rows, so anyone whose
        # career peak is below the leaderboard's tail is invisible regardless.
        final_max = df.max(axis=0).fillna(0).sort_values(ascending=False)
        keep_ids = list(final_max.head(top_n_keep).index)
        df = df[keep_ids]

        # fbref_id → display_name. Disambiguate name collisions by suffixing the
        # short fbref_id (rare, but possible).
        rename: dict[str, str] = {}
        seen: dict[str, int] = {}
        icon_ids: dict[str, str] = {}
        for fid in df.columns:
            entry = meta.get(fid) or {}
            name = (entry.get('display_name') or fid).strip()
            if name in seen:
                name = f"{name} ({fid[:4]})"
            seen[name] = 1
            rename[fid] = name
            icon_ids[name] = fid
        df = df.rename(columns=rename)

        return SourceResult(
            data=df,
            icon_ids=icon_ids,
            source_credit='Source: fbref.com',
            population=None,
        )
