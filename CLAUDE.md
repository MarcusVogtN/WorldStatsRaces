# CLAUDE.md

This document defines what this project **is for** and what it **must do**.
It is the requirements baseline. Implementation details live in the code; do
not re-document them here.

A full audit of observed behaviors, drift, and deletion candidates lives in
`./post-dumb-minimized-audit.md`. Read it before adding new behavior.

---

## Purpose

### Pipeline purpose
A flexible automated chart-race video pipeline that adapts data sources, chart
styles, and per-video features to the data; ingests performance signals from
YouTube/X to refine future ideas and the pipeline itself; with the end goal of
generating passive revenue from viewership.

### Channels
Two channels share the pipeline. Each has its own audience and content
posture, but they ride on the same render engine, narration system, and
publishing flow.

**World-stats channel** — A YouTube/X channel of short-form videos turning
world data (economic, financial, geopolitical, demographic, environmental,
and beyond) into era-spanning country-vs-country (or entity-vs-entity) races,
leveraging historical context and "aha" shifts to retain a general
curious-viewer audience.

**Sports-stats channel** — A YouTube/X channel of short-form videos turning
soccer statistics, pulled from any suitable source across leagues,
competitions, and stat types, into player-vs-player (or team-vs-team) races,
leveraging era nostalgia, milestone moments, and ranking surprises to retain
a soccer-fan audience.

---

## Requirements baseline

### Shared render engine
1. Render value-weighted bar-chart races at 30fps with smoothstep-blended
   gliding rank transitions.
2. Support pluggable data sources via `DataSource` ABC and asset providers
   via `AssetProvider` ABC, so new domains can plug in without touching the
   render core.
3. Support multiple visual themes (currently `glass_dark`,
   `glass_dark_drift`, `glass_dark_black`).
4. Support a right-side "spotlight" callout for non-top-N entities with
   notable rate-of-change.
5. Support per-row sparklines, rank-change flash (green/red), rounded flag/
   headshot corners, and a header trend line.
6. Support per-row "rate" badges and "retired" flagging for monotonically
   non-decreasing series (opt-in; only meaningful for cumulative datasets).
7. Support typography control (global `font_scale` + per-section size/weight
   overrides). Defer aggressive simplification of this surface until the
   production template is locked.
8. Support intro animations (back-ease-out bounce on title, rows, trend line).
9. Auto-size the name-box per video to fit the longest entity that ever
   lands in the visible top-N (`races/render/layout.py::auto_size_columns`).

### Pipeline orchestration
10. Per-capita transform (divide indicator by population). World-stats only.
11. Accumulated/cumulative transform (`cumsum` after per-capita). World-stats
    only.
12. Single-frame and multi-frame PNG previews for fast layout iteration.
13. Refetch flag to redownload source data, flags, population (world-stats).
14. One channel-aware CLI: `python run.py --channel {world|sports}`. Defaults
    to `world`.

### World-stats data layer
15. Fetch world-stats indicators (initially World Bank via `wbgapi`; the
    architecture must accept additional sources without renderer changes).
16. Fetch flags from a CDN with 5:3 aspect normalization.

### Sports data layer
17. Scrape per-season soccer stats (initially fbref; must accept additional
    sources) with rate-limit + HTML cache. Resolve player IDs with
    disambiguation prompts on collisions.
18. Fetch and cache headshot images via a CDN proxy; run
    background-removal so headshots render cleanly on dark themes.

### Narration
19. Generate LLM scripts (Anthropic) with stat-pack + frame-keyed event
    timeline so phrasing aligns with what's on screen.
20. Generate one variant per beat (hook, middle, ending). On-demand re-rolls
    via `--regenerate-section`.
21. Synthesize TTS via ElevenLabs with per-clip SHA256 caching for cost
    control.
22. Mix background music with ducking under voice (ffmpeg).
23. Mux narration audio onto the rendered mp4 (ffmpeg copy).
24. Archive previous narration takes on every regeneration.
25. `--auto-assemble` writes `cache/narration.json` with `meta.source="auto"`,
    which the pipeline treats as a do-not-regenerate signal.

### Big-mover curation
26. Extract candidate big-mover events to `cache/big_movers.json` for review;
    render only events with `keep:true` when a curated file is configured.

### Posting and feedback (to be built)
27. Auto-post finished videos to YouTube and X.
28. Ingest YouTube/X performance metrics to refine future video ideas and
    pipeline parameters.

---

## Adding new behavior

Before adding a new behavior, run through these checks:

1. **Does it map to a baseline requirement above?** If not, you're about to
   add scope creep. Either justify it as a new requirement (and add it here),
   or don't build it.
2. **Does an existing requirement already cover it?** If yes, the work is
   tightening or extending the existing implementation, not adding a new one.
3. **Is it required by both channels, one channel, or shared
   infrastructure?** Shared work goes in `races/`. Channel-specific work goes
   in the channel's package.
4. **Does it require modifying the render engine to behave differently for
   one channel?** If yes, gate it behind a `render_cfg` flag with a default
   that preserves existing behavior, the way row-rate and retirement badges
   are gated.

## Auditing existing behavior

If you find behavior that looks suspicious (unused, never shipped, or no
clear requirement trace):

1. Map it to a requirement above. If you can't, it slipped past.
2. Name a concrete failure scenario if it were removed. If you can't, it
   slipped past.
3. If neither check passes, run `/post-dumb-minimizer` on the affected area
   to produce a fresh audit and deletion hit-list.

---

## Repo shape

```
worldbankraces/
├── run.py                    channel-aware CLI (world | sports)
├── config.json               world-stats config
├── ideas.md                  world-stats backlog
├── races/                    shared render engine + WB pipeline + narration
│   ├── pipeline.py           world-stats orchestrator
│   ├── render/               renderer, themes, layout, big-movers
│   ├── sources/              DataSource ABC + WorldBankSource
│   ├── assets/               AssetProvider ABC + flags + fonts + music
│   └── narration/            stats, timeline, script, TTS, mux
├── sportstatsraces/          sports channel
│   ├── pipeline.py           sports orchestrator (uses races/ render engine)
│   ├── config.json           sports-stats config
│   ├── sources/              FbrefPLSource (extendable)
│   ├── assets/               HeadshotProvider
│   └── scrapers/             fbref season + headshot scrapers
├── cache/                    gitignored — fetched data, fonts, narration takes
├── output/                   gitignored — rendered mp4s
└── post-dumb-minimized-audit.md   the live deletion hit-list
```
