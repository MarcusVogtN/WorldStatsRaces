# Layout check — shared procedure

Used by both `make-world-stats-video` and `make-sports-stats-video` after
config edits, before committing to a full render.

## Goal

Catch text overflow, wrapping, and overlap (title clipping, name-box overflow,
spotlight collisions with rows, trend label running off) BEFORE spending
10–30 minutes on a full render.

## Procedure

1. **Pick 3 representative frames** spanning the configured `timeframe`:
   - Start: `timeframe[0] + 5` (skip pure-zero startup years)
   - Middle: midpoint of timeframe
   - End: `timeframe[1] - 1`

   If a curated big-mover event exists with high `score`, add its year as a
   4th frame (these often have a long entity name briefly visible).

2. **Render the previews:**
   ```bash
   python run.py --channel <world|sports> --preview-frames Y1,Y2,Y3[,Y4]
   ```
   PNGs land in `output/`. Read each one as an image.

3. **Inspect each frame visually.** Look for:
   - Title text wrapping or clipping the title region
   - Entity names overflowing the name box
   - Trend label running off the right edge
   - Spotlight callout overlapping any visible row
   - Value labels colliding with bar ends

4. **If any frame has a problem, adjust ONE knob** in the config:
   - Long entity names → enable `auto_size_columns` (already on for sports;
     world uses fixed columns by default)
   - Title overflow → shorten `video_title` (keep ≤45 chars), or drop
     `render.fonts.title.size_scale` by 0.05
   - Trend label overflow → shorten `trend_label`, or drop
     `render.fonts.header.size_scale` by 0.05
   - Spotlight collision → drop spotlight `min_screen_seconds` so it dismisses
     faster, or shrink `render.fonts.spotlight.size_scale` by 0.1
   - Generic crowding → drop `render.font_scale` by 0.05

   Change ONE thing per retry. Don't bundle.

5. **Re-render the same frames and re-inspect.**

6. **Max 3 retries.** If still broken after 3 attempts, stop and surface to
   the user: which frame(s) failed, which knobs you tried, what the residual
   problem looks like. Do not proceed to full render.

## Notes

- Preview frames render in seconds, not minutes — this loop is cheap.
- If the user has set `font_scale` deliberately for a stylistic reason, prefer
  shortening text over scaling fonts further down. When in doubt, propose both
  options and let the pre-upload checkpoint decide.
- `python run.py --validate-layout` prints column bounds without rendering —
  useful if a name-box overflow is suspected but not yet visible.
