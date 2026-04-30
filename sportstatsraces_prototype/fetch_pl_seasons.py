"""Premier League full-history goal-scorer sweep.

Scrapes every Premier League season's Standard Stats table (1992-93 to current),
aggregates per-player league goals across all seasons, and emits

    cache/fbref/pl_career_goals.parquet     # year x player, cumulative goals
    cache/fbref/pl_per_season_goals.parquet # year x player, per-season goals
    cache/fbref/pl_player_meta.json         # {fbref_id: {display_name, slug, first_season, last_season}}

Column names are fbref player IDs (stable across seasons) so re-runs in later
years won't break when display names change. The metadata json maps id ->
canonical display name (the most recent one fbref used).

Each player who has ever scored a PL goal becomes a column. The renderer only
animates the visible top-N rows, so feeding it 700+ players is fine.

Usage:
    python sportstatsraces_prototype/fetch_pl_seasons.py            # full sweep
    python sportstatsraces_prototype/fetch_pl_seasons.py --refresh-current  # re-fetch current season
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

from _headshots import MissingTracker, fetch_headshot

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = REPO_ROOT / "cache" / "fbref"
SEASONS_DIR = CACHE_DIR / "seasons"
HTML_DIR = CACHE_DIR / "html"
HEADSHOT_DIR = CACHE_DIR / "headshots"

OUT_CUM = CACHE_DIR / "pl_career_goals.parquet"
OUT_PER = CACHE_DIR / "pl_per_season_goals.parquet"
OUT_META = CACHE_DIR / "pl_player_meta.json"

FBREF_BASE = "https://fbref.com"

PL_FIRST_SEASON_START = 1992
# Edit when the next season opens; check fbref.com/en/comps/9/Premier-League-Stats
CURRENT_SEASON_END = 2026

RATE_LIMIT_SECONDS = 3.5
PLAYER_URL_RE = re.compile(r"/en/players/([a-f0-9]{8})/([A-Za-z0-9-]+)")


def _find_bin(name: str) -> str:
    for c in (f"{name}.cmd", f"{name}.exe", name):
        f = shutil.which(c)
        if f:
            return f
    return name


FIRECRAWL_BIN = _find_bin("firecrawl")


def season_label(start_year: int) -> str:
    return f"{start_year}-{start_year + 1}"


def season_url(label: str, is_current: bool) -> str:
    # Completed-season pages live at /comps/9/<season>/stats/<season>-Premier-League-Stats.
    # The current season has no <season> path segment; "Premier-League-Stats" alone is the
    # squads-only summary, so we hit /comps/9/stats/Premier-League-Stats for player rows.
    if is_current:
        return "https://fbref.com/en/comps/9/stats/Premier-League-Stats"
    return f"https://fbref.com/en/comps/9/{label}/stats/{label}-Premier-League-Stats"


def fetch_player_html(fbref_id: str, slug: str) -> Path | None:
    """Cache the player's fbref page so _headshots.fetch_headshot can parse it."""
    out = HTML_DIR / f"{fbref_id}.html"
    if out.exists() and out.stat().st_size > 50_000:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    url = f"{FBREF_BASE}/en/players/{fbref_id}/{slug}"
    print(f"  fetching {url}", flush=True)
    cmd = [FIRECRAWL_BIN, "scrape", url, "--format", "rawHtml", "--profile", "fbref", "-o", str(out)]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if res.returncode != 0 or not out.exists() or out.stat().st_size < 50_000:
        print(f"  player-page fetch failed for {fbref_id}: {res.stderr.strip()}")
        if out.exists():
            out.unlink()
        return None
    time.sleep(RATE_LIMIT_SECONDS)
    return out


def fetch_season(label: str, is_current: bool, refresh: bool = False) -> Path:
    out = SEASONS_DIR / f"{label}.html"
    if out.exists() and out.stat().st_size > 100_000 and not refresh:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    url = season_url(label, is_current)
    print(f"  fetching {url}", flush=True)
    cmd = [FIRECRAWL_BIN, "scrape", url, "--format", "rawHtml", "--profile", "fbref", "-o", str(out)]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if res.returncode != 0 or not out.exists() or out.stat().st_size < 100_000:
        raise RuntimeError(
            f"firecrawl failed for {url}\nstdout: {res.stdout}\nstderr: {res.stderr}"
        )
    time.sleep(RATE_LIMIT_SECONDS)
    return out


def parse_season(html_path: Path) -> list[tuple[str, str, str, int]]:
    """Return list of (fbref_id, slug, display_name, goals) for every player
    with non-null goals in this season's Standard Stats table.
    """
    tables = pd.read_html(str(html_path), attrs={"id": "stats_standard"}, extract_links="body")
    if not tables:
        raise RuntimeError(f"no stats_standard table in {html_path.name}")
    df = tables[0]

    # Find Player and Gls columns (cope with multi-index headers).
    def col_match(needle: str):
        for c in df.columns:
            tail = c[-1] if isinstance(c, tuple) else c
            if tail == needle:
                return c
        return None

    player_col = col_match("Player")
    gls_col = col_match("Gls")
    if player_col is None or gls_col is None:
        raise RuntimeError(f"missing Player or Gls column in {html_path.name}")

    out: list[tuple[str, str, str, int]] = []
    for _, row in df.iterrows():
        pcell = row[player_col]
        gcell = row[gls_col]
        if not isinstance(pcell, tuple):
            continue
        name, url = pcell
        if not name or not url:
            continue
        m = PLAYER_URL_RE.search(url)
        if not m:
            continue
        fbref_id, slug = m.group(1), m.group(2)
        goals_text = gcell[0] if isinstance(gcell, tuple) else gcell
        try:
            goals = int(goals_text)
        except (TypeError, ValueError):
            continue
        if goals < 0:
            continue
        out.append((fbref_id, slug, str(name).strip(), goals))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-current", action="store_true",
                    help="Re-fetch the current season's HTML even if cached.")
    ap.add_argument("--fetch-headshots", action="store_true",
                    help="After parsing seasons, fetch each player's page + headshot. "
                         "Multi-hour first run for the full PL roster; cached on re-runs.")
    ap.add_argument("--headshots-limit", type=int, default=None,
                    help="With --fetch-headshots, cap the number of players processed "
                         "(highest career PL goals first). Useful for smoke tests.")
    args = ap.parse_args()

    seasons = list(range(PL_FIRST_SEASON_START, CURRENT_SEASON_END))  # 1992..2025
    print(f"Fetching {len(seasons)} PL seasons ({seasons[0]}-{seasons[0]+1} to "
          f"{seasons[-1]}-{seasons[-1]+1})...")

    # player_id -> {end_year: goals}
    per_season: dict[str, dict[int, int]] = {}
    # player_id -> {end_year: display_name}
    name_history: dict[str, dict[int, str]] = {}
    # player_id -> slug
    slugs: dict[str, str] = {}

    for start in seasons:
        end = start + 1
        label = season_label(start)
        is_current = (end == CURRENT_SEASON_END)
        refresh = is_current and args.refresh_current
        try:
            html = fetch_season(label, is_current, refresh=refresh)
        except Exception as e:
            print(f"  [{label}] fetch failed: {e}")
            continue

        try:
            rows = parse_season(html)
        except Exception as e:
            print(f"  [{label}] parse failed: {e}")
            continue

        scorers = sum(1 for *_, g in rows if g > 0)
        print(f"  [{label}] {len(rows)} players, {scorers} scorers")

        for fbref_id, slug, name, goals in rows:
            per_season.setdefault(fbref_id, {})[end] = (
                per_season.get(fbref_id, {}).get(end, 0) + goals
            )
            name_history.setdefault(fbref_id, {})[end] = name
            slugs[fbref_id] = slug

    if not per_season:
        print("No data parsed.", file=sys.stderr)
        return 1

    all_years = sorted({y for d in per_season.values() for y in d})
    year_index = list(range(min(all_years), max(all_years) + 1))
    columns = list(per_season.keys())

    per_df = pd.DataFrame(0, index=year_index, columns=columns, dtype=float)
    for pid, season_goals in per_season.items():
        for y, g in season_goals.items():
            per_df.loc[y, pid] = g

    cum_df = per_df.cumsum()
    # NaN before each player's debut so the renderer doesn't draw zero-streaks.
    debut = {pid: min(d) for pid, d in per_season.items()}
    for pid, y in debut.items():
        cum_df.loc[cum_df.index < y, pid] = pd.NA

    per_df.to_parquet(OUT_PER)
    cum_df.to_parquet(OUT_CUM)

    meta: dict[str, dict] = {}
    for pid, history in name_history.items():
        last_year = max(history)
        meta[pid] = {
            "display_name": history[last_year],
            "fbref_slug": slugs[pid],
            "first_season_end": min(history),
            "last_season_end": last_year,
            "career_pl_goals": int(per_df[pid].sum()),
        }
    OUT_META.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nWrote {OUT_CUM.name}: {cum_df.shape[0]} years x {cum_df.shape[1]} players")
    print(f"Wrote {OUT_PER.name}, {OUT_META.name}")

    print("\nAll-time PL top-15 goalscorers (latest year cumulative):")
    last = cum_df.iloc[-1].dropna().sort_values(ascending=False).head(15)
    for pid, g in last.items():
        print(f"  {int(g):4d}  {meta[pid]['display_name']}  ({pid})")

    if args.fetch_headshots:
        ranked = sorted(meta.items(), key=lambda kv: -kv[1]["career_pl_goals"])
        if args.headshots_limit is not None:
            ranked = ranked[: args.headshots_limit]
        print(f"\nFetching headshots for {len(ranked)} players "
              f"(rate-limited at {RATE_LIMIT_SECONDS}s between fbref hits)...")
        tracker = MissingTracker()
        for pid, info in ranked:
            cached = (HEADSHOT_DIR / f"{pid}.jpg")
            if cached.exists() and cached.stat().st_size > 1000:
                continue
            print(f"[{info['display_name']}]")
            html = fetch_player_html(pid, info["fbref_slug"])
            if html is None:
                tracker.add(info["display_name"], pid)
                continue
            fetch_headshot(html, pid, info["display_name"], HEADSHOT_DIR, tracker)
        tracker.print_summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())
