---
name: make-sports-stats-video
description: End-to-end recipe to produce a new Sports-stats channel chart-race video for the WorldBankRaces pipeline. Picks a soccer-stat idea using MrBeast principles, edits sportstatsraces/config.json, runs a layout-check loop on preview frames, renders the mp4, and stops before upload to ask the user for permission. Triggers when the user asks to "make a new sports-stats video", "make a new sports video", "ship a sports-stats short", or invokes the skill by name.
---

# make-sports-stats-video

End-to-end automated recipe for the **Sports-stats** channel of the
WorldBankRaces pipeline. Operates `python run.py --channel sports`.

> **v1 limitation:** the sports pipeline's CLI surface (`run.py`) currently
> exposes only render + preview + validate-layout. Narration
> (`--generate-variants`, `--auto-assemble`, `--generate-narration`) and
> `--refetch` / `--extract-movers` are world-only. **v1 sports videos are
> music-only**, no LLM narration. If the user asks for narration, tell them
> the CLI doesn't expose it for sports yet and stop.

## Inputs you read

- `sportstatsraces/config.json` — current sports config (you will edit this)
- `../mrbeast_principles.md` — distilled principles for scoring decisions
- `../layout_check.md` — shared layout-check procedure
- The fbref scrapers under `sportstatsraces/scrapers/` — read their docstrings
  if you need to understand what stat domains are available

## Workflow

### 1. Pick the idea

There is no `ideas.md` for sports yet. Generate 3–5 candidate ideas spanning:

- **Player-vs-player races** (career goals, assists, MOTM, clean sheets,
  cards, minutes, age-vs-output curves)
- **Team-vs-team races** (titles, points-per-season, goals-for, derbies won)
- **Era-defined races** (Premier League era 1992+, Champions League era,
  post-Bosman 1995+)

Score each against `../mrbeast_principles.md`. Pick the highest-scoring
idea whose data is available via the existing `FbrefPLSource` (or a sibling
source if one has been added).

State to the user: "Selected `<title>` because <one-sentence reason tied
to the principles>." Also state which fbref data the run will need.

### 2. Edit sportstatsraces/config.json

Update `video_title`, `value_format`, `output_filename`, `theme`,
`source.parquet_path` / `meta_path` / `timeframe` / `top_n_keep`,
`trend_label`. Preserve all other keys.

If the chosen idea requires a parquet that doesn't exist yet, surface to
the user: "This idea needs a new fbref scrape (`<parquet_path>`). The
sports pipeline doesn't expose `--refetch` via the CLI — we need to either
add it or run the scraper directly. Stop?"

### 3. Layout-check loop

Follow `../layout_check.md`. Max 3 retries. Sports already enables
`auto_size_columns`, so name-box overflow is rare; the more common
failure is title length or trend-label overflow.

Also confirm the race has visible motion across the three preview frames
(top-N composition changes). If flat, surface to user.

### 4. Render the full video

```bash
python run.py --channel sports
```

Locate the output mp4 under `sportstatsraces/output/` or `output/`
(check both — the sports pipeline's output dir may differ).

### 5. Pre-upload checkpoint — STOP HERE

Show the user:

- Path to the rendered mp4
- Proposed title + description for upload
- Which idea was picked + one-line reason
- Any layout retries that happened (transparency)
- Reminder: **music-only, no narration** until the CLI exposes it

Ask: **"Upload as private draft to YouTube? (yes / no / re-roll idea)"**

- **yes** → run `python run.py --channel sports --upload <path-to-mp4>`
  and report the resulting video URL.
- **no** → stop. Leave the artifacts in place.
- **re-roll idea** → jump back to step 1.

## Failure modes — surface to user, don't paper over

- Required parquet doesn't exist (need a scrape that the CLI doesn't expose)
- Layout-check exhausts 3 retries
- Preview shows the dataset is too flat
- Render fails (ffmpeg / disk)

In every case: report what was tried, what the error was, and stop.

## What you do NOT do

- Do not auto-upload. The user always decides.
- Do not edit `sportstatsraces/` or `races/` source code. This skill only
  edits `sportstatsraces/config.json`.
- Do not fabricate fbref data. If a parquet is missing, surface it.
- Do not invent MrBeast principles. If `../mrbeast_principles.md` still has
  the placeholder header, tell the user.
