"""End-to-end orchestration: fetch source → download assets → render video."""

import json
import shutil
from datetime import datetime
from pathlib import Path

from .sources import build_source
from .sources.world_bank import WorldBankSource
from .assets import build_provider
from .assets.fonts import ensure_orbitron
from .render import render, get_theme


def _archive_narration(cache_dir: Path) -> None:
    """Copy existing narration.json / narration.wav into a timestamped archive
    so they aren't overwritten by the next --generate-narration run."""
    json_path = cache_dir / 'narration.json'
    wav_path = cache_dir / 'narration.wav'
    if not json_path.exists() and not wav_path.exists():
        return
    archive_dir = cache_dir / 'narration_archive'
    archive_dir.mkdir(parents=True, exist_ok=True)

    ts = None
    if json_path.exists():
        try:
            meta = json.loads(json_path.read_text(encoding='utf-8')).get('meta', {})
            ts = meta.get('generated_at')
        except (OSError, json.JSONDecodeError):
            ts = None
    if not ts:
        src = json_path if json_path.exists() else wav_path
        ts = datetime.utcfromtimestamp(src.stat().st_mtime).strftime('%Y-%m-%dT%H:%M:%SZ')
    stamp = ts.replace(':', '').replace('-', '').replace('Z', '')  # safe filename

    if json_path.exists():
        shutil.copy2(json_path, archive_dir / f'narration_{stamp}.json')
    if wav_path.exists():
        shutil.copy2(wav_path, archive_dir / f'narration_{stamp}.wav')
    print(f"[narration] archived prior narration to {archive_dir} (stamp={stamp})")


def run(config_path: Path, *, refetch: bool = False,
        validate_layout: bool = False,
        extract_movers: bool = False,
        generate_script: bool = False,
        generate_narration: bool = False,
        mux_narration: bool = False,
        generate_variants: bool = False,
        regenerate_section: str | None = None,
        auto_assemble: bool = False,
        per_capita_override: bool | None = None,
        accumulated_override: bool | None = None,
        preview_frame_year: float | None = None,
        preview_frame_years: list | str | None = None) -> None:
    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    repo_root = config_path.parent
    cache_dir = repo_root / 'cache'
    output_dir = repo_root / 'output'
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_cfg = cfg['source']
    asset_cfg = cfg.get('assets', {'type': 'flags'})
    render_cfg = dict(cfg.get('render', {}))
    theme = get_theme(cfg.get('theme', 'glass_dark'))
    value_format = cfg.get('value_format', 'currency')
    if 'value_suffix' in cfg:
        render_cfg['value_suffix'] = cfg['value_suffix']
    title = cfg.get('video_title', 'Race')
    output_name = cfg.get('output_filename', 'race.mp4')
    preview = cfg.get('preview_timeframe')
    preview = tuple(preview) if preview else None

    # ── Source (fetch or load from cache) ────────────────────────────────────
    source = build_source(source_cfg)
    cache_ready = (cache_dir / 'race_data.csv').exists() and (cache_dir / 'icon_ids.json').exists()
    if refetch or not cache_ready:
        result = source.fetch()
        WorldBankSource.write_cache(result, cache_dir)
    else:
        print("Using cached source data (pass --refetch to re-download).")
        result = WorldBankSource.read_cache(cache_dir, source.source_credit)

    # ── Per-capita transform (optional) ─────────────────────────────────────
    per_capita = (per_capita_override if per_capita_override is not None
                  else bool(cfg.get('per_capita', False)))
    if per_capita:
        if result.population is None:
            raise SystemExit(
                "Per-capita mode requested but cache/population.csv is missing. "
                "Run `python run.py --refetch` to fetch population data.")
        pop = result.population.copy()
        pop.index = pop.index.astype(int)
        pop = pop.reindex(index=result.data.index, columns=result.data.columns)
        pop = pop.ffill().bfill()
        pop = pop.where(pop > 0)  # avoid div-by-zero
        # Worldwide per-capita trend = Σ(raw spending) / Σ(population) per year.
        # Computed BEFORE the per-country division so the trend reflects the
        # global average per person rather than a meaningless sum of
        # per-capita values across countries of wildly different sizes.
        _world_pc_yearly = (
            result.data.fillna(0).sum(axis=1) / pop.fillna(0).sum(axis=1)
        ).replace([float('inf'), float('-inf')], float('nan'))
        render_cfg['_world_trend_yearly'] = _world_pc_yearly
        result.data = (result.data / pop).dropna(axis=1, how='all')
        stem, ext = (output_name.rsplit('.', 1) + ['mp4'])[:2]
        if not stem.endswith('_per_capita'):
            output_name = f"{stem}_per_capita.{ext}"
        # Trend label: explicit override wins; otherwise auto-insert "per capita".
        override_label = render_cfg.get('trend_label_per_capita')
        base_label = render_cfg.get('trend_label')
        if override_label:
            render_cfg['trend_label'] = override_label
        elif base_label and 'per capita' not in base_label.lower():
            if ' — ' in base_label:
                head, tail = base_label.split(' — ', 1)
                render_cfg['trend_label'] = f"{head} per capita — {tail}"
            else:
                render_cfg['trend_label'] = f"{base_label} per capita"
        print(f"[per-capita] applied — title='{title}', output='{output_name}', "
              f"trend_label='{render_cfg.get('trend_label', '')}', "
              f"{len(result.data.columns)} countries remain.")

    # ── Accumulated (cumulative-sum) transform (optional) ───────────────────
    accumulated = (accumulated_override if accumulated_override is not None
                   else bool(cfg.get('accumulated', False)))
    if accumulated:
        result.data = result.data.fillna(0).cumsum().dropna(axis=1, how='all')
        if '_world_trend_yearly' in render_cfg:
            render_cfg['_world_trend_yearly'] = (
                render_cfg['_world_trend_yearly'].fillna(0).cumsum())
        stem, ext = (output_name.rsplit('.', 1) + ['mp4'])[:2]
        if not stem.endswith('_cumulative'):
            output_name = f"{stem}_cumulative.{ext}"
        # Trend label: explicit override wins; otherwise prefix "Cumulative ".
        override_label = render_cfg.get('trend_label_accumulated')
        base_label = render_cfg.get('trend_label')
        if override_label:
            render_cfg['trend_label'] = override_label
        elif base_label and 'cumulative' not in base_label.lower():
            # Replace a leading "Total " with "Cumulative " if present, else prepend.
            if base_label.lower().startswith('total '):
                render_cfg['trend_label'] = 'Cumulative ' + base_label[len('Total '):]
            else:
                render_cfg['trend_label'] = f"Cumulative {base_label}"
        print(f"[accumulated] applied — title='{title}', output='{output_name}', "
              f"trend_label='{render_cfg.get('trend_label', '')}'.")

    # ── Optional unit scaling (e.g. Mt → t = 1e6) ────────────────────────────
    value_scale = cfg.get('value_scale')
    if value_scale and float(value_scale) != 1.0:
        scale = float(value_scale)
        result.data = result.data * scale
        if '_world_trend_yearly' in render_cfg:
            render_cfg['_world_trend_yearly'] = render_cfg['_world_trend_yearly'] * scale
        print(f"[value_scale] applied ×{scale:g}")

    # ── Assets ───────────────────────────────────────────────────────────────
    provider = build_provider(asset_cfg, cache_dir)
    # Fetch flags for every country we have an icon id for, so the spotlight
    # (which surfaces non-top-N movers) never renders text-only. top_n_to_fetch
    # is kept as a lower bound but no longer caps the set.
    final = result.data.iloc[-1].dropna().sort_values(ascending=False)
    ranked_all = [c for c in final.index if c in result.icon_ids]
    extra = [c for c in result.icon_ids.keys() if c not in ranked_all]
    all_names = ranked_all + extra
    provider.ensure(all_names, result.icon_ids)

    # Warn about any country that appears in the data but has no flag on disk.
    from .util import safe_filename
    missing = [c for c in result.data.columns
               if result.data[c].notna().any()
               and not (cache_dir / 'flags' / (safe_filename(c) + '.png')).exists()]
    if missing:
        print(f"[flags] WARNING: {len(missing)} country/countries in the dataset have no flag:")
        for c in missing[:20]:
            iso = result.icon_ids.get(c, '?')
            print(f"  - {c}  (iso2={iso})")
        if len(missing) > 20:
            print(f"  ...and {len(missing) - 20} more")

    # ── Extract big-mover candidates and exit (no render) ──────────────────
    if extract_movers:
        from .render.big_movers import extract_and_write
        extract_and_write(
            data=result.data,
            render_cfg=render_cfg,
            value_format=value_format,
            source_indicator=source_cfg.get('indicator', ''),
            out_path=cache_dir / 'big_movers.json',
        )
        return

    # ── Generate narration (script + optional TTS) and exit ──────────────
    if auto_assemble:
        from .narration.assemble import write_narration_json
        variants_path = cache_dir / 'variants.json'
        if not variants_path.exists():
            raise SystemExit(
                f"--auto-assemble: {variants_path} not found. "
                "Run `python run.py --generate-variants` first.")
        variants = json.loads(variants_path.read_text(encoding='utf-8'))
        for key in ('hooks', 'middles', 'endings'):
            if not variants.get(key):
                raise SystemExit(f"--auto-assemble: variants.json has no '{key}' options.")
        narration_cfg = (cfg.get('render') or {}).get('narration') or {}
        write_narration_json(
            hook=variants['hooks'][0],
            middle=variants['middles'][0],
            ending=variants['endings'][0],
            narration_path=cache_dir / 'narration.json',
            tone=narration_cfg.get('tone'),
            words_per_second=float(narration_cfg.get('words_per_second', 2.7)),
            source='auto',
        )
        print(f"[auto-assemble] wrote {cache_dir / 'narration.json'} "
              "(picked option 0 from each section).")
        return

    if generate_narration or generate_script or generate_variants or regenerate_section:
        from .render.big_movers import interpolate_and_rank
        from .narration.stats import build_stat_pack
        from .narration.timeline import build_timeline
        from .narration.script import (
            generate_script as _generate_script,
            generate_variants as _generate_variants,
            regenerate_section as _regenerate_section,
        )
        from .narration.voice import synthesize

        narration_cfg = dict(render_cfg.get('narration', {}))
        if accumulated and per_capita:
            mode = 'cumulative per capita'
        elif accumulated:
            mode = 'cumulative total'
        elif per_capita:
            mode = 'per capita'
        else:
            mode = 'total'
        narration_cfg['value_mode'] = mode
        steps_per_year = int(render_cfg.get('steps_per_year', 60))
        fps = int(render_cfg.get('fps', 30))
        smooth_a = int(render_cfg.get('rank_smooth_window_a', 25))
        smooth_b = int(render_cfg.get('rank_smooth_window_b', 35))
        n_on_screen = int(render_cfg.get('top_n_on_screen', 10))

        scores_df, ranks_df = interpolate_and_rank(
            result.data, steps_per_year, smooth_a, smooth_b)

        stat_pack = build_stat_pack(
            scores_df, ranks_df,
            steps_per_year=steps_per_year,
            value_format=value_format,
            video_title=title,
            n_on_screen=n_on_screen,
        )
        spotlight_cfg = render_cfg.get('spotlight', {}) or {}
        curated_rel = spotlight_cfg.get('curated_file')
        curated_path = (repo_root / curated_rel) if curated_rel else None
        end_hold_seconds = float(render_cfg.get('end_hold_seconds', 0.0))
        timeline = build_timeline(
            scores_df, ranks_df,
            steps_per_year=steps_per_year,
            fps=fps,
            n_on_screen=n_on_screen,
            curated_movers_path=curated_path,
            preview_timeframe=preview,
            end_hold_seconds=end_hold_seconds,
        )

        if generate_variants:
            _generate_variants(
                stat_pack=stat_pack,
                timeline=timeline,
                narration_cfg=narration_cfg,
                out_path=cache_dir / 'variants.json',
            )
            return

        if regenerate_section:
            _regenerate_section(
                section=regenerate_section,
                stat_pack=stat_pack,
                timeline=timeline,
                narration_cfg=narration_cfg,
                out_path=cache_dir / 'variants.json',
            )
            return

        # If --auto-assemble already wrote narration.json with source=auto,
        # honor that exact script instead of regenerating.
        narration_json_path = cache_dir / 'narration.json'
        pre_assembled = False
        script_doc: dict | None = None
        if narration_json_path.exists():
            try:
                existing = json.loads(narration_json_path.read_text(encoding='utf-8'))
                meta = existing.get('meta') or {}
                if meta.get('source') == 'auto' and existing.get('script_text'):
                    pre_assembled = True
                    script_doc = existing
                    print(f"[narration] using pre-assembled script_text "
                          f"(source=auto) from {narration_json_path} "
                          f"(skipping LLM regeneration).")
            except (OSError, json.JSONDecodeError):
                pass

        if not pre_assembled:
            _archive_narration(cache_dir)
            script_doc = _generate_script(
                stat_pack=stat_pack,
                timeline=timeline,
                narration_cfg=narration_cfg,
                out_path=narration_json_path,
            )
        if script_doc.get('suggested_trim'):
            st = script_doc['suggested_trim']
            print(f"[narration] suggested_trim: start_year={st.get('start_year')} "
                  f"— {st.get('reason')} (not applied; update config.json manually)")

        if generate_script and not generate_narration:
            print("[narration] script-only mode — skipping ElevenLabs TTS to save credits.")
            return

        synthesize(
            script_doc=script_doc,
            narration_cfg=narration_cfg,
            video_duration_seconds=timeline['video_duration_seconds'],
            clips_dir=cache_dir / 'narration_clips',
            out_wav_path=cache_dir / 'narration.wav',
            repo_root=repo_root,
        )
        return

    # ── Mux narration onto rendered video and exit ───────────────────────
    if mux_narration:
        from .narration.mux import mux_audio
        video_path = output_dir / output_name
        stem = Path(output_name).stem
        ext = Path(output_name).suffix or '.mp4'
        out_path = output_dir / f'{stem}_narrated{ext}'
        mux_audio(video_path, cache_dir / 'narration.wav', out_path)
        return

    # ── Layout validation (optional) ─────────────────────────────────────────
    if validate_layout:
        from .render.renderer import validate_layout as vl
        bounds = vl()
        print("Column bounds (px):")
        for k, (l, r) in bounds.items():
            print(f"  {k:6s} {l:7.1f} → {r:7.1f}  (width {r - l:6.1f})")

    # ── Fonts ────────────────────────────────────────────────────────────────
    ensure_orbitron(cache_dir)

    # ── Resolve --preview-frames "auto" against the data's year range ────────
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

    # ── Render ───────────────────────────────────────────────────────────────
    render(
        data=result.data,
        load_icon=provider.load,
        title=title,
        value_format=value_format,
        source_credit=result.source_credit,
        theme=theme,
        output_path=output_dir / output_name,
        render_cfg=render_cfg,
        preview_timeframe=preview if not is_single_frame else None,
        single_frame_year=preview_frame_year,
        single_frame_png_path=(cache_dir / 'preview_frame.png'
                               if preview_frame_year is not None else None),
        single_frame_years=resolved_preview_years,
        single_frames_dir=(cache_dir / 'preview_frames'
                           if resolved_preview_years is not None else None),
    )
