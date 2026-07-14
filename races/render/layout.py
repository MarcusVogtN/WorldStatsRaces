"""Fixed-column layout for the flag race.

Coordinates are in axes-fraction space (0..1). xlim/ylim = (0,1) in the renderer.

Column layout (left to right):

    [ name box: rank + country ][ gutter ][ ─── flag racing track ─── ]

Flags move horizontally within the track based on value. The name box is a
glassmorphic card that physically separates rank+name from the track; value
text can never cross into it.
"""

from dataclasses import dataclass
import numpy as np


@dataclass
class Columns:
    # Rank number sits inside the name box, right-aligned at rank_x.
    rank_x: float
    # Name text left-aligned at name_left.
    name_left: float
    # Glass name-box bounds (fixed, independent of text length).
    name_box_left: float
    name_box_right: float
    # Racing track bounds.
    track_left: float
    track_right: float


DEFAULT_COLUMNS = Columns(
    rank_x=0.085,
    name_left=0.100,
    name_box_left=0.040,
    name_box_right=0.310,
    track_left=0.330,
    track_right=0.820,
)


@dataclass
class VerticalLayout:
    race_top: float
    race_bottom: float
    n_on_screen: int

    @property
    def race_height(self) -> float:
        return self.race_top - self.race_bottom


def track_position(value: float, max_value: float,
                    track_left: float, track_right: float,
                    flag_width: float, floor: float = 0.02) -> float:
    """Left edge x for a flag based on value.

    Rank #1 (value == max) places the flag's right edge at track_right.
    A small floor keeps zero/NaN values visible at the start line.
    """
    usable = max(track_right - track_left - flag_width, 0.0)
    if max_value <= 0 or not np.isfinite(value) or value <= 0:
        t = floor
    else:
        t = floor + (1.0 - floor) * float(np.clip(value / max_value, 0.0, 1.0))
    return track_left + t * usable


def smoothstep(t: float) -> float:
    t = float(np.clip(t, 0.0, 1.0))
    return t * t * (3 - 2 * t)


# Auto-name-box sizing — used by both pipelines so long-name datasets
# (footballer rosters, full country names) don't get truncated unnecessarily.
_NAME_FS_MAX = 21.0
_CHAR_W_FRAC = _NAME_FS_MAX * 1.05 / 1080.0  # match renderer's per-char estimate (Orbitron is wide)
_NAME_BOX_LEFT = 0.040
_NAME_LEFT = 0.100
_RANK_X = 0.085
_TRACK_RIGHT = 0.820
_GUTTER = 0.020
_NAME_BOX_RIGHT_PAD = 0.018
_NAME_BOX_MIN_RIGHT = 0.310
_NAME_BOX_MAX_RIGHT = 0.530


def auto_size_columns(data, top_n_on_screen: int) -> tuple[Columns, int]:
    """Pick name-box width to fit the longest entity that ever lands in top-N.

    Walks every row of `data`, takes that row's top-N entities, unions the set,
    and sizes `name_box_right` to fit the longest. Returns (columns, name_max_chars)
    where `name_max_chars` is the cap fed back into `render_cfg` so the
    renderer's `..` truncation only kicks in for genuine outliers.
    """
    seen: set[str] = set()
    for _, row in data.iterrows():
        top = row.dropna().sort_values(ascending=False).head(top_n_on_screen)
        seen.update(map(str, top.index))

    longest = max((len(name) for name in seen), default=0)
    needed_right = _NAME_LEFT + longest * _CHAR_W_FRAC + _NAME_BOX_RIGHT_PAD
    name_box_right = max(_NAME_BOX_MIN_RIGHT,
                         min(_NAME_BOX_MAX_RIGHT, needed_right))
    chars_that_fit = int((name_box_right - _NAME_LEFT - _NAME_BOX_RIGHT_PAD)
                         / _CHAR_W_FRAC)
    name_max_chars = max(longest, chars_that_fit)

    longest_name = max(seen, key=len) if seen else ''
    print(f"[layout] {len(seen)} ever-top-{top_n_on_screen} entities · "
          f"longest name: '{longest_name}' ({longest} chars) · "
          f"name_box_right={name_box_right:.3f} · name_max_chars={name_max_chars}")

    return Columns(
        rank_x=_RANK_X,
        name_left=_NAME_LEFT,
        name_box_left=_NAME_BOX_LEFT,
        name_box_right=name_box_right,
        track_left=name_box_right + _GUTTER,
        track_right=_TRACK_RIGHT,
    ), name_max_chars
