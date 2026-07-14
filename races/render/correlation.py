"""Prototype renderer for the *correlation* video style — two animated line
charts on a shared time axis, revealing a (spurious) correlation.

Standalone on purpose: it reuses the shared theme, font loader and background
for a consistent aesthetic, but does NOT touch the bar-race render loop, so the
world/sports pipelines are unaffected. Run directly:

    python -m races.render.correlation
"""

import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.patches import Ellipse
import imageio.plugins.ffmpeg as _ffmpeg_plugin
import imageio.v2 as iio

from ..assets.fonts import ensure_orbitron
from .theme import get_theme
from .renderer import _draw_background

plt.rcParams['animation.ffmpeg_path'] = _ffmpeg_plugin.get_exe()
sys.stdout.reconfigure(encoding='utf-8')

FIG_W_IN, FIG_H_IN, DPI = 10.8, 19.2, 100
FPS = 30

# Endpoint avatar radius. y is scaled by the frame aspect so it reads round
# (axes are 0..1 over a 1080×1920 canvas, so equal data-radius would ellipse).
AVATAR_RX = 0.058
AVATAR_RY = AVATAR_RX * (FIG_W_IN / FIG_H_IN)
# Drop real photos here as <photo>.jpg/png; missing → monogram placeholder.
PHOTO_DIR = Path(__file__).resolve().parents[1] / 'assets' / 'photos'

# Chart region in axes (0..1) coords.
CHART_L, CHART_R = 0.14, 0.86
CHART_B, CHART_T = 0.34, 0.70
CHART_W = CHART_R - CHART_L
CHART_H = CHART_T - CHART_B

# ── Tyler Vigen's canonical spurious correlation (1999–2009, r ≈ 0.67) ──────
YEARS = list(range(1999, 2010))
SERIES_A = {           # the "victim" line
    'label': 'US POOL DROWNINGS',
    'short': 'POOL\nDROWNINGS',               # short caption at the line tip
    'mono': 'POOL',                           # placeholder text if no photo
    'photo': 'pool',                          # PHOTO_DIR/pool.jpg|png (optional)
    'unit': 'deaths / yr',
    'color': '#22d3ee',                       # neon cyan
    'values': [109, 102, 102, 98, 85, 95, 96, 98, 123, 94, 102],
}
SERIES_B = {           # the "culprit" line
    'label': 'NICOLAS CAGE FILMS',
    'short': 'NIC CAGE\nFILMS',
    'mono': 'NC',
    'photo': 'cage',                          # PHOTO_DIR/cage.jpg|png (optional)
    'unit': 'films / yr',
    'color': '#f472b6',                       # neon pink
    'values': [2, 2, 2, 3, 1, 1, 2, 3, 4, 1, 4],
}

TITLE = 'IS NICOLAS CAGE\nDROWNING AMERICANS?'
SOURCE_CREDIT = 'Source: CDC / Wikipedia (via Tyler Vigen)'

# Fake-serious storyboard captions: (start_s, end_s, text). Placeholder copy —
# the real narration/on-screen text comes from the LLM script later.
CAPTIONS = [
    (1.0,  7.5,  'Two numbers. The same ten years.\nWatch them move.'),
    (8.0,  13.5, 'US pool drownings...\nand Nicolas Cage films per year.'),
    (14.0, 18.5, 'They rise and fall together...\nalmost perfectly.'),
    (19.0, 25.5, 'So does Nic Cage cause\npeople to drown?'),
    (26.0, 33.0, "Of course not.\nCorrelation isn't causation."),
]

# Animation timeline (seconds). Both lines now draw together.
T_A_START, T_A_END = 1.5, 8.0     # draw series A
T_B_START, T_B_END = 1.5, 8.0     # draw series B (same window as A)
T_CORR = 19.0                     # correlation badge fades in
TOTAL_S = 33.0


def _draw_question_marks(ax, theme, *, frame_idx, fps, n=44):
    """General, low-key backdrop for correlation videos: faint '?' glyphs
    drifting slowly upward. Reusable for any 'mystery' framing — not tied to
    music like the bar-race equalizer."""
    rng = np.random.default_rng(7)                 # fixed seed → stable layout
    xs = rng.uniform(0.02, 0.98, n)
    ys0 = rng.uniform(0.0, 1.0, n)
    sizes = rng.uniform(20, 70, n)
    phases = rng.uniform(0, 2 * np.pi, n)
    speeds = rng.uniform(0.006, 0.02, n)
    tints = rng.integers(0, 3, n)
    colors = ['#475569', '#334155', SERIES_B['color']]  # mostly slate, a few pink
    t = frame_idx / fps
    for i in range(n):
        y = (ys0[i] + speeds[i] * t) % 1.0         # drift up, wrap around
        x = xs[i] + 0.012 * np.sin(phases[i] + t * 0.5)
        alpha = 0.05 + 0.045 * (0.5 + 0.5 * np.sin(phases[i] + t * 0.9))
        if tints[i] == 2:
            alpha *= 0.6                            # keep the pink ones subtle
        ax.text(x, y, '?', ha='center', va='center', fontsize=sizes[i],
                color=colors[tints[i]], alpha=alpha, fontfamily=theme.font_family,
                zorder=-6)


def _lerp(a, b, t):
    return a + (b - a) * t


def _smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _norm_series(values):
    """Normalize a series to [0.08, 0.92] within the chart band so both lines
    fill the vertical space and their *shape* (not scale) is comparable."""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    return [0.08 + 0.84 * (v - lo) / span for v in values]


def _chart_x(i):
    return CHART_L + CHART_W * (i / (len(YEARS) - 1))


def _chart_y(vn):
    return CHART_B + CHART_H * vn


def _draw_polyline(ax, series, reveal, *, zorder=3):
    """Draw the line up to fractional index `reveal` (0..N-1), with a neon
    glow and a bright head dot."""
    n = len(YEARS)
    yn = _norm_series(series['values'])
    xs = [_chart_x(i) for i in range(n)]
    ys = [_chart_y(v) for v in yn]

    if reveal <= 0:
        return
    full = int(np.floor(reveal))
    frac = reveal - full
    px = xs[:full + 1]
    py = ys[:full + 1]
    if full < n - 1 and frac > 0:
        px = px + [_lerp(xs[full], xs[full + 1], frac)]
        py = py + [_lerp(ys[full], ys[full + 1], frac)]
    if len(px) < 2:
        px = px * 2
        py = py * 2

    color = series['color']
    # Glow: stacked translucent strokes.
    for lw, a in ((14, 0.06), (9, 0.10), (5, 0.16)):
        ax.plot(px, py, color=color, linewidth=lw, alpha=a,
                solid_capstyle='round', zorder=zorder)
    ax.plot(px, py, color=color, linewidth=2.6, alpha=0.95,
            solid_capstyle='round', zorder=zorder + 0.1)
    # Revealed data points.
    ax.scatter(px[:full + 1] if frac == 0 else px[:-1], py[:full + 1] if frac == 0 else py[:-1],
               s=42, color=color, edgecolors='white', linewidths=0.8,
               zorder=zorder + 0.2)
    # Head dot.
    ax.scatter([px[-1]], [py[-1]], s=120, color='white',
               edgecolors=color, linewidths=2.5, zorder=zorder + 0.3)


def _preload_photos():
    """Load each series' optional endpoint photo into '_photo_arr' (or None).
    Called once before rendering so we don't hit disk every frame."""
    for series in (SERIES_A, SERIES_B):
        series['_photo_arr'] = None
        for ext in ('.jpg', '.jpeg', '.png', '.webp'):
            p = PHOTO_DIR / (series['photo'] + ext)
            if p.exists():
                try:
                    series['_photo_arr'] = iio.imread(p)
                    break
                except Exception as e:
                    print(f"  [photo] failed to load {p}: {e}")


def _head_pos(series, reveal):
    """(x, y) of the leading tip of a line revealed to fractional index."""
    n = len(YEARS)
    yn = _norm_series(series['values'])
    xs = [_chart_x(i) for i in range(n)]
    ys = [_chart_y(v) for v in yn]
    full = int(np.floor(reveal))
    frac = reveal - full
    if full >= n - 1:
        return xs[-1], ys[-1]
    if frac <= 0:
        return xs[full], ys[full]
    return _lerp(xs[full], xs[full + 1], frac), _lerp(ys[full], ys[full + 1], frac)


MIN_BADGE_GAP = 0.16   # min vertical spacing so avatar+caption never overlap


def _badge_anchor(hx, hy):
    """Where a badge sits relative to a line tip: beside it, flipping left near
    the right edge, clamped inside the chart band."""
    side = -1 if hx > 0.66 else 1
    bx = hx + side * (AVATAR_RX + 0.02)
    by = min(max(hy, CHART_B + AVATAR_RY), CHART_T + 0.02)
    return bx, by


def _draw_endpoint_badge(ax, theme, series, bx, by, alpha):
    """A small round photo (or monogram placeholder) + short caption pinned
    near the tip of a line, so the viewer sees what the line represents."""
    if alpha <= 0:
        return
    fam = theme.font_family
    color = series['color']

    arr = series.get('_photo_arr')
    if arr is not None:
        im = ax.imshow(arr, extent=[bx - AVATAR_RX, bx + AVATAR_RX,
                                    by - AVATAR_RY, by + AVATAR_RY],
                       aspect='auto', interpolation='bilinear', alpha=alpha,
                       zorder=7, origin='upper')
        clip = Ellipse((bx, by), 2 * AVATAR_RX, 2 * AVATAR_RY,
                       transform=ax.transData)
        im.set_clip_path(clip)
    else:
        ax.add_patch(Ellipse((bx, by), 2 * AVATAR_RX, 2 * AVATAR_RY,
                             facecolor='#0f172a', edgecolor='none',
                             alpha=alpha, zorder=7))
        ax.text(bx, by, series['mono'], ha='center', va='center',
                fontsize=17, color=color, alpha=alpha, fontfamily=fam,
                fontweight='bold', zorder=7.2)
    # Neon ring.
    ax.add_patch(Ellipse((bx, by), 2 * AVATAR_RX, 2 * AVATAR_RY, fill=False,
                         edgecolor=color, linewidth=2.5, alpha=alpha, zorder=7.3))
    # Short caption under the avatar.
    ax.text(bx, by - AVATAR_RY - 0.012, series['short'], ha='center', va='top',
            fontsize=15, color=theme.text_primary, alpha=alpha, fontfamily=fam,
            fontweight='bold', linespacing=1.15, zorder=7.3)


def _draw_frame(fig, ax, theme, frame_idx, n_frames):
    ax.clear()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    _draw_background(ax, theme, frame_idx=frame_idx, fps=FPS,
                     n_frames_total=n_frames)
    _draw_question_marks(ax, theme, frame_idx=frame_idx, fps=FPS)

    t = frame_idx / FPS
    fam = theme.font_family

    # ── Title ──────────────────────────────────────────────────────────
    ax.text(0.5, 0.90, TITLE, ha='center', va='center',
            fontsize=40, color=theme.text_primary, fontfamily=fam,
            fontweight='bold', linespacing=1.15, zorder=5)

    # ── Chart frame: baseline + year ticks ─────────────────────────────
    ax.plot([CHART_L, CHART_R], [CHART_B - 0.015, CHART_B - 0.015],
            color='#334155', linewidth=1.2, zorder=2)
    for i, yr in enumerate(YEARS):
        if yr % 2 == 1:  # label odd years to avoid crowding
            ax.text(_chart_x(i), CHART_B - 0.045, f"'{str(yr)[2:]}",
                    ha='center', va='top', fontsize=15, color=theme.text_secondary,
                    fontfamily=fam, zorder=2)

    # ── Line reveals ───────────────────────────────────────────────────
    n = len(YEARS)
    ra = _smoothstep((t - T_A_START) / (T_A_END - T_A_START)) * (n - 1)
    rb = _smoothstep((t - T_B_START) / (T_B_END - T_B_START)) * (n - 1)
    _draw_polyline(ax, SERIES_A, ra, zorder=3)
    _draw_polyline(ax, SERIES_B, rb, zorder=4)

    # ── Endpoint badges: photo/monogram + short caption at each line tip ─
    badge_a = _smoothstep((t - T_A_START) / 0.8)
    badge_b = _smoothstep((t - T_B_START) / 0.8)
    ax_, ay = _badge_anchor(*_head_pos(SERIES_A, ra))
    bx_, by = _badge_anchor(*_head_pos(SERIES_B, rb))
    # Both tips can run close together mid-draw — push the badges apart so the
    # avatars/captions never overlap, keeping their relative order.
    if abs(ay - by) < MIN_BADGE_GAP:
        mid = (ay + by) / 2
        if ay >= by:
            ay, by = mid + MIN_BADGE_GAP / 2, mid - MIN_BADGE_GAP / 2
        else:
            ay, by = mid - MIN_BADGE_GAP / 2, mid + MIN_BADGE_GAP / 2
    if badge_a > 0:
        _draw_endpoint_badge(ax, theme, SERIES_A, ax_, ay, badge_a)
    if badge_b > 0:
        _draw_endpoint_badge(ax, theme, SERIES_B, bx_, by, badge_b)

    # ── Correlation badge ──────────────────────────────────────────────
    ca = _smoothstep((t - T_CORR) / 1.0)
    if ca > 0:
        ax.text(0.5, 0.255, 'CORRELATION', ha='center', va='center',
                fontsize=16, color=theme.text_secondary, alpha=ca,
                fontfamily=fam, zorder=5)
        ax.text(0.5, 0.215, 'r = 0.67', ha='center', va='center',
                fontsize=34, color='#fbbf24', alpha=ca, fontfamily=fam,
                fontweight='bold', zorder=5)

    # ── Storyboard caption ─────────────────────────────────────────────
    for start, end, text in CAPTIONS:
        if start <= t <= end:
            fade = min(_smoothstep((t - start) / 0.5),
                       _smoothstep((end - t) / 0.5))
            ax.text(0.5, 0.135, text, ha='center', va='center',
                    fontsize=23, color=theme.text_primary, alpha=fade,
                    fontfamily=fam, linespacing=1.3, zorder=6)
            break

    # ── Source credit ──────────────────────────────────────────────────
    ax.text(0.5, 0.035, SOURCE_CREDIT, ha='center', va='center',
            fontsize=13, color=theme.text_secondary, alpha=0.7,
            fontfamily=fam, zorder=5)


def render(out_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    ensure_orbitron(repo_root / 'cache')
    _preload_photos()
    theme = get_theme('glass_dark_black')

    n_frames = int(TOTAL_S * FPS)
    fig = plt.figure(figsize=(FIG_W_IN, FIG_H_IN), dpi=DPI)
    fig.patch.set_facecolor('#000000')
    ax = fig.add_axes([0, 0, 1, 1])

    writer = animation.FFMpegWriter(fps=FPS, bitrate=8000)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Rendering {n_frames} frames → {out_path}")
    with writer.saving(fig, str(out_path), DPI):
        for f in range(n_frames):
            _draw_frame(fig, ax, theme, f, n_frames)
            writer.grab_frame()
            if f % 60 == 0:
                print(f"  frame {f}/{n_frames}")
    plt.close(fig)
    print(f"Done → {out_path}  ({TOTAL_S:.1f}s)")


if __name__ == '__main__':
    out = Path(__file__).resolve().parents[2] / 'output' / 'correlation_prototype.mp4'
    render(out)
