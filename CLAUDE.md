# CLAUDE.md

This document defines what this project **is for** and what it **must do**.
It is the requirements baseline. Implementation details live in the code; do
not re-document them here.

A full audit of observed behaviors, drift, and deletion candidates lives in
`./post-dumb-minimized-audit.md` (and a follow-up autonomous re-audit in
`./auto-dumb-minimized-audit.md`). Read them before adding new behavior.

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
   lands in the visible top-N
   (`races/render/layout.py::auto_size_columns`). Both pipelines call it
   so long country names (e.g. "Bosnia and Herzegovina") and footballer
   rosters render without truncation.

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

    **Music-duration constraint:** the final narrated video may be **shorter
    than** the configured background music file, but must never be **longer**.
    The mix loops music when the video exceeds it, which sounds wrong —
    cap voice length (and therefore body length) so total = body +
    `tail_buffer_seconds` ≤ music duration. Shorter is fine; longer is a bug.

    The current background music
    (`races/assets/music/Bar_Chart_Race_Tension_2026-04-20T113611.mp3`) has
    been trimmed to **47.0s**. Keep narrated videos using this track ≤47s
    total (voice ≤ ~45.5s with the default 1.5s `tail_buffer_seconds`).
    Do NOT speed up voice with `atempo` to fit — generate a script short
    enough that natural-speed TTS lands inside the budget. If a script
    overruns, re-roll variants with a tighter word budget
    (lower `max_speech_coverage` in `render.narration`) rather than
    post-processing the audio.
20. Generate one variant per beat (hook, middle, ending) via
    `--generate-variants`. On-demand re-rolls via `--regenerate-section`.
21. Synthesize TTS via ElevenLabs with per-clip SHA256 caching for cost
    control.
22. Mix background music with ducking under voice (ffmpeg).
23. Mux narration audio onto the rendered mp4 (ffmpeg copy).
24. Archive previous narration takes on every regeneration.
25. `--auto-assemble` is the only supported way to produce a final
    `cache/narration.json`. It writes `meta.source="auto"`, picking option 0
    from each beat in `variants.json`. `--generate-narration` requires this
    file to exist and synthesizes TTS from it.

### Big-mover curation
26. Extract candidate big-mover events to `cache/big_movers.json` for review;
    render only events with `keep:true` when a curated file is configured.

    **Currently broken — do not curate.** The spotlight render path that
    surfaces curated events is disabled in both channel configs
    (`spotlight.enabled: false`) because the system is broken (see
    `post-dumb-minimized-audit.md`). Skills MUST skip the
    `--extract-movers` step and MUST NOT edit `cache/big_movers.json::keep`
    flags until the spotlight is fixed. Setting keeps today does nothing
    visible — it only adds noise to the narration timeline. The
    `make-world-stats-video` / `make-sports-stats-video` skills should
    proceed directly from layout-check to `--generate-variants`.

### Posting and feedback
27. Auto-post finished videos to YouTube via the Data API (`--upload`).
    v1 ships private-draft only: generated title/description from the
    render manifest, `madeForKids=false`, no thumbnail. You promote each
    draft to public manually in Studio. X is deferred. Auto-publish,
    thumbnails, and curated titles are explicit v2 scope — do not bolt
    them on without a separate design pass.
28. Ingest YouTube performance metrics into `cache/analytics.db` (SQLite)
    via the Data + Analytics APIs (`--pull-analytics`), and surface them
    via a markdown report (`--analytics-report`). Per-day metrics
    (views, watch time, AVD, AVP, likes/dislikes/comments/shares,
    subs gained/lost) plus retention curves snapshotted opportunistically
    at +7d, +30d, and once as backfill for older videos. Each rendered
    video writes an `output/<stem>.manifest.json` sidecar at render time
    so analytics rows can be attributed to a specific theme, dataset,
    and script variant.

    Explicitly **deferred** until a real corpus exists (≥30 videos with
    retention): LLM script-prompt injection of "what worked," ranking of
    `ideas.md`, and formal A/B testing. Earlier feedback loops on a small
    corpus actively mislead — don't add them without the corpus.

    **Shorts-only constraint:** YouTube Analytics doesn't expose
    `impressions`/`impressionClickThroughRate` for Shorts (no
    thumbnail-click model in the vertical feed), so neither channel
    captures CTR today. If a long-form channel is ever added, re-enable
    the lifetime-impressions query in `races/youtube/analytics.py`.

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

## Later

Known gaps that don't justify work today but should not be forgotten:

- **Sports `--refetch` plumbing.** `run.py --channel sports` doesn't yet
  expose a `--refetch` that re-runs the fbref scraper end-to-end. Today the
  scraper is invoked manually
  (`python -m sportstatsraces.scrapers.fetch_pl_seasons [--refresh-current]
  [--fetch-headshots]`). When the data cadence demands automation, wire a
  sports `--refetch` flag into the sports branch of `run.py::main` and the
  `sportstatsraces.pipeline.run` signature.
- **Sports-specific background music.** Sports videos currently reuse the
  world-stats track (`races/assets/music/Bar_Chart_Race_Tension_*.mp3`,
  trimmed to 47.0s) as placeholder. Source a stadium-drums / hype-builder
  track and point `sportstatsraces/config.json::render.narration.background_music.path`
  at it. Same 47s duration cap applies.
- **Sports spotlight.** Currently disabled in `sportstatsraces/config.json`
  (and in world-stats too, since the spotlight system is broken — see
  `post-dumb-minimized-audit.md`). Re-enable for sports only after the
  world-stats spotlight fix lands.

---

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
│   ├── narration/            stats, timeline, script, TTS, mux
│   └── youtube/              OAuth, upload, analytics ingest, report,
│                             render-time manifest sidecar
├── sportstatsraces/          sports channel
│   ├── pipeline.py           sports orchestrator (uses races/ render engine)
│   ├── config.json           sports-stats config
│   ├── sources/              FbrefPLSource (extendable)
│   ├── assets/               HeadshotProvider
│   ├── narration/            sports stat-pack + prompts (reuses races/
│   │                         narration script/voice/mux/assemble/timeline)
│   └── scrapers/             fbref season + headshot scrapers
├── cache/                    gitignored — fetched data, fonts, narration takes
│   ├── analytics.db          gitignored — SQLite store for YouTube metrics
│   └── youtube/              gitignored — OAuth client_secret + per-channel
│                             refresh tokens (credentials_world.json,
│                             credentials_sports.json)
├── output/                   gitignored — rendered mp4s + manifest sidecars
├── post-dumb-minimized-audit.md   the live deletion hit-list
└── .claude/skills/           Claude Code skills that operate this pipeline
    ├── make-world-stats-video/   end-to-end recipe for the world channel
    ├── make-sports-stats-video/  end-to-end recipe for the sports channel
    ├── mrbeast_principles.md     shared rubric used by both skills for
    │                             idea selection, big-mover curation, titles
    └── layout_check.md           shared preview-frame inspection procedure
```

The skills are end-to-end automation: they pick an idea, edit the
config, run the pipeline, loop on layout previews, auto-curate big-mover
events, generate narration, render — and **stop before upload** to ask the
user for permission. They never auto-publish. To add a new behavior to a
skill, edit the skill's `SKILL.md`; to change the creative judgment, edit
`mrbeast_principles.md`.
