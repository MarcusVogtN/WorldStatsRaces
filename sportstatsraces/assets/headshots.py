"""HeadshotProvider — bg-removed player photos via rembg.

Source jpgs at <headshots_src_dir>/<fbref_id>.jpg are processed once with
rembg (U^2-Net) and cached as RGBA pngs at <cache_dir>/headshots_cutout/.
load() returns the native dimensions (200x200 from the ssref proxy) — no
aspect normalization, so the photo renders square inside the row's slot.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from races.assets.base import AssetProvider


def _lazy_rembg_remove():
    # Imported lazily so cold tools (--validate-layout, --preview-frames)
    # don't pay the onnxruntime startup unless a fresh cutout is needed.
    from rembg import remove
    return remove


class HeadshotProvider(AssetProvider):
    def __init__(self, cfg, cache_dir):
        super().__init__(cfg, cache_dir)
        self.src_dir = Path(cfg.get('headshots_src_dir', 'cache/fbref/headshots'))
        self.cutout_dir = self.cache_dir / 'headshots_cutout'
        self.cutout_dir.mkdir(parents=True, exist_ok=True)
        self._memo: dict = {}
        self._name_to_fid: dict = {}
        self._remove = None

    def _cut_one(self, fbref_id: str) -> bool:
        out = self.cutout_dir / f'{fbref_id}.png'
        if out.exists() and out.stat().st_size > 500:
            return True
        src = self.src_dir / f'{fbref_id}.jpg'
        if not src.exists():
            return False
        if self._remove is None:
            self._remove = _lazy_rembg_remove()
        try:
            cut = self._remove(src.read_bytes())
            if isinstance(cut, (bytes, bytearray)):
                out.write_bytes(bytes(cut))
            else:
                # Older rembg returns a PIL Image.
                cut.save(out, format='PNG')
            return True
        except Exception as exc:
            print(f"  rembg failed for {fbref_id}: {exc}")
            return False

    def ensure(self, names, icon_ids):
        self._name_to_fid = dict(icon_ids)
        done = skipped = missing = 0
        for name in names:
            fid = (icon_ids.get(name) or '').strip()
            if not fid:
                missing += 1
                continue
            out = self.cutout_dir / f'{fid}.png'
            if out.exists() and out.stat().st_size > 500:
                skipped += 1
                continue
            if self._cut_one(fid):
                done += 1
                print(f"  cutout {name} [{fid}]")
            else:
                missing += 1
        print(f"Headshots: {done} cut out, {skipped} cached, {missing} missing.")

    def load(self, name) -> Optional[np.ndarray]:
        if name in self._memo:
            return self._memo[name]
        fid = self._name_to_fid.get(name)
        if not fid:
            self._memo[name] = None
            return None
        path = self.cutout_dir / f'{fid}.png'
        if not path.exists():
            self._memo[name] = None
            return None
        img = np.array(Image.open(path).convert('RGBA'))
        self._memo[name] = img
        return img
