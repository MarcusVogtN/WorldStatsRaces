"""Shared headshot fetcher for the fbref prototype scripts.

fbref's `req/<datestamp>/images/headshots/<id>_<year>.jpg` CDN is gated by
Cloudflare and returns 403 to direct curl, even with browser headers and a
Referer. The same image is mirrored, unprotected, behind Sports Reference's
resize proxy at `cdn.ssref.net/scripts/image_resize.cgi?min=<px>&url=<...>`.
That proxy is what fbref itself uses for og:image / twitter:image / JSON-LD
contentUrl, so it's the canonical path. We hit it directly.

Usage:

    tracker = MissingTracker()
    fetch_headshot(html_path, fbref_id, display_name, headshot_dir, tracker)
    tracker.print_summary()
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Either form fbref uses in player HTML — direct img src or JSON-LD contentUrl.
HEADSHOT_RE = re.compile(
    r'https://fbref\.com/req/[0-9]+/images/headshots/[a-f0-9]+_[0-9]+\.jpg'
)
PROXY_TEMPLATE = "http://cdn.ssref.net/scripts/image_resize.cgi?min=200&url={url}"


def _find_bin(name: str) -> str:
    for c in (f"{name}.cmd", f"{name}.exe", name):
        f = shutil.which(c)
        if f:
            return f
    return name


CURL_BIN = _find_bin("curl")


@dataclass
class MissingTracker:
    """Collects (display_name, fbref_id) pairs whose headshots couldn't be fetched."""

    missing: list[tuple[str, str]] = field(default_factory=list)

    def add(self, display_name: str, fbref_id: str) -> None:
        self.missing.append((display_name, fbref_id))

    def print_summary(self) -> None:
        if not self.missing:
            print("\nAll headshots cached.")
            return
        width = max(len(n) for n, _ in self.missing)
        print(f"\nMissing headshots ({len(self.missing)}):")
        for name, fid in self.missing:
            print(f"  {name.ljust(width)}  ({fid})")


def fetch_headshot(
    html_path: Path,
    fbref_id: str,
    display_name: str,
    headshot_dir: Path,
    tracker: MissingTracker,
) -> Path | None:
    """Cache the player's headshot under <headshot_dir>/<fbref_id>.jpg.

    Returns the path on success (including cached), None on failure. Failures
    are recorded on the tracker so the caller can print a summary at the end.
    """
    out = headshot_dir / f"{fbref_id}.jpg"
    if out.exists() and out.stat().st_size > 1000:
        return out

    text = html_path.read_text(encoding="utf-8", errors="replace")
    m = HEADSHOT_RE.search(text)
    if not m:
        print(f"  no headshot URL in HTML for {display_name} ({fbref_id})")
        tracker.add(display_name, fbref_id)
        return None

    proxy_url = PROXY_TEMPLATE.format(url=m.group(0))
    out.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [CURL_BIN, "-fsSL", "-o", str(out), proxy_url],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0 or not out.exists() or out.stat().st_size < 1000:
        print(f"  headshot proxy failed for {display_name} ({fbref_id}): {result.stderr.strip()}")
        if out.exists():
            out.unlink()
        tracker.add(display_name, fbref_id)
        return None
    print(f"  headshot saved: {display_name} ({out.name})")
    return out
