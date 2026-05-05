---
name: make-world-stats-video
description: End-to-end recipe to produce a new World-stats channel chart-race video for the WorldBankRaces pipeline. Picks an idea from ideas.md using MrBeast principles, edits config.json, refetches data, runs a layout-check loop on preview frames, auto-curates big-mover events, generates narration variants and TTS, renders the final mp4, and stops before upload to ask the user for permission. Triggers when the user asks to "make a new world-stats video", "make a new world video", "ship a world-stats short", or invokes the skill by name.
---

# make-world-stats-video

End-to-end automated recipe for the **World-stats** channel of the
WorldBankRaces pipeline. Operates `python run.py --channel world`.

You decide everything — idea, config, big-mover curation, narration —
guided by `../mrbeast_principles.md`. You stop only at the pre-upload
checkpoint to ask the user whether to ship.

## Inputs you read

- `ideas.md` — backlog of dataset ideas with hooks
- `config.json` — current world-stats config (you will edit this)
- `../mrbeast_principles.md` — distilled principles for scoring decisions
- `../layout_check.md` — shared layout-check procedure

## Workflow

### 1. Pick the idea

Read `ideas.md` and `../mrbeast_principles.md`. Score each candidate idea
against the rubric in the principles file. Pick the highest-scoring idea
that hasn't already been shipped (check `output/` for existing mp4s and
`cache/analytics.db` if it exists).

Briefly state to the user: "Selected `<title>` (indicator `<code>`) because
<one-sentence reason tied to the principles>."

### 2. Edit config.json

Update the keys per `ideas.md` lines 96–105:
`source.indicator`, `source.timeframe`, `video_title`, `output_filename`,
`per_capita`, `accumulated`, `trend_label` (+ overrides), `value_format`.

Preserve all other keys exactly.

### 3. Refetch source data

```bash
python run.py --channel world --refetch
```

If this fails, surface the error and stop. Do not retry blindly.

### 4. Layout-check loop

Follow `../layout_check.md`. Max 3 retries. If layout still broken, stop and
surface to user.

After clean previews: also confirm the dataset is **not too flat** by
checking that the top-N composition differs across the three preview frames
(per `ideas.md` line 122). If two of three frames look identical, surface
to user — the idea may not have a watchable race.

### 5. Extract and auto-curate big-mover events

```bash
python run.py --channel world --extract-movers
```

Read `cache/big_movers.json`. Score each candidate event against the
principles file (drama, recognizability, surprise). Set `keep:true` on the
top events; aim for 3–6 kept events for a Short. Write the file back.

State to the user: "Curated <N> big-mover events: <one-line list of
years/entities>." (Just for transparency at the final checkpoint.)

### 6. Generate narration variants

```bash
python run.py --channel world --generate-variants
```

This writes `cache/variants.json` with one variant per beat (hook, middle,
ending). Review the option-0 picks.

**Hook clarity check (most important):** the hook MUST be a short, simple
question a 10-year-old understands, naming the TOPIC of the data — not
the chart mechanics. The question alone tells the viewer what's being
measured. Forbidden words in the hook: "bars", "chart", "race",
"leaderboard", "data", "ranking", "graph", "stats". Just ask about the
topic.

- ✅ "Which country has the most tourists?"
- ✅ "Which country spends the most money on its army?"
- ✅ "Which country has put the most CO2 into the air, ever?"
- ❌ "ok so each bar is a country racing yearly tourist arrivals…"
  (mentions bars, sounds like a label)
- ❌ "tell me why one of these countries is about to get cooked…"
  (vague — viewer doesn't know the topic)
- ❌ "today we look at tourism data" (formal, no stakes)

**10-year-old language everywhere:** the whole script — hook, middle,
ending — must use words a 10-year-old uses on the playground. "Money"
not "expenditure". "Got hit hard" not "experienced a sharp decline".
Two clauses per sentence max. If you'd need to define a word, use a
simpler one.

If the hook doesn't explain AND tease, re-roll just that section:

```bash
python run.py --channel world --regenerate-section hook
```

Same check applies to middle and ending — re-roll only if clearly off.
Don't burn re-rolls.

### 7. Auto-assemble narration

```bash
python run.py --channel world --auto-assemble
```

Writes `cache/narration.json` with `meta.source="auto"`.

### 8. Synthesize TTS, render to fit, mix and mux — one command

```bash
python run.py --channel world --generate-narration
```

This is now an end-to-end command. It:

1. Synthesizes the voice track via ElevenLabs (cached).
2. Measures the actual voice duration.
3. Re-computes `steps_per_year` so the animation length matches the voice
   duration, then sets `end_hold_seconds` to a small tail buffer
   (`render.narration.tail_buffer_seconds`, default 1.5s).
4. Renders the video at that fitted duration.
5. Mixes the voice with ducked background music to the same total length.
6. Muxes onto the mp4, writing `output/<stem>_narrated.mp4`.

The result is a video whose length is voice_duration + ~1.5s buffer —
no long silent music tail. Per CLAUDE.md §25, `--generate-narration`
requires `cache/narration.json` to already exist (which step 7 created).

**Tuning knobs** (in `config.json::render.narration`):
- `words_per_second` — controls how many words the LLM targets per second
  of speech window. Higher = denser script. Default 3.0.
- `max_speech_coverage` — fraction of the speech window to fill with
  words. Default 1.15 (slightly over the visual length, since the video
  adapts).
- `tts.speed` — ElevenLabs playback speed. Default 1.1 (slightly faster
  than neutral).
- `tail_buffer_seconds` — silent-tail length after voice ends. Default 1.5.

### 9. (Skip — step 8 already produced the final mp4)

Step 8 renders, mixes, and muxes in one shot. The final video lives at
`output/<stem>_narrated.mp4`. No separate render step is needed.

### 10. Pre-upload checkpoint — STOP HERE

Show the user:

- Path to the rendered mp4
- Title + description proposed for upload
- Which idea was picked + one-line reason
- Which big-mover events were curated
- Any layout retries that happened (transparency)

Ask: **"Upload as private draft to YouTube? (yes / no / re-roll <part>)"**

- **yes** → run `python run.py --channel world --upload <path-to-mp4>` and
  report the resulting video URL.
- **no** → stop. Leave the artifacts in place.
- **re-roll hook** / **re-roll middle** / **re-roll ending** → jump back
  to step 6 for that section, then resume.
- **re-roll big-movers** → jump back to step 5.
- **re-roll idea** → jump back to step 1.

## Failure modes — surface to user, don't paper over

- Refetch fails (API down, indicator deprecated)
- Preview shows the dataset is too flat
- Layout-check exhausts 3 retries
- TTS fails (ElevenLabs quota / network)
- Render fails (ffmpeg / disk)

In every case: report what was tried, what the error was, and stop.

## What you do NOT do

- Do not auto-upload. The user always decides.
- Do not edit `races/` source code. This skill only edits `config.json`,
  `cache/big_movers.json`, and `cache/variants.json` (via re-roll commands).
- Do not invent MrBeast principles. If `../mrbeast_principles.md` still has
  the placeholder header, tell the user — your output will be guesswork
  until they fill it.
