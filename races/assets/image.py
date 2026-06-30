"""Artist-image asset provider — square promo photos via TheAudioDB.

For entity races where the entities are people/acts (e.g. music artists) we
show a real photo instead of a letter avatar. Photos are square-cropped PNGs
cached at <cache_dir>/artist_photos/<name>.png; the renderer applies rounded
corners (`flag_corner_radius_frac`), so they read as clean rounded tiles.

load() is lazy and only the artists that actually reach the visible top-N are
ever fetched. Anything without a photo (or a failed fetch) falls back to a
letter avatar so a row is never blank.

Config keys (under `assets`):
  type: "image"
  name_overrides: {display_name: search_query}   # optional, for ambiguous names
"""

import urllib.parse
from io import BytesIO
from typing import Optional

import numpy as np
import requests
import urllib3
from PIL import Image

from .base import AssetProvider
from .letter import LetterAvatarProvider
from ..util import safe_filename

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_SEARCH = "https://www.theaudiodb.com/api/v1/json/2/search.php?s={q}"
_UA = {"User-Agent": "WorldBankRacePipeline/1.0"}
# Stage-name credits that don't resolve to the act on their own.
_DEFAULT_OVERRIDES = {"'N Sync": "NSYNC", "Janet": "Janet Jackson"}


def _square(pil: Image.Image) -> Image.Image:
    w, h = pil.size
    s = min(w, h)
    return pil.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))


class ArtistImageProvider(AssetProvider):
    def __init__(self, cfg, cache_dir):
        super().__init__(cfg, cache_dir)
        self.photos_dir = self.cache_dir / 'artist_photos'
        self.photos_dir.mkdir(parents=True, exist_ok=True)
        self._memo: dict = {}
        self._overrides = dict(_DEFAULT_OVERRIDES)
        self._overrides.update(cfg.get('name_overrides') or {})
        self._letter = LetterAvatarProvider(cfg, cache_dir)  # fallback

    def ensure(self, names, icon_ids):
        # Lazy: photos are fetched on first load(), so only on-screen artists
        # trigger a download.
        pass

    def _download(self, name):
        """Fetch + square-crop a thumb to the photo cache; return path or None."""
        query = self._overrides.get(name, name)
        try:
            meta = requests.get(_SEARCH.format(q=urllib.parse.quote(query)),
                                headers=_UA, timeout=20, verify=False).json()
            a = (meta.get('artists') or [None])[0]
            url = a and a.get('strArtistThumb')
            if not url:
                return None
            raw = requests.get(url, headers=_UA, timeout=20, verify=False).content
            path = self.photos_dir / (safe_filename(name) + '.png')
            _square(Image.open(BytesIO(raw)).convert('RGBA')).save(path, format='PNG')
            print(f"  photo {name}")
            return path
        except Exception as exc:
            print(f"  photo FAIL {name}: {exc}")
            return None

    def load(self, name) -> Optional[np.ndarray]:
        if name in self._memo:
            return self._memo[name]
        path = self.photos_dir / (safe_filename(name) + '.png')
        if not (path.exists() and path.stat().st_size > 500):
            path = self._download(name)
        img = (np.array(Image.open(path).convert('RGBA'))
               if path else self._letter.load(name))
        self._memo[name] = img
        return img
