"""Render-time manifest sidecar.

Each render writes `output/<basename>.manifest.json` capturing what was
rendered. The upload step reads it to fill the YouTube `videos.insert` body
and to populate the `videos` row in `cache/analytics.db`. This is the link
between "what we rendered" and "how it performed."
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

# Subset of render_cfg keys that affect visible output. We hash these so
# two renders with the same visual config share a render_cfg_hash even if
# unrelated keys (e.g. narration tone) differ.
_RENDER_CFG_VISUAL_KEYS = (
    'top_n_on_screen', 'steps_per_year', 'fps', 'race_top', 'race_bottom',
    'rank_smooth_window_a', 'rank_smooth_window_b', 'show_total_trend',
    'trend_label', 'flag_corner_radius_frac', 'row_min_weight', 'font_scale',
    'fonts', 'background_animation', 'spotlight', 'end_hold_seconds',
)


def _render_cfg_hash(render_cfg: dict) -> str:
    visual = {k: render_cfg.get(k) for k in _RENDER_CFG_VISUAL_KEYS
              if k in render_cfg}
    blob = json.dumps(visual, sort_keys=True, default=str).encode('utf-8')
    return hashlib.sha256(blob).hexdigest()[:16]


def _read_narration_snapshot(cache_dir: Path) -> dict:
    """Pull script_text + meta from cache/narration.json if it exists."""
    p = cache_dir / 'narration.json'
    if not p.exists():
        return {}
    try:
        doc = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        'source': (doc.get('meta') or {}).get('source'),
        'tone': (doc.get('meta') or {}).get('tone'),
        'model': (doc.get('meta') or {}).get('model'),
        'generated_at': (doc.get('meta') or {}).get('generated_at'),
        'script_text': doc.get('script_text'),
        'sections': doc.get('sections'),
    }


def write(*,
          channel: str,
          output_path: Path,
          cache_dir: Path,
          config_path: Path,
          config_snapshot: dict,
          render_cfg: dict,
          theme_name: str,
          dataset: dict,
          video_title: str,
          transforms: dict[str, Any] | None = None,
          source_credit: str | None = None) -> Path:
    """Write the manifest sidecar next to the rendered mp4. Returns its path.

    `output_path` is the rendered mp4 (e.g. `output/patents_race.mp4`). The
    manifest is `output/patents_race.manifest.json` — keyed to the bare stem
    so it applies equally to the `_narrated` mux output."""
    output_path = Path(output_path)
    # Strip _per_capita / _cumulative / _narrated suffixes off the stem so
    # one logical render maps to one manifest file.
    stem = output_path.stem
    for suf in ('_narrated', '_cumulative', '_per_capita'):
        if stem.endswith(suf):
            stem = stem[: -len(suf)]
    manifest_path = output_path.parent / f'{stem}.manifest.json'

    manifest = {
        'schema_version': SCHEMA_VERSION,
        'channel': channel,
        'rendered_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'config_path': str(config_path),
        'video_title': video_title,
        'output_filename': output_path.name,
        'output_stem': stem,
        'theme': theme_name,
        'dataset': dataset,
        'source_credit': source_credit,
        'transforms': transforms or {},
        'render_cfg_hash': _render_cfg_hash(render_cfg),
        'config_snapshot': config_snapshot,
        'narration': _read_narration_snapshot(cache_dir),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, default=str), encoding='utf-8')
    print(f"[manifest] wrote {manifest_path.name}")
    return manifest_path


def read(manifest_path: Path) -> dict:
    return json.loads(Path(manifest_path).read_text(encoding='utf-8'))


def find_for_video(output_dir: Path, video_filename: str) -> Path | None:
    """Resolve the manifest for a rendered (or narrated) mp4 filename."""
    stem = Path(video_filename).stem
    for suf in ('_narrated', '_cumulative', '_per_capita'):
        if stem.endswith(suf):
            stem = stem[: -len(suf)]
    p = Path(output_dir) / f'{stem}.manifest.json'
    return p if p.exists() else None
