import sys
sys.stdout.reconfigure(encoding='utf-8')

"""
s4_bar_chart_generator.py  (redesigned)
Clean, modern bar chart race renderer for the World Bank pipeline.
"""

import json
import os
import re
import hashlib

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from PIL import Image, ImageDraw
import imageio.plugins.ffmpeg as _ffmpeg_plugin

# ── Config ────────────────────────────────────────────────────────────────────
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

BG_COLOR     = config['background_color']
VIDEO_TITLE  = config['video_title']
VALUE_FORMAT = config['value_format']
N_ON_SCREEN  = config['top_n_on_screen']
OUTPUT_FILE  = config.get('output_filename', 'world_bank_race.mp4')

plt.rcParams['animation.ffmpeg_path'] = _ffmpeg_plugin.get_exe()

# ── Color palette (Tailwind 400-series — vivid on dark backgrounds) ───────────
PALETTE = [
    '#f87171',  # red
    '#60a5fa',  # blue
    '#4ade80',  # green
    '#fbbf24',  # amber
    '#a78bfa',  # violet
    '#34d399',  # emerald
    '#fb923c',  # orange
    '#f472b6',  # pink
    '#38bdf8',  # sky
    '#a3e635',  # lime
    '#818cf8',  # indigo
    '#e879f9',  # fuchsia
    '#2dd4bf',  # teal
    '#facc15',  # yellow
    '#c084fc',  # purple
    '#22d3ee',  # cyan
    '#86efac',  # light green
    '#fca5a5',  # light red
    '#93c5fd',  # light blue
    '#fde68a',  # light amber
]

# ── Value formatter ───────────────────────────────────────────────────────────
def format_value(v: float, fmt: str) -> str:
    if pd.isna(v) or v == 0:
        return ''
    prefix = '$' if fmt == 'currency' else ''
    if v >= 1e12:
        return f'{prefix}{v / 1e12:.2f} T'
    elif v >= 1e9:
        return f'{prefix}{v / 1e9:.2f} B'
    elif v >= 1e6:
        return f'{prefix}{v / 1e6:.2f} M'
    elif v >= 1e3:
        return f'{prefix}{v / 1e3:.1f} K'
    return f'{prefix}{v:,.0f}'

# ── Safe filename helper (must match s2_get_flags.py) ────────────────────────
def safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name)

# ── Short display names (World Bank full name → label shown on screen) ────────
# Add any overrides here; everything else falls back to the raw name (truncated
# at 22 chars if still too long).
DISPLAY_NAMES = {
    'United States':                      'USA',
    'United Kingdom':                     'UK',
    'Russian Federation':                 'Russia',
    'Korea, Rep.':                        'South Korea',
    'Korea, Dem. People\'s Rep.':         'North Korea',
    'Iran, Islamic Rep.':                 'Iran',
    'Egypt, Arab Rep.':                   'Egypt',
    'Syrian Arab Republic':               'Syria',
    'Venezuela, RB':                      'Venezuela',
    'Yemen, Rep.':                        'Yemen',
    'Kyrgyz Republic':                    'Kyrgyzstan',
    'Lao PDR':                            'Laos',
    'Micronesia, Fed. Sts.':              'Micronesia',
    'Congo, Dem. Rep.':                   'DR Congo',
    'Congo, Rep.':                        'Congo',
    'Central African Republic':           'C.A.R.',
    'Trinidad and Tobago':                'Trinidad & Tobago',
    'Bosnia and Herzegovina':             'Bosnia & Herz.',
    'North Macedonia':                    'N. Macedonia',
    'United Arab Emirates':               'UAE',
    'Papua New Guinea':                   'Papua N.G.',
    'Equatorial Guinea':                  'Eq. Guinea',
    'São Tomé and Príncipe':              'São Tomé',
    'Antigua and Barbuda':                'Antigua & Barbuda',
    'Saint Kitts and Nevis':              'St. Kitts & Nevis',
    'Saint Vincent and the Grenadines':   'St. Vincent',
    'Saint Lucia':                        'St. Lucia',
    'Turks and Caicos Islands':           'Turks & Caicos',
    'Virgin Islands (U.S.)':              'US Virgin Islands',
    'Brunei Darussalam':                  'Brunei',
    'Turkiye':                            'Türkiye',
    'Viet Nam':                           'Vietnam',
    'Slovak Republic':                    'Slovakia',
    'Czech Republic':                     'Czechia',
}

def display_name(country: str) -> str:
    """Return the short display label for a country."""
    name = DISPLAY_NAMES.get(country, country)
    return name if len(name) <= 22 else name[:20] + '..'

# ── Load data ─────────────────────────────────────────────────────────────────
print('Loading data...')
df = pd.read_csv('FINAL_BAR_CHART_RACE.csv', index_col='Year')

# ── Assign a unique, stable color to each country ────────────────────────────
country_colors = {}
for country in df.columns:
    idx = int(hashlib.md5(country.encode()).hexdigest(), 16) % len(PALETTE)
    country_colors[country] = PALETTE[idx]

# ── Smooth the data ───────────────────────────────────────────────────────────
STEPS_PER_YEAR = 60  # 60 sub-frames/year @ 30 fps = 2 s per year (was 1 s)
new_index  = np.linspace(df.index.min(), df.index.max(),
                         (len(df) - 1) * STEPS_PER_YEAR + 1)
df_scores  = df.reindex(new_index).interpolate(method='linear')

# Rank on smoothed values so that unique ranks are always guaranteed.
# Larger windows (relative to STEPS_PER_YEAR) give softer rank-swap motion.
_val_smooth  = df_scores.rolling(window=11, center=True, min_periods=1).mean()
smooth_ranks = _val_smooth.rank(axis=1, method='first', ascending=True).astype(float)
# Second pass — wider window (15) so close-value rank swaps stay separated
smooth_ranks = smooth_ranks.rolling(window=15, center=True, min_periods=1).mean()

TOTAL  = len(df.columns)
BAR_H  = 0.80   # bar height in rank units — taller bars = bigger content

# ── Rank-based size scaling ────────────────────────────────────────────────────
# scale(rank #1) = 1.0, scale(rank #N) = 1 - SCALE_DROP
# SCALE_EXP < 1 → concave curve: steep drop for top-3, flattens for lower ranks
SCALE_DROP  = 0.45
SCALE_EXP   = 0.28
ROW_COMPACT = 0.52   # fraction of full span; < 1 packs rows tighter
_ROW_SPAN   = (N_ON_SCREEN - 1) * ROW_COMPACT  # actual data-unit span of all rows

def rank_scale(display_rank: float) -> float:
    """Size multiplier for a given display rank (1 = largest)."""
    t = (display_rank - 1) / max(N_ON_SCREEN - 1, 1)
    t = float(np.clip(t, 0.0, 1.0))
    return 1.0 - SCALE_DROP * (t ** SCALE_EXP)

def rank_to_y(rank_val: float) -> float:
    """Map a smooth rank value to a proportionally-spaced draw-y position.

    Rows for high-ranked countries (large flags) own more vertical space;
    rows for low-ranked countries (small flags) are packed tighter.

    scale(u) = 1 - SCALE_DROP*(1-u)^SCALE_EXP
      u=0 → bottom (display rank N, smallest)  scale ≈ 1 - SCALE_DROP
      u=1 → top    (display rank 1, largest)   scale = 1.0
    ∫₀ᵘ scale(s) ds = u - SCALE_DROP/(EXP+1) * [1 - (1-u)^(EXP+1)]

    For u < 0 (country sliding in from below the visible window) we linearly
    extrapolate using the slope at u=0.  scale(0) = 1.0 (since 0^SCALE_EXP=0),
    so the normalised slope is 1/integral_1.
    """
    u   = (rank_val - (TOTAL - N_ON_SCREEN + 1)) / max(N_ON_SCREEN - 1, 1)
    ep1 = SCALE_EXP + 1.0
    integral_1 = 1.0 - SCALE_DROP / ep1   # = ∫₀¹ scale(s) ds
    if u < 0:
        # Linear extrapolation — country is below the visible window
        v = u / integral_1
    else:
        u          = float(np.clip(u, 0.0, 1.0))
        integral_u = u - SCALE_DROP / ep1 * (1.0 - (1.0 - u) ** ep1)
        v          = integral_u / integral_1   # normalised cumulative position [0, 1]
    # Map into the compacted span: u=0 → TOTAL-_ROW_SPAN, u=1 → TOTAL
    return (TOTAL - _ROW_SPAN) + v * _ROW_SPAN

# ── Flag image effects: rounded corners only ─────────────────────────────────
# Shadow was removed: it expanded the canvas asymmetrically (right/bottom only),
# making it impossible to reliably compute flag edges for text placement.
# Flags are rendered via ax.imshow with explicit data-coordinate extents instead
# of OffsetImage, so size is derived geometrically — no zoom/DPI ambiguity.
def apply_rounded_corners(img_array: np.ndarray, radius: int = 18) -> np.ndarray:
    """Return flag with rounded corners (no shadow, no canvas expansion)."""
    img = Image.fromarray(img_array).convert('RGBA')
    w, h = img.size
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1],
                                           radius=radius, fill=255)
    r, g, b, a = img.split()
    a = Image.fromarray(np.minimum(np.array(a), np.array(mask)))
    img = Image.merge('RGBA', (r, g, b, a))
    return np.array(img)

# ── Flag aspect-ratio normalisation ──────────────────────────────────────────
# Country flags have wildly different official proportions (Switzerland 1:1,
# Qatar 2.54:1, most others 3:2 or 2:1).  Since rendered width is derived from
# orig_w/orig_h, this would make Qatar flags ~70% wider than French ones at the
# same height.  We pad every flag to a standard canvas with transparent pixels
# so all flags occupy the same bounding box ratio.  The true design is never
# cropped or stretched.  Adjust FLAG_ASPECT if a different ratio is preferred.
FLAG_ASPECT = 5 / 3   # target width:height ratio (5:3 ≈ 1.667, midpoint between 3:2 and 2:1)

def normalize_flag_aspect(img_array: np.ndarray, target_ratio: float = FLAG_ASPECT) -> np.ndarray:
    """Pad flag to a standard aspect ratio with transparent pixels."""
    img = Image.fromarray(img_array).convert('RGBA')
    w, h = img.size
    current_ratio = w / h

    if abs(current_ratio - target_ratio) < 0.01:
        return img_array  # already close enough, skip

    if current_ratio < target_ratio:
        # Flag is too tall (e.g. Switzerland 1:1) → pad left and right
        new_w = round(h * target_ratio)
        new_img = Image.new('RGBA', (new_w, h), (0, 0, 0, 0))
        new_img.paste(img, ((new_w - w) // 2, 0))
    else:
        # Flag is too wide (e.g. Qatar 2.54:1) → pad top and bottom
        new_h = round(w / target_ratio)
        new_img = Image.new('RGBA', (w, new_h), (0, 0, 0, 0))
        new_img.paste(img, (0, (new_h - h) // 2))

    return np.array(new_img)

# ── Load flags ────────────────────────────────────────────────────────────────
print('Loading flags...')
flags          = {}
flag_orig_dims = {}   # (orig_w, orig_h) — needed to compute aspect ratio for imshow extents
for country in df.columns:
    path = os.path.join('flags', safe_filename(country) + '.png')
    try:
        raw_img    = np.array(Image.open(path).convert('RGBA'))
        normalized = normalize_flag_aspect(raw_img)                      # pad to standard ratio
        flag_orig_dims[country] = (normalized.shape[1], normalized.shape[0])  # use normalised dims
        flags[country] = normalized
    except FileNotFoundError:
        pass  # missing flags are silently skipped; bars render without them

missing = [c for c in df.columns if c not in flags]
if missing:
    print(f'  No flag for {len(missing)} countries (they will render without one).')

# ── Figure setup (9:16 portrait) ──────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10.8, 19.2), dpi=100)
fig.patch.set_facecolor(BG_COLOR)
# Expand the axes to fill more of the figure → taller race area
# bottom=0.22 keeps race area out of YouTube Shorts UI zone (~bottom 20% covered)
plt.subplots_adjust(top=0.93, bottom=0.14, left=0.02, right=0.98)

# Axis dimensions in display pixels — used to convert flag size between pixels
# and data units inside update().  Must stay in sync with subplots_adjust above.
AXES_W_PX = (0.98 - 0.02) * 10.8 * 100   # 1036.8
AXES_H_PX = (0.93 - 0.14) * 19.2 * 100   # 1516.8

anim_state = {
    'frame_count': 0,
    'last_year':   int(df_scores.index[0]) - 1,
    'intensity':   0.0,
}

# ── Animation update ──────────────────────────────────────────────────────────
def update(frame: int):
    ax.clear()
    ax.set_facecolor(BG_COLOR)
    ax.axis('off')

    scores = df_scores.iloc[frame]
    ranks  = smooth_ranks.iloc[frame]
    year   = int(df_scores.index[frame])

    x_max = scores.max()
    if x_max <= 0:
        return

    # ── Layout geometry (all in data coords) ──────────────────────────────────
    #   |<─ LEFT ─>|<── 0 ──── score ──>|flag|<── RPAD ──────────────────────>|
    #   rank#          name ← flag → value   (name & value travel with the flag)
    LEFT   = x_max * 0.15   # just enough for rank numbers
    RPAD   = x_max * 0.38   # tight right margin → race area fills more of the frame

    ax.set_xlim(-LEFT, x_max + RPAD)
    ax.set_ylim(TOTAL - _ROW_SPAN - 1.6, TOTAL + 1.5)

    # Flags are rendered with ax.imshow using explicit data-coordinate extents.
    # This avoids the OffsetImage DPI/zoom ambiguity (OffsetImage renders at
    # image_px × zoom × dpi/72, making flags ~39% larger than calculated at
    # dpi=100, causing text overlap).  With imshow + extent the flag size is
    # derived geometrically: bar height (data units) → pixels via AXES_H_PX /
    # ylim_range → flag width via aspect ratio → data units via AXES_W_PX /
    # xlim_range.  Text clearance uses the same computed data-unit extents, so
    # overlap is impossible regardless of flag size or rank scale.
    xlim_range    = (x_max + RPAD) + LEFT          # total x data range
    ylim_range_fr = _ROW_SPAN + 2.3                 # total y data range (matches set_ylim)
    PX_TO_DU      = xlim_range / AXES_W_PX          # data units per display pixel (x)

    # Barrier: name never drifts left past the rank number zone
    NAME_MIN_X = -LEFT * 0.45

    # ── Draw each visible country ─────────────────────────────────────────────
    for country, score, rank in zip(scores.index, scores.values, ranks.values):
        if rank < TOTAL - N_ON_SCREEN - 0.5:
            continue  # outside camera window

        # Countries sliding in from below fade from 0→1 alpha over one rank slot
        entry_alpha  = float(np.clip(rank - (TOTAL - N_ON_SCREEN), 0.0, 1.0))
        display_rank = TOTAL - int(round(rank)) + 1
        is_top       = (display_rank == 1)

        # Proportional draw-y: large countries own more vertical space
        draw_y = rank_to_y(rank)

        # Size scale using shared constants (steep drop top-3, flatter below)
        scale = rank_scale(display_rank)

        # ── Flag size in data units (geometric approach) ──────────────────────
        # FLAG_FILL: fraction of each row slot the flag occupies vertically.
        # Keep below ~(slot_height / BAR_H) to avoid rank #1 touching rank #2.
        # With ROW_COMPACT=0.52 the rank-1 slot ≈ 0.52*9*0.139=0.651 du and
        # BAR_H=0.80, so max safe fill ≈ 0.651/0.80 = 0.81.  Using 0.78 leaves
        # a comfortable ~3% gap at the top while making flags noticeably bigger.
        FLAG_FILL = 0.78
        if country in flags:
            orig_w, orig_h = flag_orig_dims[country]
            flag_h_du  = BAR_H * scale * FLAG_FILL
            flag_h_px  = flag_h_du * AXES_H_PX / ylim_range_fr
            flag_w_px  = flag_h_px * (orig_w / orig_h)
            flag_w_du  = flag_w_px * xlim_range / AXES_W_PX
        else:
            flag_w_du  = 0.0
            flag_h_du  = 0.0

        # Text clearance: half the flag width + a small gap (4% of flag width)
        gap_du          = flag_w_du * 0.04 if flag_w_du > 0 else 8 * PX_TO_DU
        name_clearance  = flag_w_du / 2 + gap_du
        value_clearance = flag_w_du / 2 + gap_du

        rank_fs = max(12, round(28 * scale))
        name_fs = max(11, round(24 * scale))
        val_fs  = max(13, round(30 * scale))   # intentionally larger than name

        # Rank number — pinned to far left edge
        ax.text(-LEFT * 0.98, draw_y,
                f'#{display_rank}',
                va='center', ha='left',
                color='white', fontsize=rank_fs, fontweight='bold',
                alpha=(0.70 + 0.30 * is_top) * entry_alpha, zorder=4,
                fontfamily='Segoe UI')

        # Flag — rendered via imshow with explicit data-coordinate extent so
        # the rendered size exactly matches what we computed for text clearance.
        if country in flags:
            x0 = score - flag_w_du / 2
            x1 = score + flag_w_du / 2
            y0 = draw_y - flag_h_du / 2
            y1 = draw_y + flag_h_du / 2
            flag_img = flags[country]
            if entry_alpha < 1.0:
                flag_img = flag_img.copy()
                flag_img[..., 3] = (flag_img[..., 3] * entry_alpha).astype(np.uint8)
            ax.imshow(flag_img, extent=[x0, x1, y0, y1],
                      origin='upper', aspect='auto', zorder=5, clip_on=False)

        # Country name — left of flag when there is room, or right of flag
        # (appended after the value with a • separator) when the flag is close
        # to the rank-number zone.  Hard switch, no fading on either side.
        # Switch early enough so the full text width never overlaps the rank zone.
        label         = display_name(country)
        name_w_du_est = len(label) * name_fs * 0.58 * PX_TO_DU
        name_x        = score - name_clearance
        name_room     = name_x - NAME_MIN_X   # space between right-edge of name and rank zone
        on_left       = (name_room > name_w_du_est)
        base_alpha = (1.0 if is_top else 0.85) * entry_alpha
        val_label  = format_value(score, VALUE_FORMAT)
        val_left   = score + value_clearance

        if on_left:
            # Name right-aligned left of the flag
            ax.text(name_x, draw_y,
                    label,
                    va='center', ha='right',
                    color='white', fontsize=name_fs, fontweight='bold',
                    alpha=base_alpha, zorder=4,
                    fontfamily='Segoe UI')

            # Value right of the flag
            available_du = (x_max + RPAD) * 0.97 - val_left
            fit_fs       = available_du / max(len(val_label), 1) / (0.58 * PX_TO_DU)
            draw_val_fs  = max(11, min(val_fs, int(fit_fs)))
            ax.text(val_left, draw_y,
                    val_label,
                    va='center', ha='left',
                    color='white', fontsize=draw_val_fs, fontweight='bold',
                    alpha=entry_alpha, zorder=4,
                    fontfamily='Segoe UI')
        else:
            # Value • Name — combined right of the flag; fit_fs prevents overflow
            combined     = f"{val_label}  •  {label}"
            available_du = (x_max + RPAD) * 0.97 - val_left
            fit_fs       = available_du / max(len(combined), 1) / (0.58 * PX_TO_DU)
            draw_val_fs  = max(11, min(val_fs, int(fit_fs)))
            ax.text(val_left, draw_y,
                    combined,
                    va='center', ha='left',
                    color='white', fontsize=draw_val_fs, fontweight='bold',
                    alpha=entry_alpha, zorder=4,
                    fontfamily='Segoe UI')

    # ── Divider lines between bar slots (subtle, transformed to match spacing) ──
    for slot in range(TOTAL - N_ON_SCREEN + 1, TOTAL + 2):
        ax.axhline(y=rank_to_y(slot - 0.5), color='white', alpha=0.04, linewidth=0.8, zorder=1)

    # ── Sequential frame count (survives ax.clear each frame) ────────────────
    anim_state['frame_count'] += 1
    fc = anim_state['frame_count']

    # ── Year transition tracking ───────────────────────────────────────────────
    anim_state['intensity'] = max(0.0, anim_state['intensity'] - 0.035)
    if year > anim_state['last_year']:
        anim_state['intensity'] = 1.0
        anim_state['last_year'] = year
    intensity = anim_state['intensity']

    # ── Title (two lines) — slides in from above over first 50 frames ───────
    # Split "Military Spending Race (1960-2023)" → main + timeframe subtitle
    if ' (' in VIDEO_TITLE:
        title_main, title_sub = VIDEO_TITLE.split(' (', 1)
        title_sub = '(' + title_sub
    else:
        title_main, title_sub = VIDEO_TITLE, ''

    t_title  = min(1.0, fc / 50)
    t_ease   = t_title * t_title * (3 - 2 * t_title)   # smoothstep
    slide    = 1.0 - t_ease                              # 1→0 as it settles
    title_a  = t_ease * 0.92

    # Line 1 — main title, larger, settles at y=1.000 (very top edge)
    ax.text(0.5, 1.000 + slide * 0.08, title_main,
            transform=ax.transAxes,
            color='white', fontsize=36,
            ha='center', va='top',
            fontweight='bold', alpha=title_a,
            fontfamily='Segoe UI',
            clip_on=False)

    # Line 2 — timeframe, clearly spaced below line 1
    if title_sub:
        ax.text(0.5, 0.962 + slide * 0.08, title_sub,
                transform=ax.transAxes,
                color='white', fontsize=24,
                ha='center', va='top',
                fontweight='bold', alpha=title_a * 0.75,
                fontfamily='Segoe UI',
                clip_on=False)

    # ── Year counter — bottom-right of race area ──────────────────────────────
    ax.text(0.80, 0.08, str(year),
            transform=ax.transAxes,
            color='white', fontsize=58,
            ha='right', va='bottom',
            fontweight='bold', alpha=1.0,
            fontfamily='Segoe UI')

    # ── Source credit (bottom right, below year) ──────────────────────────────
    ax.text(0.80, 0.012, 'Source: World Bank',
            transform=ax.transAxes,
            color='white', fontsize=11,
            ha='right', va='bottom',
            alpha=0.35,
            fontfamily='Segoe UI')

# ── Render ────────────────────────────────────────────────────────────────────
# TEST_MODE: render only a short window for quick layout checks.
# Set to None to render the full video.
TEST_MODE = (1980, 1990)   # (start_year, end_year) or None

if TEST_MODE:
    y0, y1 = TEST_MODE
    idx = df_scores.index
    frame_range = [i for i, y in enumerate(idx) if y0 <= y <= y1]
    print(f'TEST MODE: rendering years {y0}-{y1} ({len(frame_range)} frames) => {OUTPUT_FILE}')
else:
    frame_range = range(len(df_scores))
    print(f'Rendering {len(frame_range)} frames => {OUTPUT_FILE}')
    print('  (This will take several minutes.)')

ani    = animation.FuncAnimation(fig, update, frames=frame_range, interval=30)
writer = animation.FFMpegWriter(fps=30, bitrate=8000)
ani.save(OUTPUT_FILE, writer=writer)
plt.close()

print(f'\nDone! => {OUTPUT_FILE}')
