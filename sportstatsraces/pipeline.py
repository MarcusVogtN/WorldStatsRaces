"""Sports race pipeline — uses the shared races/ render engine with sport-side
defaults. Skips per-capita / accumulated / narration / big-mover paths because
they are domain-specific to the world-stats channel.
"""

from __future__ import annotations

import json
from pathlib import Path

from races.assets import build_provider
from races.assets.fonts import ensure_orbitron
from races.render import render, get_theme
from races.render.layout import auto_size_columns
from races.sources import build_source


def run(config_path: Path, *,
        validate_layout: bool = False,
        preview_frame_year: float | None = None,
        preview_frame_years: list | str | None = None) -> None:
    cfg = json.loads(Path(config_path).read_text(encoding='utf-8'))
    repo_root = Path(config_path).resolve().parent
    cache_dir = repo_root / 'cache'
    output_dir = repo_root / 'output'
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_cfg = cfg['source']
    asset_cfg = cfg.get('assets', {'type': 'headshots'})
    render_cfg = dict(cfg.get('render', {}))
    theme = get_theme(cfg.get('theme', 'glass_dark_black'))
    value_format = cfg.get('value_format', 'goals')
    title = cfg.get('video_title', 'Race')
    output_name = cfg.get('output_filename', 'race.mp4')
    preview = cfg.get('preview_timeframe')
    preview = tuple(preview) if preview else None

    source = build_source(source_cfg)
    result = source.fetch()
    print(f"[source] {len(result.data.columns)} entities, "
          f"years {int(result.data.index.min())}..{int(result.data.index.max())}.")

    provider = build_provider(asset_cfg, cache_dir)
    final = result.data.iloc[-1].dropna().sort_values(ascending=False)
    ranked_all = [c for c in final.index if c in result.icon_ids]
    extra = [c for c in result.icon_ids.keys() if c not in ranked_all]
    provider.ensure(ranked_all + extra, result.icon_ids)

    if validate_layout:
        from races.render.renderer import validate_layout as vl
        bounds = vl()
        print("Column bounds (px):")
        for k, (l, r) in bounds.items():
            print(f"  {k:6s} {l:7.1f} → {r:7.1f}  (width {r - l:6.1f})")

    ensure_orbitron(cache_dir)

    resolved_preview_years: list | None = None
    if preview_frame_years is not None:
        if isinstance(preview_frame_years, str) and preview_frame_years == 'auto':
            years = sorted(float(y) for y in result.data.index)
            if years:
                y0, y1 = years[0], years[-1]
                span = y1 - y0
                resolved_preview_years = [y0, y0 + span * 0.25, y0 + span * 0.5,
                                          y0 + span * 0.75, y1]
        elif isinstance(preview_frame_years, list):
            resolved_preview_years = list(preview_frame_years)

    is_single_frame = preview_frame_year is not None or resolved_preview_years is not None

    columns, name_max_chars = auto_size_columns(
        result.data, int(render_cfg.get('top_n_on_screen', 10)))
    render_cfg['name_max_chars'] = name_max_chars

    render(
        data=result.data,
        load_icon=provider.load,
        title=title,
        value_format=value_format,
        source_credit=result.source_credit,
        theme=theme,
        output_path=output_dir / output_name,
        render_cfg=render_cfg,
        columns=columns,
        preview_timeframe=preview if not is_single_frame else None,
        single_frame_year=preview_frame_year,
        single_frame_png_path=(cache_dir / 'preview_frame.png'
                               if preview_frame_year is not None else None),
        single_frame_years=resolved_preview_years,
        single_frames_dir=(cache_dir / 'preview_frames'
                           if resolved_preview_years is not None else None),
    )
