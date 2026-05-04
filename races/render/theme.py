"""Theme system — visual params separated from renderer logic."""

import hashlib
from dataclasses import dataclass, field
from typing import Literal, Tuple, Union

# Vivid Tailwind 400-series — reads well on dark backgrounds.
PALETTE = [
    '#f87171', '#60a5fa', '#4ade80', '#fbbf24', '#a78bfa',
    '#34d399', '#fb923c', '#f472b6', '#38bdf8', '#a3e635',
    '#818cf8', '#e879f9', '#2dd4bf', '#facc15', '#c084fc',
    '#22d3ee', '#86efac', '#fca5a5', '#93c5fd', '#fde68a',
]


# background: solid hex
#  OR ("gradient", c_top, c_bottom)
#  OR ("radial", c_center, c_edge)
#  OR ("radial_drift", [c_center_1, c_center_2, ...], c_edge)
BackgroundSpec = Union[str, Tuple]


@dataclass
class Theme:
    name: str
    background: BackgroundSpec
    bar_style: Literal['glass', 'solid', 'gradient']
    bar_corner_radius_px: int
    bar_opacity: float
    bar_backdrop: bool            # translucent wider rect behind bar (frosted tint)
    bar_inner_gradient: bool      # light highlight band within bar
    row_card: bool
    row_card_color: str
    row_card_opacity: float
    row_card_corner_radius_px: int
    title_card: bool
    title_card_color: str
    title_card_opacity: float
    font_family: str
    accent_palette: list = field(default_factory=lambda: list(PALETTE))
    text_primary: str = '#ffffff'
    text_secondary: str = '#cbd5e1'
    show_sparkline: bool = True
    show_total: bool = True
    smooth_year_ticker: bool = True
    rank_flash: bool = True


GLASS_DARK = Theme(
    name='glass_dark',
    background=('radial', '#1e293b', '#000000'),
    bar_style='glass',
    bar_corner_radius_px=18,
    bar_opacity=0.55,
    bar_backdrop=True,
    bar_inner_gradient=True,
    row_card=True,
    row_card_color='#ffffff',
    row_card_opacity=0.04,
    row_card_corner_radius_px=22,
    title_card=True,
    title_card_color='#ffffff',
    title_card_opacity=0.08,
    font_family='Orbitron',
)

# Dark center palette for the drifting radial. All entries are deliberately
# low-lightness so the frame never brightens too much; edges stay pure black
# via the radial smoothstep falloff in renderer._draw_background.
DARK_DRIFT_CENTERS = [
    '#1e293b',  # slate blue (matches glass_dark default)
    '#3b1e3a',  # dark plum
    '#1e3a32',  # dark forest
    '#3a1e1e',  # dark crimson
    '#2a1e3a',  # dark indigo
]

GLASS_DARK_DRIFT = Theme(
    name='glass_dark_drift',
    background=('radial_drift', DARK_DRIFT_CENTERS, '#000000'),
    bar_style='glass',
    bar_corner_radius_px=18,
    bar_opacity=0.55,
    bar_backdrop=True,
    bar_inner_gradient=True,
    row_card=True,
    row_card_color='#ffffff',
    row_card_opacity=0.04,
    row_card_corner_radius_px=22,
    title_card=True,
    title_card_color='#ffffff',
    title_card_opacity=0.08,
    font_family='Orbitron',
)


GLASS_DARK_BLACK = Theme(
    name='glass_dark_black',
    background='#000000',
    bar_style='glass',
    bar_corner_radius_px=18,
    bar_opacity=0.55,
    bar_backdrop=True,
    bar_inner_gradient=True,
    row_card=True,
    row_card_color='#ffffff',
    row_card_opacity=0.04,
    row_card_corner_radius_px=22,
    title_card=True,
    title_card_color='#ffffff',
    title_card_opacity=0.08,
    font_family='Orbitron',
)


THEMES = {
    GLASS_DARK.name: GLASS_DARK,
    GLASS_DARK_DRIFT.name: GLASS_DARK_DRIFT,
    GLASS_DARK_BLACK.name: GLASS_DARK_BLACK,
}


def get_theme(name: str) -> Theme:
    if name not in THEMES:
        raise ValueError(f"Unknown theme '{name}'. Available: {list(THEMES)}")
    return THEMES[name]


def assign_colors(names, palette) -> dict:
    """Deterministic color per name via MD5 hash — stable across re-renders."""
    out = {}
    for name in names:
        idx = int(hashlib.md5(name.encode()).hexdigest(), 16) % len(palette)
        out[name] = palette[idx]
    return out
