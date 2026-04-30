# Fetch PL player headshots (top 500)

Reference for kicking off the Premier League headshot sweep capped at the top 500 all-time scorers. Covers ~99% of anyone the renderer will ever spotlight.

## Run it

```bash
python sportstatsraces_prototype/fetch_pl_seasons.py --fetch-headshots --headshots-limit 500
```

## What this does

1. Loads the existing `cache/fbref/pl_player_meta.json` (already built — no PL season scraping needed unless `--refresh-current` is passed).
2. Sorts players by career PL goals, takes the top 500.
3. For each player not already in `cache/fbref/headshots/`:
   - Fetches their fbref player page via Firecrawl (rate-limited 3.5 s, profile `fbref`).
   - Pulls the headshot via the unprotected `cdn.ssref.net/scripts/image_resize.cgi` proxy (200×200 JPEG).
4. Prints a "Missing headshots" summary at the end listing any player whose page didn't yield a headshot URL or whose proxy fetch failed.

## Time estimate

~7–8 seconds per uncached player. Top-500 → roughly **1 hour** end-to-end. Already-cached players are skipped instantly.

## Idempotent

Re-running is safe. Only missing headshots get fetched. To re-fetch a specific player, delete `cache/fbref/headshots/<fbref_id>.jpg` first.

## Output

- Headshots: `cache/fbref/headshots/<fbref_id>.jpg` (200×200 JPEG)
- Player pages (for the headshot URL parse + future stats reuse): `cache/fbref/html/<fbref_id>.html`

## If you want more

- Top 1000: `--headshots-limit 1000` (~2 hours)
- Everyone: drop `--headshots-limit` entirely (~10–12 hours)
