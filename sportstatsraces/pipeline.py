"""Sports race pipeline — uses the shared races/ render engine with sport-side
defaults. Mirrors the world-stats narration flow: stat-pack + timeline →
variants → auto-assembled narration.json → ElevenLabs TTS → ducked music
mix → ffmpeg mux. Skips per-capita / accumulated / big-mover paths because
they are world-stats-specific.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from races.assets import build_provider
from races.assets.fonts import ensure_orbitron
from races.render import render, get_theme
from races.render.layout import auto_size_columns
from races.paths import output_dir as _output_dir
from races.sources import build_source


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
    stamp = ts.replace(':', '').replace('-', '').replace('Z', '')

    if json_path.exists():
        shutil.copy2(json_path, archive_dir / f'narration_{stamp}.json')
    if wav_path.exists():
        shutil.copy2(wav_path, archive_dir / f'narration_{stamp}.wav')
    print(f"[narration] archived prior narration to {archive_dir} (stamp={stamp})")


def run(config_path: Path, *,
        validate_layout: bool = False,
        generate_script: bool = False,
        generate_narration: bool = False,
        mux_narration: bool = False,
        generate_variants: bool = False,
        regenerate_section: str | None = None,
        auto_assemble: bool = False,
        preview_frame_year: float | None = None,
        preview_frame_years: list | str | None = None) -> None:
    cfg = json.loads(Path(config_path).read_text(encoding='utf-8'))
    repo_root = Path(config_path).resolve().parent
    cache_dir = repo_root / 'cache'
    output_dir = _output_dir(repo_root)
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
          f"seasons {int(result.data.index.min())}..{int(result.data.index.max())}.")

    provider = build_provider(asset_cfg, cache_dir)
    final = result.data.iloc[-1].dropna().sort_values(ascending=False)
    ranked_all = [c for c in final.index if c in result.icon_ids]
    extra = [c for c in result.icon_ids.keys() if c not in ranked_all]
    provider.ensure(ranked_all + extra, result.icon_ids)

    # ── --auto-assemble: pick variant option 0 per beat ────────────────
    if auto_assemble:
        from races.narration.assemble import write_narration_json
        variants_path = cache_dir / 'variants.json'
        if not variants_path.exists():
            raise SystemExit(
                f"--auto-assemble: {variants_path} not found. "
                "Run `python run.py --channel sports --generate-variants` first.")
        variants = json.loads(variants_path.read_text(encoding='utf-8'))
        for key in ('hooks', 'middles', 'endings'):
            if not variants.get(key):
                raise SystemExit(f"--auto-assemble: variants.json has no '{key}' options.")
        narration_cfg = (render_cfg.get('narration') or {})
        _archive_narration(cache_dir)
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

    # ── Narration build (variants / regenerate / generate-narration) ────
    if generate_narration or generate_script or generate_variants or regenerate_section:
        from races.render.big_movers import interpolate_and_rank
        from races.narration.script import (
            generate_variants as _generate_variants,
            regenerate_section as _regenerate_section,
        )
        from races.narration.voice import synthesize_voice
        from sportstatsraces.narration.stats import build_stat_pack
        from sportstatsraces.narration.timeline import build_timeline

        # Validate the configured prompt module imports cleanly before we
        # spend Anthropic tokens — surface a clear error here instead of
        # deep inside the script.py call.
        narration_cfg = dict(render_cfg.get('narration', {}))
        prompt_mod_path = narration_cfg.get('system_prompt_module')
        if prompt_mod_path:
            import importlib
            try:
                importlib.import_module(prompt_mod_path)
            except ImportError as exc:
                raise SystemExit(
                    f"narration.system_prompt_module={prompt_mod_path!r} "
                    f"could not be imported: {exc}"
                )

        narration_cfg['video_title'] = title
        narration_cfg['trend_label'] = render_cfg.get('trend_label')
        narration_cfg['value_mode'] = 'cumulative total'  # career goals
        steps_per_year = int(render_cfg.get('steps_per_year', 60))
        fps = int(render_cfg.get('fps', 30))
        smooth_a = int(render_cfg.get('rank_smooth_window_a', 25))
        smooth_b = int(render_cfg.get('rank_smooth_window_b', 35))
        n_on_screen = int(render_cfg.get('top_n_on_screen', 10))

        scores_df, ranks_df = interpolate_and_rank(
            result.data, steps_per_year, smooth_a, smooth_b,
            invert=bool(render_cfg.get('invert_ranking', False)))

        stat_pack = build_stat_pack(
            scores_df, ranks_df,
            steps_per_year=steps_per_year,
            value_format=value_format,
            video_title=title,
            n_on_screen=n_on_screen,
            invert_ranking=bool(render_cfg.get('invert_ranking', False)),
        )
        end_hold_seconds = float(render_cfg.get('end_hold_seconds', 0.0))
        timeline = build_timeline(
            scores_df, ranks_df,
            steps_per_year=steps_per_year,
            fps=fps,
            n_on_screen=n_on_screen,
            curated_movers_path=None,  # sports has no big-movers file
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

        # --generate-narration requires an auto-assembled narration.json.
        narration_json_path = cache_dir / 'narration.json'
        if not narration_json_path.exists():
            raise SystemExit(
                f"--generate-narration: {narration_json_path} not found. "
                "Run `--generate-variants` then `--auto-assemble` first.")
        existing = json.loads(narration_json_path.read_text(encoding='utf-8'))
        meta = existing.get('meta') or {}
        if meta.get('source') != 'auto' or not existing.get('script_text'):
            raise SystemExit(
                f"--generate-narration: {narration_json_path} is not an "
                "auto-assembled script (meta.source != 'auto'). Re-run "
                "`--generate-variants` then `--auto-assemble`.")
        script_doc = existing
        print(f"[narration] using pre-assembled script_text "
              f"(source=auto) from {narration_json_path}.")

        if generate_script and not generate_narration:
            print("[narration] script-only mode — nothing to do (script is "
                  "already in narration.json from --auto-assemble).")
            return

        # TTS first, then size the video to fit voice duration.
        voice_mp3, voice_seconds = synthesize_voice(
            script_doc=script_doc,
            narration_cfg=narration_cfg,
            clips_dir=cache_dir / 'narration_clips',
        )

        tail_buffer = float(narration_cfg.get('tail_buffer_seconds', 1.5))
        seasons = result.data.index.tolist()
        season_count = max(2, len(seasons))
        # Optional floor on body length (e.g. to fill a background video's
        # motion window even when the voice track runs shorter).
        min_body = float(narration_cfg.get('min_body_seconds', 0.0) or 0.0)
        target_body_frames = max(int(round(voice_seconds * fps)),
                                 int(round(min_body * fps)), season_count)
        spy_override = max(2, int(round((target_body_frames - 1) / (season_count - 1))))
        render_cfg['steps_per_year'] = spy_override
        render_cfg['end_hold_seconds'] = tail_buffer
        render_cfg['_pending_voice_mp3'] = voice_mp3
        render_cfg['_pending_voice_seconds'] = voice_seconds
        render_cfg['_pending_narration_cfg'] = narration_cfg
        render_cfg['_pending_mux'] = True
        new_body_s = ((season_count - 1) * spy_override + 1) / fps
        new_total_s = new_body_s + tail_buffer
        print(f"[narration] timing fit: voice={voice_seconds:.2f}s, "
              f"steps_per_year {steps_per_year}→{spy_override}, "
              f"body≈{new_body_s:.2f}s, end_hold={tail_buffer:.2f}s, "
              f"total≈{new_total_s:.2f}s")
        # Fall through to render block.

    # ── --mux-narration: mux narration.wav onto a previously-rendered mp4 ─
    if mux_narration:
        from races.narration.mux import mux_audio
        video_path = output_dir / output_name
        stem = Path(output_name).stem
        ext = Path(output_name).suffix or '.mp4'
        out_path = output_dir / f'{stem}_narrated{ext}'
        mux_audio(video_path, cache_dir / 'narration.wav', out_path)
        return

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

    # ── Voice mix + auto-mux when --generate-narration kicked us here ───
    if not is_single_frame and render_cfg.get('_pending_mux'):
        from races.narration.voice import mix_voice_with_music
        from races.narration.mux import mux_audio
        voice_mp3 = render_cfg['_pending_voice_mp3']
        voice_seconds = float(render_cfg['_pending_voice_seconds'])
        narration_cfg_post = render_cfg['_pending_narration_cfg']
        fps_post = int(render_cfg.get('fps', 30))
        tail_buffer = float(narration_cfg_post.get('tail_buffer_seconds', 1.5))
        season_count = max(2, len(result.data.index))
        spy = int(render_cfg['steps_per_year'])
        body_s = ((season_count - 1) * spy + 1) / fps_post
        total_s = body_s + tail_buffer
        mix_voice_with_music(
            voice_mp3=voice_mp3,
            narration_cfg=narration_cfg_post,
            video_duration_seconds=total_s,
            out_wav_path=cache_dir / 'narration.wav',
            repo_root=repo_root,
        )
        video_path = output_dir / output_name
        stem = Path(output_name).stem
        ext = Path(output_name).suffix or '.mp4'
        narrated_path = output_dir / f'{stem}_narrated{ext}'
        mux_audio(video_path, cache_dir / 'narration.wav', narrated_path)
        print(f"[narration] tail (post-voice) ≈ {total_s - voice_seconds:.2f}s")

    if not is_single_frame:
        from races.youtube import manifest as _manifest
        _manifest.write(
            channel='sports',
            output_path=output_dir / output_name,
            cache_dir=cache_dir,
            config_path=Path(config_path),
            config_snapshot=cfg,
            render_cfg=render_cfg,
            theme_name=cfg.get('theme', 'glass_dark_black'),
            dataset={
                'source_type': source_cfg.get('type'),
                'indicator': source_cfg.get('indicator'),
                'season': source_cfg.get('season'),
                'competition': source_cfg.get('competition'),
            },
            video_title=title,
            transforms={},
            source_credit=result.source_credit,
        )
