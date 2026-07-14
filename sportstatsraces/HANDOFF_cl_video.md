# Handoff — Champions League Top Scorers video

Resume point for the `/make-sports-stats-video` work on the all-time CL top
scorers race. Work happens in the **sports worktree**:
`C:/Users/mvnmv/Documents/GitHub/wbr-sports` (branch `sports`). Confirm with
`git -C /c/Users/mvnmv/Documents/GitHub/wbr-sports rev-parse --abbrev-ref HEAD` → `sports`.

## What this video is
Cumulative career-goals chart race of every player who has ever been in the
all-time top 10 European Cup / Champions League scorers, season by season
1955→2025. 46 players. Leader trend line, real headshots, El Faraon narration.

## Key files
- Config: `sportstatsraces/config_cl_top_scorers.json`
- Data (dense pre-cumulated matrix): `sportstatsraces/data/cl_top_scorers.csv`
- Narration script: `sportstatsraces/cache/variants.json` (Claude-authored, no API)
- Static bg image: `stadium_bg_dark.png` (repo root, dark 9:16 floodlit pitch)
- Final output: `sportstatsraces/output/cl_top_scorers_narrated.mp4`
- Skill (all defaults documented here): `C:/Users/mvnmv/.claude/skills/make-sports-stats-video/SKILL.md`

## Renderer changes made (all in `races/render/renderer.py`, all GATED, default-off)
1. `retirement_exclude` (list) — players never flagged RETIRED even if their
   value stops rising (Messi/Ronaldo/Benzema left European football but active).
2. `background_image` (path) — static full-frame PNG behind the chart + header
   scrim. Mutually exclusive with `background_video`. **Skipped in preview
   frames** — only shows in the final render.
3. `trend_from_zero` (bool) — anchors trend y-axis to 0 baseline, draws a "0"
   origin mark at the left, paints a gold trail over the swept portion of the
   curve. Under `ordinal_periods` the endpoint labels auto-show calendar years
   (1955 / 2025) instead of the 0..N-1 ordinals (fix at the start_year/end_year
   assignment ~line 874).
4. `adaptive_pacing` + `adaptive_base` / `adaptive_gain` / `adaptive_min_frames`
   / `adaptive_max_frames` / `adaptive_anticipate` — spend frames proportional
   to visible top-N turbulence (only the top `top_n_on_screen` slots count).
   Anticipation = **single-segment lookahead** (only the one transition
   immediately before a shake-up braces; does NOT propagate back through frozen
   runs). See the `adaptive_pacing` block ~line 632-665.
   `interpolate_and_rank` in `big_movers.py` takes a `new_index=` param for the
   non-uniform frame index.

## Current pacing tuning (in config now)
```
"adaptive_base": 0.15, "adaptive_gain": 0.7,
"adaptive_anticipate": 0.4, "adaptive_min_frames": 1
```
This makes frozen years (e.g. 1994-97, zero top-10 change) get 1 frame each
(~0.03s, fly through), 1998 gets ~8 frames (one brace beat right before the
1999 surge), 1999-2004 expand to 20-36 frames.

History of the anticipation tuning (user feedback):
- 0.55 cascading = dragged ~4 pre-surge years, 90s too slow.
- 0.3 cascading = better but 90s still not fast enough.
- Switched to **single-segment lookahead** (from raw turbulence, no cascade)
  + `min_frames:1` + `anticipate:0.4` — this is the current, user-approved
  direction.

## PENDING — do this first
The config was just edited to `anticipate:0.4, min_frames:1` but the video was
**NOT yet re-rendered** (the render call was interrupted). Re-render:
```
cd /c/Users/mvnmv/Documents/GitHub/wbr-sports
PYTHONIOENCODING=utf-8 python run.py --channel sports \
  --config sportstatsraces/config_cl_top_scorers.json --generate-narration
```
Watch: `[adaptive-pacing]` line, `total≈` ≤ 47.0s, `[bg-image] static
background: stadium_bg_dark.png` present. Voice is 32.18s, total ~33.7s.

Then verify from the final mp4 (NOT preview frames — bg is skipped in preview):
extract frames around the 90s (should fly) and 2000s (should be slow). ffmpeg
binary: `~/AppData/Roaming/Python/Python314/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe`.

Diagnostic for frame-per-year allocation (no render needed) — a standalone
script pattern that pivots the CSV, computes top-10 turbulence, applies the
single-segment anticipation + normalization, and prints frames per year. Use
it to sanity-check pacing changes before a full render.

## Then — upload checkpoint (skill step 6)
Proposed:
- Title: `Champions League Top Scorers of ALL TIME 🏆 (1955 → 2025)`
- Description: `Every player who has ever cracked the all-time top 10 scorers
  of the European Cup / Champions League, raced season by season from 1955 to
  today. Sources: RSSSF, UEFA, Wikipedia. #ChampionsLeague #UCL #football`

Ask: **"Upload as a private draft to YouTube? (yes / no / re-roll idea)"**
- yes → `python run.py --channel sports --upload <narrated.mp4>`, report URL,
  then move all `output/cl_top_scorers*` artifacts into `output/uploaded/`.

## Notes / gotchas
- Console is cp1252 — prefix python with `PYTHONIOENCODING=utf-8` for accented
  player names.
- CSV player names are ASCII-ized where the font lacks glyphs (Kostic,
  Ibrahimovic, Milos Milutinovic).
- Narration variants are written by hand (no Anthropic API — user won't pay).
  Don't run `--generate-variants`.
- All renderer edits are gated so the world-stats channel is unaffected.
