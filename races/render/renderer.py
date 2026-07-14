"""Main rendering loop. Flag-racing layout for YouTube Shorts safe zones."""

import bisect
import sys
import subprocess
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.colors import hsv_to_rgb
from matplotlib.patches import FancyBboxPatch, Rectangle
import matplotlib.patheffects as pe
import imageio.plugins.ffmpeg as _ffmpeg_plugin

from ..util import format_value, display_name

from .theme import Theme, assign_colors
from .layout import (
    Columns, DEFAULT_COLUMNS, VerticalLayout,
    track_position, smoothstep,
)
from .big_movers import interpolate_and_rank, load_curated

plt.rcParams['animation.ffmpeg_path'] = _ffmpeg_plugin.get_exe()
sys.stdout.reconfigure(encoding='utf-8')


FIG_W_IN, FIG_H_IN = 10.8, 19.2
DPI = 100
FIG_W_PX = FIG_W_IN * DPI
FIG_H_PX = FIG_H_IN * DPI

AX_MARGIN = 0.02

SAFE_RIGHT = 0.86
SAFE_BOTTOM = 0.08   # just enough clearance for the source-credit line


def _prepare_bg_video_frames(video_path, n_frames, fps, work_dir):
    """Extract n_frames frames at `fps` from a background video, looping the
    source if it's shorter, cropped/scaled to fill the 1080x1920 frame. Returns
    the sorted list of extracted PNG paths. Used as a per-frame full-bleed
    backdrop the chart composites over (see render's update loop)."""
    import shutil
    work_dir = Path(work_dir)
    shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = _ffmpeg_plugin.get_exe()
    w, h = int(FIG_W_PX), int(FIG_H_PX)
    vf = (f"fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase,"
          f"crop={w}:{h}")
    cmd = [ffmpeg, '-y', '-stream_loop', '-1', '-i', str(video_path),
           '-vf', vf, '-frames:v', str(int(n_frames)),
           str(work_dir / 'bg_%05d.png')]
    subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=600)
    frames = sorted(work_dir.glob('bg_*.png'))
    if not frames:
        raise RuntimeError(f"bg-video extraction produced no frames: {video_path}")
    return frames


def _draw_background(ax, theme: Theme, *, frame_idx: int = 0, fps: int = 30,
                     n_frames_total: int = 1,
                     drift_period_frames: int | None = None):
    bg = theme.background
    if isinstance(bg, tuple) and bg[0] == 'gradient':
        _, c_top, c_bottom = bg
        top_rgb = np.array(_hex_to_rgb(c_top))
        bot_rgb = np.array(_hex_to_rgb(c_bottom))
        grad = np.linspace(0, 1, 256).reshape(-1, 1)
        img = bot_rgb[None, None, :] * (1 - grad[:, :, None]) + top_rgb[None, None, :] * grad[:, :, None]
        img = np.flipud(img)
        ax.imshow(img, extent=[0, 1, 0, 1], aspect='auto', zorder=-10,
                  origin='upper', interpolation='bilinear')
    elif isinstance(bg, tuple) and bg[0] in ('radial', 'radial_drift'):
        # 'radial':       ('radial', c_center, c_edge)
        # 'radial_drift': ('radial_drift', [c_1, c_2, ...], c_edge) — center
        #                 color smoothly cycles across the run; edge is fixed.
        if bg[0] == 'radial':
            _, c_center, c_edge = bg
            center_rgb = np.array(_hex_to_rgb(c_center))
        else:
            _, palette, c_edge = bg
            n = max(1, len(palette))
            # Period in frames: defaults to one full cycle across the video.
            period = drift_period_frames if drift_period_frames else max(1, n_frames_total)
            pos = (frame_idx / max(1, period)) * n
            i = int(pos) % n
            j = (i + 1) % n
            t_blend = pos - int(pos)
            # smoothstep so the transition between hues is non-linear.
            t_blend = t_blend * t_blend * (3 - 2 * t_blend)
            a = np.array(_hex_to_rgb(palette[i]))
            b = np.array(_hex_to_rgb(palette[j]))
            center_rgb = a * (1 - t_blend) + b * t_blend
        edge_rgb = np.array(_hex_to_rgb(c_edge))
        h, w = 540, 960  # 16:9 sampling; bilinear handles upscale
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        # Normalized offset from center in [-1, 1], aspect-aware so the falloff is an ellipse matching the frame.
        nx = (xx - (w - 1) / 2) / ((w - 1) / 2)
        ny = (yy - (h - 1) / 2) / ((h - 1) / 2)
        dist = np.sqrt(nx * nx + ny * ny)
        # Smooth falloff: lighter (t=0) in center, dark (t=1) past the corners.
        t = np.clip(dist / 1.25, 0.0, 1.0)
        t = t * t * (3 - 2 * t)  # smoothstep
        img = center_rgb[None, None, :] * (1 - t[:, :, None]) + edge_rgb[None, None, :] * t[:, :, None]
        ax.imshow(img, extent=[0, 1, 0, 1], aspect='auto', zorder=-10,
                  origin='upper', interpolation='bilinear')
    else:
        ax.set_facecolor(bg)


def _draw_music_visualizer(ax, theme: Theme, *, frame_idx: int, fps: int,
                           cfg: dict | None):
    """Procedural equalizer backdrop behind the race — a row of bars whose
    heights bounce with a pseudo-beat, so a music video reads as musical.
    Gated: absent/disabled cfg draws nothing (other channels unaffected)."""
    if not cfg or not cfg.get('enabled'):
        return
    import math
    n = int(cfg.get('bars', 48))
    max_h = float(cfg.get('max_height', 0.5))
    base_alpha = float(cfg.get('alpha', 0.10))
    speed = float(cfg.get('speed', 1.0))
    bpm = float(cfg.get('bpm', 120.0))
    mirror_top = bool(cfg.get('mirror_top', False))
    top_scale = float(cfg.get('top_scale', 0.6))
    # Explicit colours (music-vibe neon) override the muted artist palette.
    palette = list(cfg.get('colors') or theme.accent_palette) or ['#ffffff']
    t = (frame_idx / max(1, fps)) * speed
    # Global beat: a pulse that scales every bar together, ~bpm.
    beat = 0.6 + 0.4 * abs(math.sin(math.pi * (t * bpm / 60.0)))
    gap_frac = 0.30
    bar_w = 1.0 / n
    for i in range(n):
        p = i / max(1, n - 1)
        # Two layered sines with per-bar phase → uncorrelated bouncing.
        a = math.sin(2 * math.pi * (0.7 * t + p * 3.1)) * 0.5 + 0.5
        b = math.sin(2 * math.pi * (1.3 * t + p * 5.7 + 0.4)) * 0.5 + 0.5
        amp = 0.6 * a + 0.4 * b
        # Center-weighted envelope so it looks like a spectrum (bass mid).
        env = 1.0 - 0.5 * abs(p - 0.5) * 2
        h = max_h * (0.12 + 0.88 * amp) * env * beat
        x = i * bar_w + bar_w * gap_frac / 2
        w = bar_w * (1 - gap_frac)
        color = palette[i % len(palette)]
        ax.add_patch(Rectangle((x, 0.0), w, h, facecolor=color,
                               edgecolor='none', alpha=base_alpha, zorder=-5))
        if mirror_top:
            # A second, phase-shifted row hanging from the top edge so the
            # visualizer frames the whole screen.
            a2 = math.sin(2 * math.pi * (0.9 * t + p * 4.3 + 1.7)) * 0.5 + 0.5
            h2 = max_h * top_scale * (0.12 + 0.88 * a2) * env * beat
            ax.add_patch(Rectangle((x, 1.0 - h2), w, h2, facecolor=color,
                                   edgecolor='none', alpha=base_alpha,
                                   zorder=-5))


def _hex_to_rgb(hx: str) -> tuple:
    hx = hx.lstrip('#')
    return tuple(int(hx[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _rounded_rect(ax, x, y, w, h, *, radius_px, fig_w_px, facecolor, alpha,
                  edgecolor='none', zorder=1):
    r = radius_px / fig_w_px
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={r}",
        linewidth=0, edgecolor=edgecolor,
        facecolor=facecolor, alpha=alpha, zorder=zorder,
    )
    ax.add_patch(patch)
    return patch


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * float(np.clip(t, 0.0, 1.0))


# ── Streak-effect helpers (win-streak fire / rainbow row cards) ──────────
_FIRE_LUT = None


def _fire_lut() -> np.ndarray:
    """256-entry RGBA float LUT: transparent → deep red → orange → yellow →
    near-white, with alpha ramping up with heat."""
    global _FIRE_LUT
    if _FIRE_LUT is None:
        i = np.arange(256, dtype=float)
        stops = [0, 50, 110, 170, 220, 255]
        r = np.interp(i, stops, [0.0, 0.45, 0.85, 1.0, 1.0, 1.0])
        g = np.interp(i, stops, [0.0, 0.02, 0.18, 0.55, 0.85, 1.0])
        b = np.interp(i, stops, [0.0, 0.00, 0.02, 0.05, 0.25, 0.85])
        a = np.clip((i / 255.0) ** 1.1 * 1.05, 0.0, 1.0)
        _FIRE_LUT = np.stack([r, g, b, a], axis=1)
    return _FIRE_LUT


def _fire_step(buf: np.ndarray, burning: bool) -> None:
    """One tick of the classic Doom-fire propagation. Heat rises from the
    bottom source row with random decay + lateral jitter. `burning=False`
    cuts the source so the flames die out naturally."""
    h, w = buf.shape
    buf[-1, :] = 255.0 if burning else 0.0
    decay = np.random.randint(2, 11, size=(h - 1, w))
    shift = np.random.randint(-1, 2, size=(h - 1, w))
    cols = (np.arange(w)[None, :] + shift) % w
    src = buf[1:, :][np.arange(h - 1)[:, None], cols]
    buf[:-1, :] = np.clip(src - decay, 0.0, 255.0)


def _fire_rgba(buf: np.ndarray) -> np.ndarray:
    return _fire_lut()[buf.astype(np.uint8)]


def _edge_feather(h: int, w: int, fx: float, fy: float) -> np.ndarray:
    """h×w mask: 1 in the middle, smoothly fading to 0 at the borders.
    fx/fy are the feather widths as fractions of each dimension."""
    wx = np.clip(np.minimum(np.arange(w), np.arange(w)[::-1])
                 / max(w * fx, 1.0), 0.0, 1.0)
    hy = np.clip(np.minimum(np.arange(h), np.arange(h)[::-1])
                 / max(h * fy, 1.0), 0.0, 1.0)
    m = np.outer(hy, wx)
    return m * m * (3.0 - 2.0 * m)   # vectorized smoothstep


def _rainbow_rgba(w: int, frame: int, h: int = 32,
                  sat: float = 0.55) -> np.ndarray:
    """h×w×4 glassmorphic scrolling rainbow: soft pastel hues frosted toward
    white, a glass sheen along the top, and a travelling shine band."""
    x = np.arange(w) / max(w - 1, 1)
    hue = (x * 1.2 + frame * 0.03) % 1.0
    hsv = np.stack([hue, np.full(w, sat), np.ones(w)], axis=-1)
    rgb = np.tile(hsv_to_rgb(hsv[None, :, :]), (h, 1, 1))
    # Frosted-glass: lift everything toward white, extra sheen up top.
    rgb = rgb + (1.0 - rgb) * 0.18
    yy = np.linspace(0.0, 1.0, h)[:, None, None]
    sheen = np.exp(-((yy - 0.12) / 0.18) ** 2) * 0.32
    rgb = rgb + (1.0 - rgb) * sheen
    # Travelling white shine band.
    c = (frame * 0.022) % 1.4 - 0.2
    band = np.exp(-((x - c) / 0.10) ** 2)[None, :, None] * 0.55
    rgb = rgb + (1.0 - rgb) * band
    alpha = np.ones((h, w, 1))
    return np.concatenate([rgb, alpha], axis=2)


def _round_image_corners(img: np.ndarray, radius_frac: float = 0.12) -> np.ndarray:
    """Apply rounded-corner alpha mask to RGBA image. radius_frac is fraction of short side."""
    if img.ndim != 3 or img.shape[2] != 4:
        return img
    h, w = img.shape[:2]
    r = max(1, int(round(min(h, w) * radius_frac)))
    mask = np.ones((h, w), dtype=np.float32)

    # Build corner masks using distance-to-corner-center
    yy, xx = np.ogrid[:h, :w]
    # Top-left
    corners = [
        (r, r, yy < r, xx < r),
        (r, w - 1 - r, yy < r, xx > w - 1 - r),
        (h - 1 - r, r, yy > h - 1 - r, xx < r),
        (h - 1 - r, w - 1 - r, yy > h - 1 - r, xx > w - 1 - r),
    ]
    for cy, cx, my, mx in corners:
        region = my & mx
        dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
        # Smooth 1-pixel edge
        a = np.clip(r + 0.5 - dist, 0.0, 1.0)
        mask = np.where(region, np.minimum(mask, a), mask)

    out = img.copy()
    out[..., 3] = (out[..., 3].astype(np.float32) * mask).astype(np.uint8)
    return out


def _draw_title_year_trend(ax, theme: Theme, title: str, year_int: int,
                            t_ease: float, *,
                            trend_series: Optional[np.ndarray],
                            trend_pos: Optional[float],
                            trend_label: str,
                            start_year: Optional[int] = None,
                            end_year: Optional[int] = None,
                            t_title: float = 1.0,
                            t_draw: float = 1.0,
                            total_value: Optional[float] = None,
                            value_format: str = '',
                            value_suffix: str = '',
                            title_scale_fs: float = 1.0,
                            title_weight='bold',
                            header_scale_fs: float = 1.0,
                            header_weight='black',
                            now_playing: Optional[str] = None,
                            header_template: str = '',
                            header_timeline: bool = False,
                            timeline_label: str = 'AGE {year}',
                            timeline_endpoints: Optional[tuple] = None,
                            timeline_pop: bool = True,
                            header_y_offset: float = 0.0,
                            year_frac: Optional[float] = None,
                            year_display: Optional[str] = None):
    """Title card + (label-card | year-card) row + wide borderless trend line.

    `now_playing`, when set, draws a small "song at #1 right now" caption in the
    gap under the centered year card (no-trend layout only). Default None keeps
    the existing layout untouched.
    """
    if ' (' in title:
        main = title.split(' (', 1)[0]
    else:
        main = title

    alpha = t_ease

    # Display string for the current period. Defaults to the integer period
    # (str(year_int)); a channel can override via render.period_labels to show
    # e.g. "JAN 2025" for a month-indexed dataset. year_int itself is kept as
    # the int for photo/sublabel lookups — only the on-screen label changes.
    yd = year_display if year_display is not None else str(year_int)

    # Back-ease-out bounce for the title: overshoots above 1.0 then settles.
    tt = float(np.clip(t_title, 0.0, 1.0))
    c1 = 1.70158
    c3 = c1 + 1.0
    title_scale = 1.0 + c3 * (tt - 1) ** 3 + c1 * (tt - 1) ** 2
    # Start slightly shrunk so the pop reads clearly.
    title_scale = 0.35 + title_scale * 0.65

    title_cx = 0.5
    title_cy = 0.915

    # Timeline header: static title on top, then a start→end age track with a
    # sliding dot, yellow progress fill, and a big age number riding above the
    # dot that pops on every integer tick. Gated — only used when a channel
    # sets render.header_timeline. Needs year_frac + start/end for the dot.
    if header_timeline and year_frac is not None and \
            start_year is not None and end_year is not None and end_year > start_year:
        accent = theme.text_primary
        line = header_template or title
        ax.text(title_cx, 0.955 - header_y_offset, line.upper(),
                transform=ax.transAxes, ha='center', va='center',
                color=theme.text_primary,
                fontsize=26 * title_scale * title_scale_fs, fontweight=title_weight,
                alpha=1.0, fontfamily=theme.font_family, zorder=3)

        track_y = 0.878 - header_y_offset
        track_x0, track_x1 = 0.17, 0.83
        frac = float(np.clip((year_frac - start_year) / (end_year - start_year), 0.0, 1.0))
        dot_x = track_x0 + frac * (track_x1 - track_x0)

        # Track: dim full line + accent progress fill up to the dot.
        ax.plot([track_x0, track_x1], [track_y, track_y],
                transform=ax.transAxes, color=theme.text_secondary,
                linewidth=3, alpha=0.25 * alpha, zorder=2,
                solid_capstyle='round')
        ax.plot([track_x0, dot_x], [track_y, track_y],
                transform=ax.transAxes, color=accent,
                linewidth=3, alpha=alpha, zorder=2, solid_capstyle='round')
        ax.scatter([dot_x], [track_y], transform=ax.transAxes,
                   s=140, color=accent, alpha=alpha, zorder=3,
                   edgecolors='none')

        # Endpoint age labels just outside the track.
        _ep = timeline_endpoints or (int(start_year), int(end_year))
        for x, ha, v in ((track_x0 - 0.025, 'right', _ep[0]),
                         (track_x1 + 0.025, 'left', _ep[1])):
            ax.text(x, track_y, str(v),
                    transform=ax.transAxes, ha=ha, va='center',
                    color=theme.text_secondary,
                    fontsize=18 * header_scale_fs, fontweight=header_weight,
                    alpha=0.8 * alpha, fontfamily=theme.font_family, zorder=3)

        # Big age number above the dot; pops (scale bounce) right after each
        # integer tick, driven by the fractional progress into the current age.
        if timeline_pop:
            age_prog = year_frac - np.floor(year_frac)
            pop_t = float(np.clip(age_prog / 0.15, 0.0, 1.0))
            pop_scale = 1.0 + 0.45 * (1.0 - smoothstep(pop_t))
        else:
            pop_scale = 1.0
        num_x = float(np.clip(dot_x, 0.12, 0.88))
        ax.text(num_x, track_y + 0.033,
                timeline_label.replace('{year}', yd),
                transform=ax.transAxes, ha='center', va='center',
                color=accent,
                fontsize=34 * pop_scale * title_scale * header_scale_fs,
                fontweight=header_weight,
                alpha=alpha, fontfamily=theme.font_family, zorder=3)
        return

    # Combined title+period header: one centered line (e.g. "GOALS AT 18 YEARS
    # OLD") with the live period substituted in. Replaces both the standalone
    # title and the year card, freeing vertical room for the race. Gated — only
    # used when a channel sets render.header_template.
    if header_template:
        line = header_template.replace('{age}', yd).replace('{period}', yd)
        ax.text(title_cx, title_cy, line.upper(),
                transform=ax.transAxes, ha='center', va='center',
                color=theme.text_primary,
                fontsize=36 * title_scale * title_scale_fs, fontweight=title_weight,
                alpha=1.0, fontfamily=theme.font_family, zorder=3)
        return

    ax.text(title_cx, title_cy, main.upper(),
            transform=ax.transAxes, ha='center', va='center',
            color=theme.text_primary,
            fontsize=44 * title_scale * title_scale_fs, fontweight=title_weight,
            alpha=1.0, fontfamily=theme.font_family, zorder=3)

    # Header row above the trend line: label card (left) + year card (right).
    if trend_series is None:
        # Fallback: keep a centered year card if there's no trend line.
        year_card_w = 0.28
        year_card_h = 0.065
        year_card_x = 0.5 - year_card_w / 2
        year_card_y = 0.810
        if theme.title_card:
            _rounded_rect(
                ax, year_card_x, year_card_y, year_card_w, year_card_h,
                radius_px=24, fig_w_px=FIG_W_PX,
                facecolor=theme.title_card_color,
                alpha=theme.title_card_opacity * alpha, zorder=2,
            )
        ax.text(0.5, year_card_y + year_card_h / 2, yd,
                transform=ax.transAxes, ha='center', va='center',
                color=theme.text_primary,
                fontsize=52 * header_scale_fs, fontweight=header_weight,
                alpha=alpha, fontfamily=theme.font_family, zorder=3)
        if now_playing:
            ax.text(0.5, 0.790, 'NOW AT #1',
                    transform=ax.transAxes, ha='center', va='center',
                    color=theme.text_secondary,
                    fontsize=20 * header_scale_fs, fontweight=header_weight,
                    alpha=0.85 * alpha, fontfamily=theme.font_family, zorder=3)
            song_fs = 35 if len(now_playing) <= 30 else 28
            ax.text(0.5, 0.755, now_playing,
                    transform=ax.transAxes, ha='center', va='center',
                    color=theme.text_primary,
                    fontsize=song_fs * header_scale_fs, fontweight=header_weight,
                    alpha=alpha, fontfamily=theme.font_family, zorder=3)
        return

    header_y = 0.850
    header_h = 0.042

    # Trend label (no card) — "TREND:" prefix in secondary color, label in primary.
    # Shares the same back-ease-out bounce as the main title (title_scale) so
    # these header elements pop in rather than appearing full-size.
    label_x = 0.070
    label_y = header_y + header_h / 2
    prefix = 'TREND: '
    # matplotlib warns on zero-size text; floor scale to a tiny positive value.
    header_scale = max(title_scale, 1e-3)
    ax.text(label_x, label_y, prefix,
            transform=ax.transAxes, ha='left', va='center',
            color=theme.text_secondary,
            fontsize=16 * header_scale * header_scale_fs, fontweight=header_weight,
            alpha=0.9, fontfamily=theme.font_family, zorder=3)
    ax.text(label_x + 0.095, label_y, trend_label.upper(),
            transform=ax.transAxes, ha='left', va='center',
            color=theme.text_primary,
            fontsize=21 * header_scale * header_scale_fs, fontweight=header_weight,
            alpha=1.0, fontfamily=theme.font_family, zorder=3)

    # Live total on the right side of the header row.
    if total_value is not None and np.isfinite(total_value):
        ax.text(0.930, label_y, format_value(float(total_value), value_format).upper() + (' ' + value_suffix if value_suffix else ''),
                transform=ax.transAxes, ha='right', va='center',
                color=theme.text_primary,
                fontsize=26 * header_scale * header_scale_fs, fontweight=header_weight,
                alpha=1.0, fontfamily=theme.font_family, zorder=3)

    # Trend line — wide, no background card. Sits closer to the flag race;
    # the TREND header above stays in place.
    plot_x0 = 0.070
    plot_x1 = 0.930
    plot_y0 = 0.755
    plot_y1 = 0.815

    ys = trend_series.astype(float)
    ymin = float(np.nanmin(ys)) if np.isfinite(np.nanmin(ys)) else 0.0
    ymax = float(np.nanmax(ys)) if np.isfinite(np.nanmax(ys)) else 1.0
    if ymax <= ymin:
        ymax = ymin + 1.0
    n = len(ys)
    xs_frac = np.linspace(0.0, 1.0, n)
    line_x = plot_x0 + xs_frac * (plot_x1 - plot_x0)
    line_y = plot_y0 + (ys - ymin) / (ymax - ymin) * (plot_y1 - plot_y0)

    td = float(np.clip(t_draw, 0.0, 1.0))
    # Ease-out cubic for a smooth "draw-in" sweep from left to right.
    td_eased = 1.0 - (1.0 - td) ** 3
    draw_end = max(2, int(round(td_eased * n)))

    # Vertical back-ease-out bounce around the baseline — same curve as the title.
    _pop = 1.0 + c3 * (tt - 1) ** 3 + c1 * (tt - 1) ** 2
    trend_pop = 0.35 + _pop * 0.65
    line_y_pop = plot_y0 + (line_y - plot_y0) * trend_pop
    ax.plot(line_x[:draw_end], line_y_pop[:draw_end],
            color=theme.text_primary, linewidth=1.6,
            alpha=0.75, zorder=3, solid_capstyle='round')

    # Current-position indicator
    if trend_pos is not None:
        tp = float(np.clip(trend_pos, 0.0, 1.0))
        idx = int(round(tp * (n - 1)))
        dot_x = line_x[idx]
        dot_y = line_y_pop[idx]
        guide_top = plot_y0 + (plot_y1 - plot_y0) * trend_pop
        # Vertical guide
        ax.plot([dot_x, dot_x], [plot_y0, guide_top],
                color=theme.text_primary, linewidth=1.0,
                alpha=0.35, zorder=3)
        ax.plot([dot_x], [dot_y], marker='o', markersize=7,
                color=theme.text_primary, markeredgewidth=0,
                alpha=1.0, zorder=4)

        # Current year floats above the indicator, tracking dot_x smoothly.
        # Instead of flipping ha=left/center/right at the plot edges (which
        # snapped visibly), use ha='left' with a clamped x so the text
        # visually centers over dot_x but slides to stay inside [plot_x0, plot_x1].
        year_str = yd
        year_fs = 24 * header_scale_fs
        year_text_w = len(year_str) * year_fs * 0.68 / FIG_W_PX
        year_x = dot_x - year_text_w / 2
        year_x = max(plot_x0, min(plot_x1 - year_text_w, year_x))
        ax.text(year_x, guide_top + 0.008, year_str,
                transform=ax.transAxes, ha='left', va='bottom',
                color=theme.text_primary, fontsize=year_fs, fontweight=header_weight,
                alpha=1.0, fontfamily=theme.font_family, zorder=4)

    if start_year is not None:
        ax.text(plot_x0, plot_y0 - 0.012, str(start_year),
                transform=ax.transAxes, ha='left', va='top',
                color=theme.text_secondary,
                fontsize=17 * header_scale_fs, fontweight=header_weight,
                alpha=0.85, fontfamily=theme.font_family, zorder=3)
    if end_year is not None:
        ax.text(plot_x1, plot_y0 - 0.012, str(end_year),
                transform=ax.transAxes, ha='right', va='top',
                color=theme.text_secondary,
                fontsize=17 * header_scale_fs, fontweight=header_weight,
                alpha=0.85, fontfamily=theme.font_family, zorder=3)


# Spotlight card geometry (axes fractions). Spans rows 7-10's y band on the
# right side; flags of rows 7-10 cluster near track_left (smaller values), so
# the card has real estate to the right without colliding. Kept inside
# SAFE_RIGHT so social-button overlays stay clear.
SPOTLIGHT_X = 0.575
SPOTLIGHT_Y = 0.115
SPOTLIGHT_W = 0.245
SPOTLIGHT_H = 0.140


def _draw_spotlight(ax, theme: Theme, *, country: str, display_name_str: str,
                    rank_int: int, value: float, icon, alpha: float,
                    label_text: str, subtext: str, value_format: str,
                    spot_scale_fs: float = 1.0,
                    spot_weight=1000):
    """Vertical stack: banner, name, [subtext], centered flag, value. Rank pinned top-right."""
    if alpha <= 0.0:
        return
    x, y, w, h = SPOTLIGHT_X, SPOTLIGHT_Y, SPOTLIGHT_W, SPOTLIGHT_H

    # Glass card
    if theme.row_card:
        _rounded_rect(
            ax, x, y, w, h,
            radius_px=theme.row_card_corner_radius_px,
            fig_w_px=FIG_W_PX,
            facecolor=theme.row_card_color,
            alpha=theme.row_card_opacity * alpha, zorder=4,
        )

    pad = 0.010
    cx = x + w / 2

    # Banner (top)
    banner_h = 0.026
    banner_y = y + h - banner_h - pad * 0.2
    ax.text(cx, banner_y + banner_h / 2, label_text,
            transform=ax.transAxes, ha='center', va='center',
            color=theme.text_secondary,
            fontsize=14 * spot_scale_fs, fontweight=spot_weight,
            alpha=0.9 * alpha, fontfamily=theme.font_family, zorder=5)

    # Rank pinned to top-right of card.
    ax.text(x + w - pad, banner_y + banner_h / 2, f'#{rank_int}',
            transform=ax.transAxes, ha='right', va='center',
            color=theme.text_primary,
            fontsize=18 * spot_scale_fs, fontweight=spot_weight,
            alpha=alpha, fontfamily=theme.font_family, zorder=5)

    # Name (centered, directly under banner).
    name_label = display_name_str.upper()
    if len(name_label) > 16:
        name_label = name_label[:15] + '…'
    name_y = banner_y - 0.010
    ax.text(cx, name_y, name_label,
            transform=ax.transAxes, ha='center', va='top',
            color=theme.text_primary,
            fontsize=20 * spot_scale_fs, fontweight=spot_weight,
            alpha=alpha, fontfamily=theme.font_family, zorder=5)

    # Subtext (optional, under name).
    has_subtext = bool(subtext)
    subtext_y = name_y - 0.024
    if has_subtext:
        ax.text(cx, subtext_y, subtext.upper(),
                transform=ax.transAxes, ha='center', va='top',
                color=theme.text_secondary,
                fontsize=14 * spot_scale_fs, fontweight=spot_weight,
                alpha=0.9 * alpha, fontfamily=theme.font_family, zorder=5)

    # Value (bottom, centered).
    value_y = y + pad * 0.4 + 0.002
    ax.text(cx, value_y, format_value(value, value_format).upper(),
            transform=ax.transAxes, ha='center', va='bottom',
            color=theme.text_primary,
            fontsize=22 * spot_scale_fs, fontweight=spot_weight,
            alpha=alpha, fontfamily=theme.font_family, zorder=5)

    # Flag centered between name/subtext and value.
    flag_top = (subtext_y - 0.008) if has_subtext else (name_y - 0.010)
    flag_bot = value_y + 0.005
    flag_box_h = max(0.02, flag_top - flag_bot)
    flag_cy = (flag_top + flag_bot) / 2
    flag_cx = cx
    if icon is not None and flag_box_h > 0:
        ih, iw = icon.shape[0], icon.shape[1]
        # Fit within both a max width and the available height.
        max_flag_w = w - 2 * pad - 0.020
        draw_h = flag_box_h
        draw_w = draw_h * (iw / ih) * (FIG_H_PX / FIG_W_PX)
        if draw_w > max_flag_w:
            draw_w = max_flag_w
            draw_h = draw_w * (ih / iw) * (FIG_W_PX / FIG_H_PX)
        draw_h *= 0.70
        draw_w *= 0.70
        fx = flag_cx - draw_w / 2
        fy = flag_cy - draw_h / 2
        img = icon
        if alpha < 1.0:
            img = img.copy()
            img[..., 3] = (img[..., 3] * alpha).astype(np.uint8)
        ax.imshow(img, extent=[fx, fx + draw_w, fy, fy + draw_h],
                  origin='upper', aspect='auto', zorder=5, clip_on=False)


def _weighted_row_position(display_rank_target: float,
                            all_ranks: np.ndarray,
                            all_weights: np.ndarray,
                            *,
                            race_top: float,
                            race_height: float,
                            total_weight_norm: float) -> tuple:
    """y_center and slot height for a country, using smoothstep-blended
    cumulative weight of all other countries above it by fractional rank."""
    # Fraction of each other country that sits above this one.
    # Input to smoothstep: (dr_target - dr_other) + 0.5, clamped to [0,1].
    # = 1 when other is clearly above; 0 when below; 0.5 when tied.
    u = np.clip((display_rank_target - all_ranks) + 0.5, 0.0, 1.0)
    fracs = u * u * (3 - 2 * u)  # smoothstep
    # Exclude self (where dr_other == dr_target exactly — they contribute 0.5,
    # we want 0). Simplest: the self term's fraction is 0.5 * its own weight,
    # which we subtract out.
    cum_above = float(np.sum(fracs * all_weights))
    return cum_above


def render(data: pd.DataFrame,
           *,
           load_icon,
           title: str,
           value_format: str,
           source_credit: str,
           theme: Theme,
           output_path: Path,
           render_cfg: dict,
           columns: Columns = DEFAULT_COLUMNS,
           preview_timeframe: Optional[tuple] = None,
           single_frame_year: Optional[float] = None,
           single_frame_png_path: Optional[Path] = None,
           single_frame_years: Optional[list] = None,
           single_frames_dir: Optional[Path] = None) -> None:

    n_on_screen = render_cfg.get('top_n_on_screen', 10)
    steps_per_year = render_cfg.get('steps_per_year', 60)
    fps = render_cfg.get('fps', 30)
    bitrate = render_cfg.get('bitrate', 8000)
    smooth_a = render_cfg.get('rank_smooth_window_a', 25)
    smooth_b = render_cfg.get('rank_smooth_window_b', 35)
    row_min_weight = render_cfg.get('row_min_weight', 0.35)
    layout_baseline = float(render_cfg.get('value_layout_baseline', 0.0) or 0.0)
    show_total_trend = render_cfg.get('show_total_trend', True)
    trend_label = render_cfg.get('trend_label', 'Total — all countries')
    flag_corner_radius_frac = render_cfg.get('flag_corner_radius_frac', 0.14)
    value_suffix = str(render_cfg.get('value_suffix', '') or '')
    show_zero_values = bool(render_cfg.get('show_zero_values', False))
    intro_style = str(render_cfg.get('intro_style', '') or '')
    # >1 speeds up all intro reveals (title, track, row cascade) by that
    # factor; default 1.0 keeps existing timing on other channels/configs.
    intro_speed = float(render_cfg.get('intro_speed', 1.0) or 1.0)
    row_gap = render_cfg.get('row_gap', 0.008)
    name_max_chars = int(render_cfg.get('name_max_chars', 22))
    show_row_rate = bool(render_cfg.get('show_row_rate', False))
    show_retirement = bool(render_cfg.get('show_retirement', False))
    row_rate_window_years = float(render_cfg.get('row_rate_window_years', 1.0))
    row_rate_label = str(render_cfg.get('row_rate_label', '/SZN'))
    # 'absolute' keeps the "+N/SZN" cumulative badge; 'percent' shows signed
    # window-over-window growth ("+23%" green / "-12%" red) for level series;
    # 'delta' shows the signed absolute change over the window ("+2" / "-1")
    # for level series with small point scales (e.g. player ratings).
    row_rate_style = str(render_cfg.get('row_rate_style', 'absolute'))
    row_retired_label = str(render_cfg.get('row_retired_label', 'RETIRED'))
    now_playing_timeline = render_cfg.get('now_playing_timeline') or None
    _np_fracs = [e[0] for e in now_playing_timeline] if now_playing_timeline else None
    # How many seasons of zero growth before flagging retirement. Guards
    # against marking still-active entities whose interpolated current season
    # happens to be flat at the very end of the dataset.
    row_retired_dead_seasons = float(render_cfg.get('row_retired_dead_seasons', 1.5))

    race_top = render_cfg.get('race_top', 0.72 if show_total_trend else 0.78)
    race_bottom = render_cfg.get('race_bottom', 0.11)

    vertical = VerticalLayout(
        race_top=race_top,
        race_bottom=race_bottom,
        n_on_screen=n_on_screen,
    )
    race_height = vertical.race_height

    # Ordinal periods: give every source period (e.g. each World Cup) equal
    # screen time regardless of calendar gaps, and snap the displayed year to
    # the period the bars are racing toward. Gated — default keeps the
    # calendar-proportional behavior.
    ordinal_periods = bool(render_cfg.get('ordinal_periods', False))
    period_years = None
    if ordinal_periods:
        period_years = [int(round(float(y))) for y in data.index]
        data = data.copy()
        data.index = pd.Index(np.arange(len(period_years), dtype=float),
                              name=data.index.name)

    # Optional period int -> display string map (e.g. {202501: "JAN 2025"}) so a
    # month-indexed race shows real dates on the ticker. Default: str(int).
    _period_labels = {int(k): str(v)
                      for k, v in (render_cfg.get('period_labels') or {}).items()}

    def _plabel(v):
        return _period_labels.get(int(round(float(v))), str(int(round(float(v)))))

    print('Preparing frames...')
    scores_df, ranks_df = interpolate_and_rank(
        data, steps_per_year, smooth_a, smooth_b,
        invert=bool(render_cfg.get('invert_ranking', False)))
    invert_ranking = bool(render_cfg.get('invert_ranking', False))
    country_colors = assign_colors(data.columns, theme.accent_palette)

    # Per-row rate ("goals over the last N steps") and retirement detection.
    # Both are derived from the smoothed scores_df and only consulted when the
    # corresponding render_cfg flag is on.
    rate_window_steps = max(1, int(round(row_rate_window_years * steps_per_year)))
    if show_row_rate:
        if row_rate_style == 'percent':
            rate_df = (scores_df.pct_change(rate_window_steps) * 100.0
                       ).replace([np.inf, -np.inf], np.nan)
        elif row_rate_style == 'delta':
            rate_df = scores_df.diff(rate_window_steps)
        else:
            rate_df = scores_df.diff(rate_window_steps).clip(lower=0)
    else:
        rate_df = None

    if show_retirement:
        # An entity "retires" the first frame after which their cumulative
        # value never increases again. Detected via the last frame where the
        # forward diff is meaningfully positive. If they're still scoring at
        # the very last frame, they are not flagged.
        retirement_frame: dict = {}
        eps = 1e-4
        n_frames_total_pre = len(scores_df)
        min_dead_steps = max(1, int(round(row_retired_dead_seasons * steps_per_year)))
        for c in scores_df.columns:
            v = scores_df[c].fillna(0).to_numpy(dtype=float)
            if v.size < 2 or v.max() <= 0:
                retirement_frame[c] = 10**9
                continue
            d = np.diff(v)
            incr = np.where(d > eps)[0]
            if incr.size == 0:
                retirement_frame[c] = 10**9
            elif incr[-1] >= n_frames_total_pre - min_dead_steps:
                retirement_frame[c] = 10**9
            else:
                # Wait one rate-window before flagging so the badge doesn't
                # pop the instant a player goes scoreless mid-season.
                retirement_frame[c] = int(incr[-1]) + 1 + rate_window_steps
    else:
        retirement_frame = None

    # ── Background animation (radial-drift only) ─────────────────────────
    bg_anim_cfg = render_cfg.get('background_animation', {}) or {}
    drift_period_seconds = bg_anim_cfg.get('drift_period_seconds')
    drift_period_frames = (int(float(drift_period_seconds) * fps)
                           if drift_period_seconds else None)
    music_visualizer_cfg = render_cfg.get('music_visualizer') or None
    _bg_cache: dict = {}

    total_countries = len(data.columns)

    # Precompute total-trend series. By default it's Σ across countries per
    # frame. In per-capita mode the pipeline injects a precomputed yearly
    # worldwide-per-capita series (Σ raw / Σ pop) into render_cfg under
    # `_world_trend_yearly`; we re-interpolate it onto the frame index so the
    # trend reflects the global per-person average rather than a sum of
    # per-capita values across mismatched country sizes.
    if show_total_trend:
        world_yearly = render_cfg.get('_world_trend_yearly')
        if world_yearly is not None:
            ws = pd.Series(world_yearly).copy()
            ws.index = ws.index.astype(float)
            trend_series = (
                ws.reindex(ws.index.union(scores_df.index))
                  .sort_index()
                  .interpolate('linear')
                  .reindex(scores_df.index)
                  .ffill()
                  .bfill()
                  .to_numpy()
            )
        else:
            trend_series = scores_df.fillna(0).sum(axis=1).to_numpy()
    else:
        trend_series = None

    # ── Spotlight (right-side callout for significant non-top-N mover) ──
    spotlight_cfg = render_cfg.get('spotlight', {}) or {}
    spotlight_enabled = bool(spotlight_cfg.get('enabled', False))
    spotlight_deltas = None
    spotlight_signed_deltas = None
    rate_window_years = float(spotlight_cfg.get('rate_window_years', 3)) if spotlight_cfg else 3.0
    spotlight_threshold = 0.0  # absolute |Δvalue| floor, computed from data
    spotlight_min_screen_frames = int(
        float(spotlight_cfg.get('min_screen_seconds', 2.0)) * fps)
    spotlight_fade_frames = int(spotlight_cfg.get('fade_frames', 12))
    spotlight_label_text = str(spotlight_cfg.get('label', 'BIG MOVER')).upper()
    # How strongly a challenger must outscore the current pick to trigger an
    # early switch (before min_screen_seconds elapses). Higher = stickier.
    spotlight_switch_ratio = float(spotlight_cfg.get('switch_ratio', 2.0))
    # Curated mode: if a curated_file is configured and parses, skip the
    # percentile scoring and drive the spotlight straight from the kept list.
    spotlight_curated: list = []
    curated_file_raw = spotlight_cfg.get('curated_file')
    if spotlight_enabled and curated_file_raw:
        curated_path = Path(curated_file_raw)
        if not curated_path.is_absolute():
            curated_path = Path.cwd() / curated_path
        if curated_path.exists():
            spotlight_curated = load_curated(curated_path)
            print(f"Spotlight curated mode · {len(spotlight_curated)} kept event(s) "
                  f"from {curated_path}")
        else:
            print(f"[spotlight] curated_file {curated_path} not found — "
                  "falling back to auto-selection.")

    if spotlight_enabled and not spotlight_curated:
        rate_window_years = float(spotlight_cfg.get('rate_window_years', 3))
        rate_window_frames = max(1, int(rate_window_years * steps_per_year))
        spotlight_signed_deltas = scores_df.diff(periods=rate_window_frames)
        spotlight_deltas = spotlight_signed_deltas.abs()
        # Dataset-wide threshold: only the top (100 - percentile)% of all
        # |Δvalue| observations across every country/frame ever qualify. This
        # keeps the callout reserved for genuinely huge moves instead of
        # firing on mid-level fluctuations in every era.
        percentile = float(spotlight_cfg.get('percentile', 99.7))
        flat = spotlight_deltas.to_numpy().ravel()
        flat = flat[np.isfinite(flat) & (flat > 0)]
        if flat.size > 0:
            spotlight_threshold = float(np.percentile(flat, percentile))
        # Legacy absolute floor (raw |Δ|). If set, take the max of the two.
        min_abs = spotlight_cfg.get('min_abs_delta')
        if min_abs is not None:
            spotlight_threshold = max(spotlight_threshold, float(min_abs))
        print(f"Spotlight enabled · percentile={percentile} threshold=|Δ|≥{spotlight_threshold:,.0f}")

    # Per-country normalized history for in-row sparklines. Default plots
    # the value curve; 'rank' plots table position instead (1.0 = 1st place,
    # 0.0 = last), so ups and downs in the standings show directly.
    country_hist: dict = {}
    if str(render_cfg.get('sparkline_source', 'value')) == 'rank':
        # ranks_df counts up toward the top of the display (largest rank
        # number = 1st place), so higher rank maps straight to card top.
        _n_ent = max(2, len(scores_df.columns))
        for c in scores_df.columns:
            r = ranks_df[c].fillna(1.0).to_numpy(dtype=float)
            country_hist[c] = np.clip(
                (r - 1.0) / (_n_ent - 1.0), 0.0, 1.0)
    else:
        for c in scores_df.columns:
            vals = scores_df[c].fillna(0).to_numpy(dtype=float)
            vmax = float(np.nanmax(vals)) if len(vals) else 0.0
            country_hist[c] = vals / vmax if vmax > 0 else vals
    spark_x0 = columns.name_box_left + 0.010
    spark_x1 = columns.name_box_right - 0.010
    spark_xs_full = np.linspace(spark_x0, spark_x1, len(scores_df))

    # Flag cache with rounded corners applied. With yearly_icons the
    # provider serves a different image per period (load(name, year)),
    # so the cache key includes the year.
    yearly_icons = bool(render_cfg.get('yearly_icons', False))
    flag_cache: dict = {}

    def get_flag(country, year=None):
        key = (country, year) if yearly_icons else country
        if key in flag_cache:
            return flag_cache[key]
        icon = load_icon(country, year) if yearly_icons else load_icon(country)
        if icon is not None and flag_corner_radius_frac > 0:
            icon = _round_image_corners(icon, flag_corner_radius_frac)
        flag_cache[key] = icon
        return icon

    fig = plt.figure(figsize=(FIG_W_IN, FIG_H_IN), dpi=DPI)
    fig.patch.set_facecolor('#000000')
    ax = fig.add_axes([AX_MARGIN, 0.0, 1.0 - 2 * AX_MARGIN, 1.0])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    # Global font scale: multiplies every fontsize=... arg passed to ax.text.
    fs_scale = float(render_cfg.get('font_scale', 1.0))
    if fs_scale != 1.0:
        _orig_text = ax.text
        def _scaled_text(*args, **kw):
            fs = kw.get('fontsize')
            if fs is not None:
                kw['fontsize'] = max(1e-3, float(fs) * fs_scale)
            return _orig_text(*args, **kw)
        ax.text = _scaled_text

    # Per-section font specs (size scale + weight). Stack on top of font_scale.
    fonts_cfg = render_cfg.get('fonts', {}) or {}
    def _spec(section, default_weight):
        s = fonts_cfg.get(section, {}) or {}
        return float(s.get('size_scale', 1.0)), s.get('weight', default_weight)
    title_scale_fs, title_weight = _spec('title', 'bold')
    header_scale_fs, header_weight = _spec('header', 'black')
    row_scale_fs, row_weight = _spec('row', 'bold')
    spot_scale_fs, spot_weight = _spec('spotlight', 1000)

    # Streak effects (gated; e.g. win-streak fire/rainbow on season-table
    # races). Config: render.streak_effects = {path, fire_min, star_min}.
    # The JSON at `path` maps entity -> {period: streak}.
    # Optional per-config override of the theme's row-card glass fill (e.g.
    # darker cards over a bright video background). Defaults keep the theme.
    _card_color = render_cfg.get('row_card_color') or theme.row_card_color
    _card_opacity = float(render_cfg.get('row_card_opacity',
                                         theme.row_card_opacity))

    _sfx_cfg = render_cfg.get('streak_effects') or {}
    _sfx_map: dict = {}
    if _sfx_cfg:
        import json as _json
        _sfx_map = _json.loads(Path(_sfx_cfg['path']).read_text(encoding='utf-8'))
        _sfx_fire_min = int(_sfx_cfg.get('fire_min', 4))
        _sfx_star_min = int(_sfx_cfg.get('star_min', 6))

    state = {
        'frame': 0,
        'prev_int_rank': {},
        'flash_start': {},
        'flash_color': {},
        'spotlight_target': None,
        'spotlight_adopted_frame': -10**9,
        'spotlight_prev': None,
        'spotlight_prev_start': -10**9,
        'spotlight_active_label': None,
        'spotlight_prev_label': None,
        'spotlight_active_subtext': '',
        'spotlight_prev_subtext': '',
    }

    start_year = int(float(data.index.min()))
    end_year = int(float(data.index.max()))

    n_frames_total = len(scores_df)

    # Optional full-frame video background: extract (looping) frames to match
    # the animation length, then paint each behind the chart per frame.
    bg_frame_paths = None
    bg_video = render_cfg.get('background_video')
    _is_single = single_frame_year is not None or bool(single_frame_years)
    # Optional static full-frame image background (same scrim treatment as
    # the video path, no per-frame extraction). Takes precedence over
    # background_video when both are set.
    bg_image = None
    bg_image_path = render_cfg.get('background_image')
    if bg_image_path:
        bgi = Path(bg_image_path)
        if not bgi.is_absolute():
            bgi = Path.cwd() / bgi
        if not bgi.exists():
            raise SystemExit(f"background_image not found: {bgi}")
        bg_image = plt.imread(str(bgi))
        bg_video = None
        # Full-bleed: paint on a dedicated axes spanning the whole figure so
        # the image also covers the AX_MARGIN strips left/right of the chart
        # axes. Drawn once — it persists across ax.clear() calls in update().
        _bg_ax = fig.add_axes([0.0, 0.0, 1.0, 1.0], zorder=-1)
        _bg_ax.axis('off')
        _bg_ax.imshow(bg_image, extent=[0, 1, 0, 1], aspect='auto')
    if bg_video and not _is_single:
        bgv = Path(bg_video)
        if not bgv.is_absolute():
            bgv = Path.cwd() / bgv
        if not bgv.exists():
            raise SystemExit(f"background_video not found: {bgv}")
        print(f"[bg-video] extracting {n_frames_total} frames from {bgv.name} ...")
        bg_frame_paths = _prepare_bg_video_frames(
            bgv, n_frames_total, fps, output_path.parent / '.bg_frames')
        print(f"[bg-video] {len(bg_frame_paths)} frames ready.")

    def update(frame_idx):
        ax.clear()
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        if bg_image is not None or bg_frame_paths is not None:
            if bg_frame_paths is not None:
                bi = frame_idx if frame_idx < len(bg_frame_paths) else len(bg_frame_paths) - 1
                ax.imshow(plt.imread(str(bg_frame_paths[bi])),
                          extent=[0, 1, 0, 1], aspect='auto', zorder=-10)
            # Dark scrim over the header zone so title/age/track stay legible
            # when the video background is bright (e.g. stadium floodlights).
            # Solid over the header, fading out just below it.
            scrim = np.zeros((120, 1, 4), dtype=np.float32)
            ys = np.linspace(1.0, 0.80, 120)  # row 0 = top of extent
            solid_until, fade_until = 0.855, 0.80
            scrim[..., 3] = (0.88 * np.clip(
                (ys - fade_until) / (solid_until - fade_until), 0.0, 1.0))[:, None]
            ax.imshow(scrim, extent=[0, 1, 0.80, 1.0], aspect='auto',
                      origin='upper', zorder=-9, interpolation='bilinear')
        else:
            _draw_background(ax, theme, frame_idx=frame_idx, fps=fps,
                             n_frames_total=n_frames_total,
                             drift_period_frames=drift_period_frames)
        _draw_music_visualizer(ax, theme, frame_idx=frame_idx, fps=fps,
                               cfg=music_visualizer_cfg)

        scores = scores_df.iloc[frame_idx]
        ranks = ranks_df.iloc[frame_idx]
        if period_years is not None:
            # Snap to the period the bars are racing toward (ceil), so the
            # standings match the label exactly when each transition settles.
            _i = int(np.ceil(float(scores_df.index[frame_idx]) - 1e-6))
            year_int = period_years[max(0, min(_i, len(period_years) - 1))]
        else:
            year_int = int(float(scores_df.index[frame_idx]))

        max_val = float(scores.max())
        if not np.isfinite(max_val) or max_val <= 0:
            return
        # Effective values for layout (weight + track position). Subtracting
        # a baseline compresses tightly-clustered datasets (e.g. heights
        # 160-184cm) so bar widths and row heights show visible variation.
        # In invert mode the baseline is the upper clip and eff = baseline - v
        # (smaller original values produce larger bars). Display values
        # are unchanged in either mode.
        if invert_ranking:
            min_val = float(scores.min())
            eff_max = max(layout_baseline - min_val, 1e-9)

            def eff(v: float) -> float:
                if not np.isfinite(v):
                    return 0.0
                return max(layout_baseline - v, 0.0)
        else:
            eff_max = max(max_val - layout_baseline, 1e-9)

            def eff(v: float) -> float:
                if not np.isfinite(v):
                    return 0.0
                return max(v - layout_baseline, 0.0)

        state['frame'] += 1
        _if = state['frame'] * intro_speed  # intro clock (sped-up frame count)
        t_ease = smoothstep(min(1.0, _if / 50))
        t_title = min(1.0, _if / 18)
        t_draw = min(1.0, _if / 55)

        # Same back-ease-out bounce used for the title, applied to each race row.
        _tt = float(np.clip(t_title, 0.0, 1.0))
        _c1 = 1.70158
        _c3 = _c1 + 1.0
        _bounce = 1.0 + _c3 * (_tt - 1) ** 3 + _c1 * (_tt - 1) ** 2
        race_intro_scale = 0.35 + _bounce * 0.65

        trend_pos = (frame_idx / max(1, n_frames_total - 1)) if show_total_trend else None
        current_total = float(trend_series[frame_idx]) if trend_series is not None else None
        now_playing = None
        if now_playing_timeline:
            _i = bisect.bisect_right(_np_fracs,
                                     float(scores_df.index[frame_idx])) - 1
            if _i >= 0:
                now_playing = now_playing_timeline[_i][1]
        _draw_title_year_trend(ax, theme, title, year_int, t_ease,
                                trend_series=trend_series,
                                trend_pos=trend_pos,
                                trend_label=trend_label,
                                start_year=start_year,
                                end_year=end_year,
                                t_title=t_title,
                                t_draw=t_draw,
                                total_value=current_total,
                                value_format=value_format,
                                value_suffix=value_suffix,
                                title_scale_fs=title_scale_fs,
                                title_weight=title_weight,
                                header_scale_fs=header_scale_fs,
                                header_weight=header_weight,
                                now_playing=now_playing,
                                header_template=render_cfg.get('header_template', ''),
                                header_timeline=bool(render_cfg.get('header_timeline', False)),
                                timeline_label=render_cfg.get('timeline_label', 'AGE {year}'),
                                timeline_endpoints=((_plabel(period_years[0]),
                                                     _plabel(period_years[-1]))
                                                    if period_years else None),
                                timeline_pop=bool(render_cfg.get('timeline_pop', True)),
                                header_y_offset=float(render_cfg.get('header_y_offset', 0.0)),
                                year_frac=float(scores_df.index[frame_idx]),
                                year_display=_plabel(year_int))

        ax.text(0.04, SAFE_BOTTOM - 0.02, source_credit.upper(),
                transform=ax.transAxes, ha='left', va='bottom',
                color=theme.text_secondary, fontsize=10,
                alpha=0.5, fontfamily=theme.font_family, zorder=3)

        # ── Visible countries by smoothed fractional display rank ───────────
        display_ranks_all = {c: total_countries - r + 1
                             for c, r in zip(ranks.index, ranks.values)}

        # Per-country weight (value/max, floored).
        def weight_of(c):
            v = float(scores[c])
            if not np.isfinite(v) or v <= 0:
                return row_min_weight
            return max(row_min_weight, eff(v) / eff_max)

        # Normalization denominator: the *true* top-N by smoothed rank, drawn
        # from all countries (not the entry-fade subset). Slicing top_n out of
        # an already-filtered visible set caused a one-frame count mismatch
        # whenever a country's smoothed dr flickered across the visibility
        # threshold (e.g. Canada around 1991), which rescaled every row.
        true_top_n = sorted(display_ranks_all.keys(),
                            key=lambda c: display_ranks_all[c])[:n_on_screen]
        w_norm = sum(weight_of(c) for c in true_top_n) or 1.0

        # Keep countries within entry-fade band (dr <= n_on_screen + 1.2). The
        # small extra margin keeps a rank-crossing country drawn through its
        # transition so rows 8-10 don't visibly re-stack.
        visible = [c for c, dr in display_ranks_all.items()
                   if dr <= n_on_screen + 1.2]
        if not visible:
            return

        weights = {c: weight_of(c) for c in visible}

        # Equal inter-row gaps: distribute card heights proportional to weight
        # over (race_height - n_on_screen * row_gap); gap itself is constant.
        avail_for_cards = max(race_height - n_on_screen * row_gap, race_height * 0.5)
        card_scale = avail_for_cards / w_norm
        max_card_h_render = max(weights.values()) * card_scale

        # Slot numbers: enumerate visible rows by smoothed rank so the displayed
        # number matches the physical row order (unique 1..N, no collisions).
        # Gated by render.slot_rank_numbers; default keeps int(round(dr)) which
        # can collide/skip during a swap on sparse or tie-heavy datasets.
        slot_of = {c: i + 1 for i, c
                   in enumerate(sorted(visible, key=lambda c: display_ranks_all[c]))}

        visible_ranks = np.array([display_ranks_all[c] for c in visible])
        visible_weights = np.array([weights[c] for c in visible])
        # Per-country total vertical footprint (card + one gap) used for y-placement.
        visible_footprint = visible_weights * card_scale + row_gap

        for country in visible:
            dr = display_ranks_all[country]
            weight = weights[country]
            value = float(scores[country])

            # Smoothstep-blended vertical footprint above this country.
            u = np.clip((dr - visible_ranks) + 0.5, 0.0, 1.0)
            fracs = u * u * (3 - 2 * u)
            y_center = race_top - float(np.sum(fracs * visible_footprint))

            # Intro reveal: 'cascade' staggers each row in top-to-bottom with a
            # smooth ease-out cubic (no overshoot); default keeps the uniform
            # back-ease bounce so the world channel is unchanged.
            if intro_style == 'cascade':
                _p = np.clip((_if - (dr - 1.0) * 3.5) / 16.0, 0.0, 1.0)
                _p = 1.0 - (1.0 - _p) ** 3
                this_intro_scale = 0.70 + 0.30 * _p
                intro_alpha = _p
            else:
                this_intro_scale = race_intro_scale
                intro_alpha = 1.0

            card_h_i = weight * card_scale * this_intro_scale
            slot_h = card_h_i + row_gap

            entry_alpha = float(np.clip((n_on_screen + 0.5) - dr, 0.0, 1.0))
            if total_countries <= n_on_screen:
                # Every entity fits on screen, so nothing scrolls past the
                # bottom edge — don't entry-fade the last row.
                entry_alpha = 1.0
            entry_alpha *= intro_alpha
            int_rank = int(round(dr))
            s = card_h_i / max_card_h_render if max_card_h_render > 0 else 1.0
            # Alpha weight: lower rows dim with `s` by default. With
            # row_fade disabled, hold text/rank at full opacity (font size
            # still scales with `s`).
            alpha_s = s if render_cfg.get('row_fade', True) else 1.0

            # Rank-change flash
            if theme.rank_flash and entry_alpha >= 0.95:
                prev_r = state['prev_int_rank'].get(country)
                if prev_r is not None and prev_r != int_rank:
                    state['flash_start'][country] = state['frame']
                    state['flash_color'][country] = (
                        '#22c55e' if int_rank < prev_r else '#ef4444'
                    )
                state['prev_int_rank'][country] = int_rank
            flash_alpha = 0.0
            if theme.rank_flash and country in state['flash_start']:
                dt = state['frame'] - state['flash_start'][country]
                flash_alpha = max(0.0, 1.0 - dt / 20.0)

            color = country_colors.get(country, theme.accent_palette[0])
            flash_color = state['flash_color'].get(country, color)

            # Glass name box
            card_h = card_h_i
            card_y = y_center - card_h / 2
            name_box_x = columns.name_box_left
            name_box_w = columns.name_box_right - columns.name_box_left
            # Optional: stretch the card to the row's icon so name and icon
            # read as one connected bar. Gated — default keeps the fixed-width
            # card. True stretches per row; "uniform" gives every row the same
            # right edge (just past where the leader's icon lands), so all
            # cards align while icons stay value-proportional inside them.
            _box_mode = render_cfg.get('row_box_to_icon', False)
            if _box_mode == 'uniform':
                name_box_w = (columns.track_right + 0.008) - name_box_x
            elif _box_mode:
                # Pre-computes the icon geometry used again further down
                # (get_flag is memoized, so the early call is free).
                _icon_pre = get_flag(country, year_int)
                if _icon_pre is not None:
                    _pih, _piw = _icon_pre.shape[0], _icon_pre.shape[1]
                    _pdw = (card_h_i * 0.96) * (_piw / _pih) * (FIG_H_PX / FIG_W_PX)
                else:
                    _pdw = 0.0
                _pfx = track_position(
                    eff(value), eff_max,
                    columns.track_left, columns.track_right, _pdw)
                name_box_w = max(name_box_w,
                                 (_pfx + _pdw + 0.008) - name_box_x)
            if theme.row_card:
                _rounded_rect(
                    ax, name_box_x, card_y, name_box_w, card_h,
                    radius_px=theme.row_card_corner_radius_px,
                    fig_w_px=FIG_W_PX,
                    facecolor=_card_color,
                    alpha=_card_opacity * entry_alpha, zorder=2,
                )
            if flash_alpha > 0:
                _rounded_rect(
                    ax, name_box_x, card_y, name_box_w, card_h,
                    radius_px=theme.row_card_corner_radius_px,
                    fig_w_px=FIG_W_PX,
                    facecolor=flash_color,
                    alpha=0.28 * flash_alpha * entry_alpha, zorder=2.5,
                )

            # Optional per-row sub-label (e.g. club · season at this age),
            # keyed by entity then by the current integer period (year_int).
            # When present it replaces the in-row sparkline for that row.
            sub_labels = render_cfg.get('row_sublabels') or {}
            sub_text = ''
            if sub_labels:
                _entry = sub_labels.get(country) or {}
                sub_text = _entry.get(str(year_int)) or _entry.get(year_int) or ''

            # In-row sparkline: this country's own history up to now, drawn
            # in the bottom band of the name card so it sits under the text.
            # With a sub-label the text stack fills the card, so draw the
            # line faint across the full card height behind the text instead.
            _spark_min_h = 0.012 if _box_mode == 'uniform' else 0.022
            if card_h >= _spark_min_h and frame_idx >= 2:
                hist = country_hist[country][:frame_idx + 1]
                xs_hist = spark_xs_full[:frame_idx + 1]
                if _box_mode == 'uniform':
                    # Uniform cards span the full track: stretch the trend
                    # line edge-to-edge and draw it faint behind the text.
                    xs_hist = np.linspace(name_box_x + 0.010,
                                          name_box_x + name_box_w - 0.010,
                                          len(scores_df))[:frame_idx + 1]
                    spark_bot = card_y + card_h * 0.12
                    spark_top = card_y + card_h * 0.88
                    spark_alpha, spark_lw = 0.30, 2.0
                elif sub_text:
                    spark_bot = card_y + card_h * 0.12
                    spark_top = card_y + card_h * 0.88
                    spark_alpha, spark_lw = 0.28, 2.0
                else:
                    spark_bot = card_y + card_h * 0.08
                    spark_top = card_y + card_h * 0.44
                    spark_alpha, spark_lw = 0.55, 1.4
                ys_hist = spark_bot + hist * (spark_top - spark_bot)
                ax.plot(xs_hist, ys_hist,
                        color=theme.text_primary, linewidth=spark_lw,
                        alpha=spark_alpha * entry_alpha, zorder=2.6,
                        solid_capstyle='round')

            # Cap row fonts so glyphs never overflow very thin cards (only
            # binds when the floor size would poke past the card edges).
            _fs_cap = card_h * FIG_H_PX * 0.55
            rank_fs = min(_lerp(14, 28, s) * row_scale_fs, _fs_cap)
            _disp_rank = slot_of[country] if render_cfg.get('slot_rank_numbers') else int_rank
            ax.text(columns.rank_x, y_center, str(_disp_rank),
                    ha='right', va='center',
                    color=theme.text_primary,
                    fontsize=rank_fs, fontweight=row_weight,
                    alpha=_lerp(0.55, 0.95, alpha_s) * entry_alpha,
                    fontfamily=theme.font_family, zorder=4)

            name_fs = min(_lerp(13, 21, s) * row_scale_fs, _fs_cap)
            label = display_name(country, max_chars=name_max_chars).upper()
            if sub_text:
                # Three-line stack centred on y_center: NAME / CLUB / YEAR.
                # sub_text is "CLUB, YEAR"; split it onto its own two lines.
                club_str, _, year_str = sub_text.partition(', ')
                club_fs = _lerp(12, 17, s) * row_scale_fs
                year_fs = _lerp(11, 15, s) * row_scale_fs
                gap = 6.5  # px between lines
                d_nc = name_fs * 0.5 + gap + club_fs * 0.5   # name→club center gap
                d_cy = club_fs * 0.5 + gap + year_fs * 0.5   # club→year center gap
                total = name_fs * 0.5 + d_nc + d_cy + year_fs * 0.5  # block height px
                name_y = y_center + (total * 0.5 - name_fs * 0.5) / FIG_H_PX
                club_y = name_y - d_nc / FIG_H_PX
                year_y = club_y - d_cy / FIG_H_PX
                ax.text(columns.name_left, name_y, label,
                        ha='left', va='center',
                        color=theme.text_primary,
                        fontsize=name_fs, fontweight=row_weight,
                        alpha=_lerp(0.9, 1.0, alpha_s) * entry_alpha,
                        fontfamily=theme.font_family, zorder=5)
                ax.text(columns.name_left, club_y, club_str,
                        ha='left', va='center',
                        color=theme.text_primary,
                        fontsize=club_fs, fontweight='bold',
                        alpha=_lerp(0.85, 0.98, alpha_s) * entry_alpha,
                        fontfamily=theme.font_family, zorder=5)
                if year_str:
                    ax.text(columns.name_left, year_y, year_str,
                            ha='left', va='center',
                            color=theme.text_secondary,
                            fontsize=year_fs, fontweight='bold',
                            alpha=_lerp(0.8, 0.95, alpha_s) * entry_alpha,
                            fontfamily=theme.font_family, zorder=5)
            else:
                ax.text(columns.name_left, y_center, label,
                        ha='left', va='center',
                        color=theme.text_primary,
                        fontsize=name_fs, fontweight=row_weight,
                        alpha=_lerp(0.9, 1.0, alpha_s) * entry_alpha,
                        fontfamily=theme.font_family, zorder=5)

            # Right-edge badge inside the name card: per-window rate or
            # retirement marker. Skipped when the card is too short to fit
            # comfortably above the sparkline.
            if (rate_df is not None or retirement_frame is not None) and card_h_i >= 0.030:
                is_retired = (retirement_frame is not None
                              and frame_idx >= retirement_frame.get(country, 10**9))
                badge_text = ''
                badge_color = theme.text_secondary
                if is_retired:
                    badge_text = row_retired_label
                elif rate_df is not None:
                    rv = float(rate_df.iloc[frame_idx][country]) if (
                        country in rate_df.columns) else 0.0
                    if row_rate_style in ('percent', 'delta'):
                        mag = int(round(abs(rv))) if np.isfinite(rv) else 0
                        if mag >= 1:
                            unit = '%' if row_rate_style == 'percent' else ''
                            badge_text = f"{'+' if rv > 0 else '-'}{mag}{unit}"
                            badge_color = '#22c55e' if rv > 0 else '#ef4444'
                    elif np.isfinite(rv) and rv > 0.5:
                        badge_text = f"+{int(round(rv))}{row_rate_label}"
                if badge_text:
                    badge_x = columns.name_box_right - 0.012
                    # With a sublabel the name line fills the top of the card;
                    # park the badge bottom-right next to the sublabel instead.
                    badge_y = (y_center - card_h * 0.28 if sub_text
                               else y_center + card_h * 0.28)
                    badge_fs = _lerp(11, 17, s) * row_scale_fs
                    ax.text(badge_x, badge_y, badge_text,
                            ha='right', va='center',
                            color=badge_color,
                            fontsize=badge_fs, fontweight=row_weight,
                            alpha=0.85 * entry_alpha,
                            fontfamily=theme.font_family, zorder=5)

            # Flag
            icon = get_flag(country, year_int)
            flag_h = card_h_i * 0.96
            if icon is not None:
                ih, iw = icon.shape[0], icon.shape[1]
                draw_h = flag_h
                draw_w = draw_h * (iw / ih) * (FIG_H_PX / FIG_W_PX)
            else:
                # No icon: render a virtual zero-width marker so the value
                # text below can still anchor at the value's track position.
                ih = iw = 1
                draw_h = flag_h
                draw_w = 0.0

            # Uniform-card mode pins the icon to the card's right edge (no
            # horizontal motion — a pure ranking table); otherwise the icon
            # rides the track proportionally to its value.
            if _box_mode == 'uniform':
                fx = (columns.track_right + 0.008) - 0.006 - draw_w
            else:
                fx = track_position(
                    eff(value), eff_max,
                    columns.track_left, columns.track_right,
                    draw_w,
                )
            fy = y_center - draw_h / 2

            if icon is not None:
                if flash_alpha > 0:
                    _rounded_rect(
                        ax, fx - 0.01, fy - 0.005,
                        draw_w + 0.02, draw_h + 0.01,
                        radius_px=12, fig_w_px=FIG_W_PX,
                        facecolor=flash_color,
                        alpha=0.35 * flash_alpha * entry_alpha, zorder=4.5,
                    )

                img = icon
                if entry_alpha < 1.0:
                    img = img.copy()
                    img[..., 3] = (img[..., 3] * entry_alpha).astype(np.uint8)
                ax.imshow(img, extent=[fx, fx + draw_w, fy, fy + draw_h],
                          origin='upper', aspect='auto', zorder=5,
                          clip_on=False)

            value_fs = min(_lerp(14, 24, s) * row_scale_fs, _fs_cap)
            _num = format_value(value, value_format).upper()
            if not _num and show_zero_values and np.isfinite(value):
                _num = '0'
            # Only append the unit when there's a number, so a blank value
            # never renders as an orphan " goals". Singularize the unit for
            # exactly 1 ("1 goal", not "1 goals").
            _suffix = value_suffix[:-1] if (_num == '1' and value_suffix.endswith('s')) else value_suffix
            value_str = (_num + (' ' + _suffix if _suffix else '')) if _num else ''
            gap = 0.012
            min_allowed_left = columns.track_left + 0.025

            # Decide the side using the *final* (non-intro-scaled) geometry so the
            # value text doesn't flip sides as the row scales up during intro.
            draw_h_final = (card_h_i / this_intro_scale) * 0.96 if this_intro_scale > 0 else draw_h
            draw_w_final = draw_h_final * (iw / ih) * (FIG_H_PX / FIG_W_PX) if icon is not None else 0.0
            fx_final = track_position(
                eff(value), eff_max,
                columns.track_left, columns.track_right,
                draw_w_final,
            )
            s_final = (card_h_i / this_intro_scale) / max_card_h_render if (
                this_intro_scale > 0 and max_card_h_render > 0) else s
            value_fs_final = _lerp(14, 24, s_final) * row_scale_fs
            approx_text_w_final = len(value_str) * (value_fs_final * 0.68 / FIG_W_PX)
            # Pinned icon leaves the whole card free to its left — the value
            # always fits there, and keeping it left avoids overflowing the
            # card's right edge.
            place_left = (_box_mode == 'uniform') or \
                (fx_final - gap - approx_text_w_final) >= min_allowed_left

            if place_left:
                ax.text(fx - gap, y_center, value_str,
                        ha='right', va='center',
                        color=theme.text_primary,
                        fontsize=value_fs, fontweight=row_weight,
                        alpha=entry_alpha,
                        fontfamily=theme.font_family, zorder=5)
            else:
                ax.text(fx + draw_w + gap, y_center, value_str,
                        ha='left', va='center',
                        color=theme.text_primary,
                        fontsize=value_fs, fontweight=row_weight,
                        alpha=entry_alpha,
                        fontfamily=theme.font_family, zorder=5)

            # Win-streak effects: Doom-fire flames engulfing the row card
            # (streak >= fire_min) or a Mario-star scrolling rainbow with
            # sparkles (streak >= star_min), plus a small icon after the name.
            if _sfx_map:
                _streak = int((_sfx_map.get(country) or {}).get(str(year_int), 0))
                _on_fire = _sfx_fire_min <= _streak < _sfx_star_min
                _is_star = _streak >= _sfx_star_min

                # Fire: per-row simulation buffer persists in `state` so the
                # flames flicker continuously and die out naturally (source
                # row cut) when the streak ends.
                _bufs = state.setdefault('fire_bufs', {})
                if _on_fire and country not in _bufs:
                    _b = np.zeros((68, 440))
                    for _ in range(70):          # pre-warm so flames ignite hot
                        _fire_step(_b, True)
                    _bufs[country] = _b
                if country in _bufs:
                    _b = _bufs[country]
                    _fire_step(_b, _on_fire)
                    if not _on_fire and _b.max() < 8.0:
                        del _bufs[country]
                    else:
                        _pulse = 0.20 + 0.10 * np.sin(state['frame'] * 0.4)
                        _rounded_rect(
                            ax, name_box_x, card_y, name_box_w, card_h,
                            radius_px=theme.row_card_corner_radius_px,
                            fig_w_px=FIG_W_PX, facecolor='#ff6a00',
                            alpha=_pulse * entry_alpha, zorder=2.40,
                        )
                        _fimg = _fire_rgba(_b)
                        # Feather the sides so the flames fade out softly
                        # where they spill past the card edges.
                        _fw_px = _b.shape[1]
                        _wx = np.clip(np.minimum(np.arange(_fw_px),
                                                 np.arange(_fw_px)[::-1])
                                      / (_fw_px * 0.05), 0.0, 1.0)
                        _fimg[..., 3] *= 0.95 * entry_alpha * \
                            (_wx * _wx * (3.0 - 2.0 * _wx))[None, :]
                        # Flames spill past the card: wider than the box and
                        # licking a full card height above its top edge.
                        ax.imshow(_fimg,
                                  extent=[name_box_x - 0.014,
                                          name_box_x + name_box_w + 0.014,
                                          card_y - card_h * 0.10,
                                          card_y + card_h * 2.0],
                                  origin='upper', aspect='auto',
                                  interpolation='bilinear',
                                  zorder=2.42, clip_on=False)

                # Mario star: glassmorphic scrolling rainbow across the card
                # with a soft rainbow aura glowing past the card edges, a
                # travelling shine band and twinkling sparkles. Pops in at
                # full strength, like the power-up itself.
                if _is_star:
                    # Outer aura: bigger, heavily feathered, low alpha.
                    _aimg = _rainbow_rgba(220, state['frame'], h=48, sat=0.75)
                    _aimg[..., 3] = 0.45 * entry_alpha * \
                        _edge_feather(48, 220, fx=0.10, fy=0.35)
                    ax.imshow(_aimg,
                              extent=[name_box_x - 0.020,
                                      name_box_x + name_box_w + 0.020,
                                      card_y - card_h * 0.45,
                                      card_y + card_h * 1.45],
                              origin='upper', aspect='auto',
                              interpolation='bilinear',
                              zorder=2.41, clip_on=False)
                    # Glass card fill: pastel rainbow, softly feathered edges.
                    _rimg = _rainbow_rgba(220, state['frame'])
                    _rimg[..., 3] = 0.62 * entry_alpha * \
                        _edge_feather(32, 220, fx=0.02, fy=0.12)
                    ax.imshow(_rimg,
                              extent=[name_box_x, name_box_x + name_box_w,
                                      card_y, card_y + card_h],
                              origin='upper', aspect='auto',
                              interpolation='bilinear',
                              zorder=2.42, clip_on=False)
                    _seed = sum(map(ord, country)) * 7919
                    _rng = np.random.default_rng(_seed)
                    _n_sp = 7
                    _u = _rng.uniform(0.04, 0.96, _n_sp)
                    _v = _rng.uniform(0.15, 0.85, _n_sp)
                    _ph = _rng.uniform(0, 2 * np.pi, _n_sp)
                    _tw = np.clip(np.sin(state['frame'] * 0.35 + _ph), 0.0, 1.0)
                    _cols = np.ones((_n_sp, 4))
                    _cols[:, 3] = _tw * entry_alpha
                    ax.scatter(name_box_x + _u * name_box_w,
                               card_y + _v * card_h,
                               marker='*', s=90 + 160 * _tw, c=_cols,
                               edgecolors='none', zorder=2.48)
                # Streak count label right after the name ("4X WIN STREAK").
                if (_on_fire or _is_star) and card_h >= 0.014:
                    # Orbitron is wide: ~1.05× fontsize px per char.
                    _sx = columns.name_left + \
                        len(label) * (name_fs * 1.05 / FIG_W_PX) + 0.034
                    _stxt = f"{_streak}X STREAK!"
                    # Video-game combo counter: white core over a colored +
                    # black layered outline, with an overshoot "pop" (2× →
                    # 1×) every time the streak count ticks up.
                    _pops = state.setdefault('streak_pop', {})
                    if (_pops.get(country) or (None,))[0] != _streak:
                        _pops[country] = (_streak, state['frame'])
                    _dt = state['frame'] - _pops[country][1]
                    _k = 1.0 - min(1.0, _dt / 9.0)
                    _pop = 1.0 + 0.45 * _k * _k
                    _sfs = name_fs * 0.80 * _pop
                    _accent = '#e11d8f' if _is_star else '#ff7300'
                    ax.text(_sx, y_center, _stxt,
                            ha='left', va='center', color='#ffffff',
                            fontsize=_sfs, fontweight='bold',
                            alpha=entry_alpha,
                            fontfamily=theme.font_family, zorder=5,
                            path_effects=[
                                pe.Stroke(linewidth=5.5, foreground='#000000'),
                                pe.Stroke(linewidth=2.2, foreground=_accent),
                                pe.Normal()])
                elif _sfx_map and country in state.get('streak_pop', {}):
                    del state['streak_pop'][country]

        # ── Spotlight: curated-mode OR auto-select non-top-N mover ──────
        if spotlight_enabled:
            cur = state['spotlight_target']
            active_label = spotlight_label_text

            def _switch(new_target, *, label=None, subtext=''):
                if cur is not None:
                    state['spotlight_prev'] = cur
                    state['spotlight_prev_start'] = state['frame']
                    state['spotlight_prev_label'] = state.get('spotlight_active_label',
                                                              spotlight_label_text)
                    state['spotlight_prev_subtext'] = state.get('spotlight_active_subtext', '')
                state['spotlight_target'] = new_target
                state['spotlight_adopted_frame'] = state['frame']
                state['spotlight_active_label'] = label or spotlight_label_text
                state['spotlight_active_subtext'] = subtext or ''

            if spotlight_curated:
                # Curated mode: the active event is determined purely by the
                # current year. Whichever kept event covers `year_float` wins;
                # earliest start_year breaks ties.
                year_float = float(scores_df.index[frame_idx])
                top_n_set = set(true_top_n)
                active = None
                for ev in spotlight_curated:
                    if ev.start_year <= year_float <= ev.end_year:
                        # Don't show a curated event while its subject is on-screen.
                        if ev.country in top_n_set:
                            continue
                        active = ev
                        break
                active_country = active.country if active else None
                active_label = (active.label_override if active and active.label_override
                                else spotlight_label_text)
                active_subtext = active.subtext if active else ''
                if active_country != cur:
                    _switch(active_country, label=active_label, subtext=active_subtext)
            elif spotlight_deltas is not None:
                # Auto-select mode: same logic as before — biggest qualifying
                # |Δ| per frame, sticky via screen-hold and switch-ratio.
                top_n_set = set(true_top_n)
                row = spotlight_deltas.iloc[frame_idx]
                best_c, best_delta = None, 0.0
                for c in row.index:
                    if c in top_n_set:
                        continue
                    d = float(row[c]) if np.isfinite(row[c]) else 0.0
                    if d <= 0:
                        continue
                    if d > best_delta:
                        best_c, best_delta = c, d
                qualifies = best_c is not None and best_delta >= spotlight_threshold

                cur_delta = 0.0
                if cur is not None and cur in row.index:
                    cv = float(row[cur]) if np.isfinite(row[cur]) else 0.0
                    cur_delta = cv if cv > 0 else 0.0
                held = (state['frame'] - state['spotlight_adopted_frame']) < spotlight_min_screen_frames

                def _auto_subtext(country):
                    if country is None or spotlight_signed_deltas is None:
                        return ''
                    try:
                        signed = float(spotlight_signed_deltas.iloc[frame_idx][country])
                        v_now = float(scores_df.iloc[frame_idx][country])
                    except (KeyError, IndexError, ValueError):
                        return ''
                    if not np.isfinite(signed) or not np.isfinite(v_now):
                        return ''
                    v_before = v_now - signed
                    if v_before <= 0:
                        return ''
                    pct = abs(signed) / v_before * 100.0
                    direction = 'UP' if signed > 0 else 'DOWN'
                    yrs = int(round(rate_window_years))
                    return f"{direction} {pct:.0f}% IN {yrs}Y"

                if cur is None:
                    if qualifies:
                        _switch(best_c, subtext=_auto_subtext(best_c))
                elif not held:
                    if cur_delta < spotlight_threshold and qualifies:
                        _switch(best_c, subtext=_auto_subtext(best_c))
                    elif cur_delta < spotlight_threshold:
                        _switch(None)
                    elif best_c != cur and qualifies and best_delta > cur_delta * spotlight_switch_ratio:
                        _switch(best_c, subtext=_auto_subtext(best_c))

            # ── Draw current + previous (shared across both modes) ──────
            cur = state['spotlight_target']
            if cur is not None:
                since = state['frame'] - state['spotlight_adopted_frame']
                alpha_in = min(1.0, max(0.0, since / max(1, spotlight_fade_frames)))
                v = float(scores[cur]) if np.isfinite(scores[cur]) else 0.0
                dr_cur = display_ranks_all.get(cur)
                rk = int(round(dr_cur)) if dr_cur is not None else 0
                _draw_spotlight(ax, theme, country=cur,
                                display_name_str=display_name(cur),
                                rank_int=rk, value=v, icon=get_flag(cur),
                                alpha=alpha_in,
                                label_text=state.get('spotlight_active_label',
                                                     spotlight_label_text),
                                subtext=state.get('spotlight_active_subtext', ''),
                                value_format=value_format,
                                spot_scale_fs=spot_scale_fs,
                                spot_weight=spot_weight)

            prev = state['spotlight_prev']
            if prev is not None:
                since_out = state['frame'] - state['spotlight_prev_start']
                alpha_out = 1.0 - min(1.0, max(0.0, since_out / max(1, spotlight_fade_frames)))
                if alpha_out > 0.0 and prev != state['spotlight_target']:
                    v = float(scores[prev]) if prev in scores.index and np.isfinite(scores[prev]) else 0.0
                    dr_prev = display_ranks_all.get(prev)
                    rk = int(round(dr_prev)) if dr_prev is not None else 0
                    _draw_spotlight(ax, theme, country=prev,
                                    display_name_str=display_name(prev),
                                    rank_int=rk, value=v, icon=get_flag(prev),
                                    alpha=alpha_out,
                                    label_text=state.get('spotlight_prev_label',
                                                         spotlight_label_text),
                                    subtext=state.get('spotlight_prev_subtext', ''),
                                    value_format=value_format,
                                    spot_scale_fs=spot_scale_fs,
                                    spot_weight=spot_weight)
                else:
                    state['spotlight_prev'] = None

    if single_frame_year is not None or single_frame_years:
        idx = scores_df.index.to_numpy()
        # Skip past the intro: intros key off state['frame'] (t_ease/50, t_title/18,
        # t_draw/55). update() increments first, so set high enough that all
        # easings clamp to 1.0 on every call.
        if single_frame_years:
            out_dir = single_frames_dir or (output_path.parent / 'preview_frames')
            out_dir.mkdir(parents=True, exist_ok=True)
            for year in single_frame_years:
                target = float(year)
                if period_years is not None:
                    target = float(np.argmin(np.abs(
                        np.asarray(period_years, dtype=float) - target)))
                frame_idx = int(np.argmin(np.abs(idx - target)))
                state['frame'] = 200
                update(frame_idx)
                if period_years is not None:
                    year_label = str(period_years[int(round(idx[frame_idx]))])
                else:
                    year_label = f"{idx[frame_idx]:.0f}"
                png = out_dir / f"{year_label}.png"
                fig.savefig(str(png), dpi=DPI, facecolor='#000000')
                print(f"Preview frame saved → {png} (year≈{idx[frame_idx]:.2f})")
        else:
            target = float(single_frame_year)
            if period_years is not None:
                target = float(np.argmin(np.abs(
                    np.asarray(period_years, dtype=float) - target)))
            frame_idx = int(np.argmin(np.abs(idx - target)))
            png = single_frame_png_path or (output_path.parent / 'preview_frame.png')
            png.parent.mkdir(parents=True, exist_ok=True)
            state['frame'] = 200
            update(frame_idx)
            fig.savefig(str(png), dpi=DPI, facecolor='#000000')
            print(f"Preview frame saved → {png} (year≈{idx[frame_idx]:.2f})")
        plt.close(fig)
        return

    if preview_timeframe:
        y0, y1 = preview_timeframe
        idx = scores_df.index
        frames = [i for i, y in enumerate(idx) if y0 <= y <= y1]
        print(f"Preview mode: {len(frames)} frames ({y0}-{y1}) → {output_path}")
    else:
        frames = list(range(len(scores_df)))
        print(f"Rendering {len(frames)} frames → {output_path}")

    end_hold_seconds = float(render_cfg.get('end_hold_seconds', 0.0))
    if end_hold_seconds > 0 and frames:
        hold_frames = int(round(end_hold_seconds * fps))
        frames = frames + [frames[-1]] * hold_frames
        print(f"Holding last frame for {end_hold_seconds}s ({hold_frames} frames)")

    ani = animation.FuncAnimation(fig, update, frames=frames, interval=1000 / fps)
    writer = animation.FFMpegWriter(fps=fps, bitrate=bitrate)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ani.save(str(output_path), writer=writer)
    plt.close(fig)
    print(f"Done → {output_path}")


def validate_layout(columns: Columns = DEFAULT_COLUMNS) -> dict:
    assert columns.name_box_left < columns.name_box_right, "name box has non-positive width"
    assert columns.name_box_right < columns.track_left, (
        f"name_box_right {columns.name_box_right} overlaps track_left {columns.track_left}"
    )
    assert columns.track_right <= SAFE_RIGHT + 1e-9, (
        f"track_right {columns.track_right} exceeds Shorts safe zone {SAFE_RIGHT}"
    )
    bounds = {
        'name_box': (columns.name_box_left, columns.name_box_right),
        'gutter':   (columns.name_box_right, columns.track_left),
        'track':    (columns.track_left, columns.track_right),
    }
    return {k: (round(l * FIG_W_PX, 1), round(r * FIG_W_PX, 1))
            for k, (l, r) in bounds.items()}
