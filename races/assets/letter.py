"""Letter-avatar asset provider.

For datasets with no natural icon (e.g. baby names) we render a colored
rounded square bearing the entity's first initial. Color is a stable hash of
the name so each name keeps its identity as it moves through the race.

Avatars are generated lazily in `load()` (in-memory, memoized) — no network,
no disk. By the time `load()` runs the renderer has already registered the
Orbitron font in cache/fonts/, which we reuse for a consistent look.
"""

import hashlib
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .base import AssetProvider

# Vibrant, dark-theme-friendly palette. Index chosen by name hash.
_PALETTE = [
    (231, 76, 60), (46, 204, 113), (52, 152, 219), (155, 89, 182),
    (241, 196, 15), (230, 126, 34), (26, 188, 156), (233, 30, 99),
    (102, 187, 106), (66, 165, 245), (255, 167, 38), (171, 71, 188),
]
_SIZE = 256


def _load_font(cache_dir: Path, px: int) -> ImageFont.FreeTypeFont:
    for cand in (cache_dir / 'fonts' / 'Orbitron.ttf',
                 Path('C:/Windows/Fonts/arialbd.ttf')):
        try:
            return ImageFont.truetype(str(cand), px)
        except OSError:
            continue
    return ImageFont.load_default()


class LetterAvatarProvider(AssetProvider):
    def __init__(self, cfg, cache_dir):
        super().__init__(cfg, cache_dir)
        self._memo: dict = {}

    def ensure(self, names, icon_ids):
        # Avatars are generated on demand in load(); nothing to prefetch.
        pass

    def load(self, name) -> Optional[np.ndarray]:
        if name in self._memo:
            return self._memo[name]

        digest = hashlib.md5(name.encode('utf-8')).hexdigest()
        color = _PALETTE[int(digest, 16) % len(_PALETTE)]
        letter = (name.strip()[:1] or '?').upper()

        img = Image.new('RGBA', (_SIZE, _SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([0, 0, _SIZE - 1, _SIZE - 1],
                               radius=int(_SIZE * 0.22),
                               fill=color + (255,))
        font = _load_font(self.cache_dir, int(_SIZE * 0.6))
        l, t, r, b = draw.textbbox((0, 0), letter, font=font)
        draw.text(((_SIZE - (r - l)) / 2 - l, (_SIZE - (b - t)) / 2 - t),
                  letter, font=font, fill=(255, 255, 255, 255))

        arr = np.array(img)
        self._memo[name] = arr
        return arr
