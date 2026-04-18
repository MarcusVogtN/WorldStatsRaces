# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Pipeline

Run the three steps in order:

```bash
python s1_world_bank_data.py   # fetch World Bank data → FINAL_BAR_CHART_RACE.csv + country_codes.json
python s2_get_flags.py         # download flag images → flags/
python s4_bar_chart_generator.py  # render animation → <output_filename>.mp4
```

Steps 1 and 2 only need to re-run when `config.json` changes (new indicator, new timeframe). Step 4 re-runs whenever config or rendering code changes.

## Dependencies

```bash
pip install wbgapi pycountry pandas requests urllib3 numpy matplotlib Pillow imageio[ffmpeg]
```

FFmpeg must be installed and on PATH for `animation.FFMpegWriter` to work.

## config.json fields

| Field | Purpose |
|---|---|
| `wb_indicator` | World Bank indicator code (e.g. `MS.MIL.XPND.CD`) |
| `timeframe` | `[start_year, end_year]` |
| `top_n_on_screen` | How many bars are visible at once |
| `value_format` | `"currency"` (prepends `$`) or anything else (plain number) |
| `color_theme` | Unused by renderer — color per country is hash-assigned from PALETTE |
| `background_color` | Hex color for the video background |
| `output_filename` | Output `.mp4` filename |

## Architecture notes

**TEST_MODE** in `s4_bar_chart_generator.py` (line ~430) is hardcoded to `(1980, 1990)` — a short year window for fast layout checks. Set it to `None` before a full render, otherwise only a ~10-year clip is produced.

**safe_filename()** is duplicated in `s2_get_flags.py` and `s4_bar_chart_generator.py`. Both must stay identical — s2 uses it to name downloaded PNG files, s4 uses it to load them. Any change to the regex must be applied to both.

**Color stability**: country colors are assigned by `int(md5(name)) % len(PALETTE)` so colors are consistent across re-renders even if the country list changes.

**Rank smoothing** in s4 uses two rolling-window passes (windows 11 and 15) over `STEPS_PER_YEAR=60` interpolated sub-frames per year. Adjusting these constants changes how snappy vs. smooth rank swaps appear.

**DISPLAY_NAMES** dict in s4 maps verbose World Bank country names to short on-screen labels (e.g. `"Russian Federation"` → `"Russia"`). Add entries here for any new country whose raw name is too long or awkward.

**Flag layout geometry**: flags are rendered with `ax.imshow(extent=...)` in data coordinates rather than `OffsetImage`, so text clearance calculations are exact. `AXES_W_PX` / `AXES_H_PX` constants (lines ~224-225) must stay in sync with `subplots_adjust` values above them.

**s3 does not exist** — the step numbering skips from s2 to s4 intentionally.
