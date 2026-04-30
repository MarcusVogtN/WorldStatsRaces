"""Stage-one fbref data sourcing for sportstatsraces.

Scrapes top all-time scorers' fbref pages, parses Standard Stats: Domestic
Leagues into a per-season league-goals DataFrame, and emits
cache/fbref/career_goals.parquet in the shape SourceResult.data expects
(index = end-of-season year, columns = player display names, values =
cumulative league goals).

Also downloads each player's headshot to cache/fbref/headshots/<id>.jpg for
the future HeadshotProvider.

Usage:
    python sportstatsraces_prototype/fetch_fbref.py

Subsequent runs are no-ops for cached players. Add new names to players.json
and re-run; only new players hit the network.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

def _find_bin(name: str) -> str:
    # On Windows, prefer .cmd/.exe over shell shims.
    for candidate in (f"{name}.cmd", f"{name}.exe", name):
        found = shutil.which(candidate)
        if found:
            return found
    return name


FIRECRAWL_BIN = _find_bin("firecrawl")
CURL_BIN = _find_bin("curl")

import pandas as pd

from _headshots import MissingTracker, fetch_headshot

REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYERS_JSON = REPO_ROOT / "sportstatsraces_prototype" / "players.json"
CACHE_DIR = REPO_ROOT / "cache" / "fbref"
HTML_DIR = CACHE_DIR / "html"
HEADSHOT_DIR = CACHE_DIR / "headshots"
OUT_PARQUET = CACHE_DIR / "career_goals.parquet"
OUT_PER_SEASON_PARQUET = CACHE_DIR / "league_goals_per_season.parquet"

FBREF_BASE = "https://fbref.com"
RATE_LIMIT_SECONDS = 3.5  # Sports Reference asks for ~1 req / 3 sec

CANONICAL_RE = re.compile(r'rel="canonical"\s+href="([^"]+)"')
PLAYER_URL_RE = re.compile(r"/en/players/([a-f0-9]{8})/([A-Za-z0-9-]+)")
SEARCH_ITEM_RE = re.compile(
    r'<div class="search-item-name">\s*<a href="([^"]+)"[^>]*>([^<]+)</a>', re.S
)
def firecrawl_scrape(url: str, output: Path, fmt: str = "rawHtml") -> None:
    """Run firecrawl scrape and save to disk. Raises on non-zero exit."""
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [FIRECRAWL_BIN, "scrape", url, "--format", fmt, "--profile", "fbref", "-o", str(output)]
    print(f"  fetching {url}", flush=True)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0 or not output.exists() or output.stat().st_size < 1000:
        raise RuntimeError(
            f"firecrawl failed for {url}\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
    time.sleep(RATE_LIMIT_SECONDS)


def _normalize(s: str) -> str:
    """Casefold + strip diacritics + collapse non-alnum for fuzzy name match."""
    import unicodedata

    nfkd = unicodedata.normalize("NFKD", s)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", ascii_only.casefold())


def resolve_player(name: str) -> tuple[str, str]:
    """Search fbref for a player name, return (fbref_id, slug).

    Strategy:
    1. If the search redirects (canonical URL points to /en/players/...), use it.
    2. Otherwise fbref returned a results list. Look at search-item-name links.
       Pick the candidate whose visible name normalizes to the requested name.
       If multiple candidates match, raise — caller must hardcode the ID.
    """
    q = urllib.parse.quote_plus(name)
    search_html = HTML_DIR / "_search" / f"{name.replace(' ', '_')}.html"
    if not search_html.exists():
        firecrawl_scrape(f"{FBREF_BASE}/en/search/search.fcgi?search={q}", search_html)
    text = search_html.read_text(encoding="utf-8", errors="replace")

    canon = CANONICAL_RE.search(text)
    if canon and "/en/players/" in canon.group(1):
        url_match = PLAYER_URL_RE.search(canon.group(1))
        if url_match:
            return url_match.group(1), url_match.group(2)

    target = _normalize(name)
    candidates: list[tuple[str, str, str]] = []  # (fbref_id, slug, visible_name)
    for url, visible in SEARCH_ITEM_RE.findall(text):
        url_match = PLAYER_URL_RE.search(url)
        if not url_match:
            continue
        if _normalize(visible) == target:
            candidates.append((url_match.group(1), url_match.group(2), visible.strip()))

    if len(candidates) == 1:
        return candidates[0][0], candidates[0][1]

    # Show the user what was found and bail.
    all_items = [
        (PLAYER_URL_RE.search(u).group(1), v.strip())
        for u, v in SEARCH_ITEM_RE.findall(text)
        if PLAYER_URL_RE.search(u)
    ]
    msg = [f"Could not unambiguously resolve {name!r} on fbref."]
    if candidates:
        msg.append(f"  {len(candidates)} exact-name matches — disambiguate manually:")
        for cid, _slug, vis in candidates:
            msg.append(f"    {cid}  {vis}")
    else:
        msg.append("  No exact-name match. Top candidates:")
        for cid, vis in all_items[:6]:
            msg.append(f"    {cid}  {vis}")
    msg.append(f"  Edit {PLAYERS_JSON.name} and set fbref_id manually.")
    raise RuntimeError("\n".join(msg))


def fetch_player_html(fbref_id: str, slug: str) -> Path:
    out = HTML_DIR / f"{fbref_id}.html"
    if out.exists() and out.stat().st_size > 50_000:
        return out
    firecrawl_scrape(f"{FBREF_BASE}/en/players/{fbref_id}/{slug}", out)
    return out


SEASON_RE = re.compile(r"^\d{4}-\d{4}$")


def parse_league_goals_by_season(html_path: Path) -> dict[int, int]:
    """Return {end_of_season_year: league_goals} for one player.

    Sums across multiple league rows in the same season (e.g. Ronaldo 2022-23
    Manchester Utd + Al-Nassr both appear). Drops summary rows like
    'La Liga (9 Seasons)'.
    """
    tables = pd.read_html(str(html_path), attrs={"id": "stats_standard_dom_lg"})
    if not tables:
        raise RuntimeError(f"no stats_standard_dom_lg table in {html_path}")
    df = tables[0]

    # Flatten multi-index columns: ('Performance', 'Gls') -> 'Gls', etc.
    season_col = df.columns[0]  # ('Unnamed: 0_level_0', 'Season')
    gls_col = ("Performance", "Gls")
    if gls_col not in df.columns:
        # Some tables collapse to single-level when there's only one season.
        for c in df.columns:
            if isinstance(c, tuple) and c[-1] == "Gls":
                gls_col = c
                break

    out: dict[int, int] = {}
    for _, row in df.iterrows():
        season = str(row[season_col]).strip()
        if not SEASON_RE.match(season):
            continue  # skip 'La Liga (9 Seasons)' etc.
        try:
            goals = int(row[gls_col])
        except (TypeError, ValueError):
            continue
        end_year = int(season.split("-")[1])
        out[end_year] = out.get(end_year, 0) + goals
    return out


def main() -> int:
    blob = json.loads(PLAYERS_JSON.read_text(encoding="utf-8"))
    players = blob["players"]

    per_season: dict[str, dict[int, int]] = {}
    icon_ids: dict[str, str] = {}
    headshot_tracker = MissingTracker()

    dirty = False
    for entry in players:
        name = entry["display_name"]
        print(f"[{name}]")
        if not entry.get("fbref_id"):
            fbref_id, slug = resolve_player(name)
            entry["fbref_id"] = fbref_id
            entry["fbref_slug"] = slug
            dirty = True
            print(f"  resolved -> {fbref_id} / {slug}")
        else:
            fbref_id = entry["fbref_id"]
            slug = entry["fbref_slug"]

        html_path = fetch_player_html(fbref_id, slug)
        fetch_headshot(html_path, fbref_id, name, HEADSHOT_DIR, headshot_tracker)

        try:
            per_season[name] = parse_league_goals_by_season(html_path)
        except Exception as e:
            print(f"  parse failed: {e}")
            continue
        icon_ids[name] = fbref_id

    if dirty:
        PLAYERS_JSON.write_text(json.dumps(blob, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nUpdated {PLAYERS_JSON.name} with newly resolved IDs.")

    if not per_season:
        print("No data parsed.", file=sys.stderr)
        return 1

    all_years = sorted({y for d in per_season.values() for y in d})
    year_index = list(range(min(all_years), max(all_years) + 1))

    per_season_df = pd.DataFrame(0, index=year_index, columns=list(per_season.keys()), dtype=float)
    for player, season_goals in per_season.items():
        for year, g in season_goals.items():
            per_season_df.loc[year, player] = g

    # Cumulative: NaN before debut, then running total.
    debut = {p: min(d) for p, d in per_season.items()}
    cum_df = per_season_df.cumsum()
    for p, year in debut.items():
        cum_df.loc[cum_df.index < year, p] = pd.NA

    per_season_df.to_parquet(OUT_PER_SEASON_PARQUET)
    cum_df.to_parquet(OUT_PARQUET)

    print(f"\nWrote {OUT_PARQUET} ({cum_df.shape[0]} years x {cum_df.shape[1]} players)")
    print(f"Wrote {OUT_PER_SEASON_PARQUET}")
    print("\nLatest year top-10 cumulative league goals:")
    last = cum_df.iloc[-1].dropna().sort_values(ascending=False).head(10)
    for name, g in last.items():
        print(f"  {int(g):4d}  {name}  ({icon_ids[name]})")

    icon_path = CACHE_DIR / "icon_ids.json"
    icon_path.write_text(json.dumps(icon_ids, indent=2), encoding="utf-8")

    headshot_tracker.print_summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())
