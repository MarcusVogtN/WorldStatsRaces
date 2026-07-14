"""YearlyPhotoProvider — pre-cut transparent player photos, one per period.

Source pngs at <photos_dir>/<icon_id>_<year>.png are already RGBA cutouts
(e.g. SoFIFA edition portraits), so no rembg pass is needed. load() accepts
an optional year and returns that period's photo, falling back to the
nearest available year for the player. Requires the renderer's
`yearly_icons` flag to actually receive a year; without it the provider
behaves like a static one (latest photo wins).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from races.assets.base import AssetProvider


class YearlyPhotoProvider(AssetProvider):
    def __init__(self, cfg, cache_dir):
        super().__init__(cfg, cache_dir)
        self.photos_dir = Path(cfg.get('photos_dir', 'sportstatsraces/data/fifa_photos'))
        self._name_to_id: dict = {}
        self._years: dict = {}   # icon_id -> sorted list of available years
        self._memo: dict = {}

    def _years_for(self, icon_id: str) -> list:
        if icon_id not in self._years:
            years = []
            for p in self.photos_dir.glob(f'{icon_id}_*.png'):
                m = re.fullmatch(rf'{re.escape(icon_id)}_(\d{{4}})', p.stem)
                if m:
                    years.append(int(m.group(1)))
            self._years[icon_id] = sorted(years)
        return self._years[icon_id]

    def ensure(self, names, icon_ids):
        self._name_to_id = dict(icon_ids)
        missing = [n for n in names
                   if not self._years_for((icon_ids.get(n) or '').strip())]
        print(f"Yearly photos: {len(names) - len(missing)} players covered, "
              f"{len(missing)} missing.")
        for n in missing:
            print(f"  no photos for {n} [{icon_ids.get(n)}]")

    def load(self, name, year=None) -> Optional[np.ndarray]:
        icon_id = (self._name_to_id.get(name) or '').strip()
        if not icon_id:
            return None
        years = self._years_for(icon_id)
        if not years:
            return None
        y = min(years, key=lambda v: abs(v - year)) if year is not None else years[-1]
        key = (icon_id, y)
        if key not in self._memo:
            path = self.photos_dir / f'{icon_id}_{y}.png'
            self._memo[key] = np.array(Image.open(path).convert('RGBA'))
        return self._memo[key]
