"""Markdown analytics report.

v1: top-N rollups + per-video retention drop-off aligned to narration
sections. Reads cache/analytics.db and the manifests recorded against
each video. Output goes to `output/analytics_report.md`.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from . import manifest as manifest_mod
from . import store


def _fmt_pct(x: float | None) -> str:
    """YouTube Analytics `averageViewPercentage` already comes back as a
    percentage (0-100+), not a 0-1 ratio."""
    return f'{x:.1f}%' if isinstance(x, (int, float)) and x is not None else '--'


def _fmt_num(x) -> str:
    if x is None:
        return '—'
    if isinstance(x, float):
        return f'{x:,.1f}'
    try:
        return f'{int(x):,}'
    except (TypeError, ValueError):
        return str(x)


def _aggregate_video(conn: sqlite3.Connection, video_id: str,
                     since: str) -> dict:
    cur = conn.execute(
        "SELECT "
        "  SUM(views) AS views, "
        "  SUM(watch_time_minutes) AS wtm, "
        "  AVG(avg_view_duration_s) AS avd, "
        "  AVG(avg_view_percentage) AS avp, "
        "  SUM(likes) AS likes, "
        "  SUM(dislikes) AS dislikes, "
        "  SUM(comments) AS comments, "
        "  SUM(subscribers_gained) AS subs_g, "
        "  SUM(subscribers_lost) AS subs_l "
        "FROM metrics_daily WHERE video_id=? AND date >= ?",
        (video_id, since))
    return dict(cur.fetchone() or {})


def _section_breakpoints(narration: dict) -> list[tuple[str, float]]:
    """Map narration sections to elapsed_ratio cutoffs by word-count share.
    Returns [(section_name, end_ratio), ...]. Approximate but useful enough
    to label retention drop-offs."""
    sections = (narration or {}).get('sections') or {}
    if not sections:
        return []
    order = ('hook', 'middle', 'ending')
    counts = [(name, len((sections.get(name) or '').split()))
              for name in order if sections.get(name)]
    total = sum(c for _, c in counts) or 1
    out, acc = [], 0
    for name, c in counts:
        acc += c
        out.append((name, acc / total))
    return out


def _retention_drops(conn: sqlite3.Connection, video_id: str,
                     narration: dict) -> str:
    """Find the steepest drops in the latest retention snapshot and label
    each with the narration section it overlaps."""
    cur = conn.execute(
        "SELECT snapshot_date, elapsed_ratio, relative_retention "
        "FROM retention_curve WHERE video_id=? "
        "ORDER BY snapshot_date DESC, elapsed_ratio ASC",
        (video_id,))
    rows = cur.fetchall()
    if not rows:
        return '_no retention snapshot yet_'
    latest = rows[0]['snapshot_date']
    points = [(r['elapsed_ratio'], r['relative_retention'])
              for r in rows if r['snapshot_date'] == latest
              and r['elapsed_ratio'] is not None
              and r['relative_retention'] is not None]
    if len(points) < 3:
        return '_retention curve too short to analyze_'
    points.sort()

    breakpoints = _section_breakpoints(narration)

    def section_at(ratio: float) -> str:
        for name, end in breakpoints:
            if ratio <= end:
                return name
        return breakpoints[-1][0] if breakpoints else 'unknown'

    # Compute frame-to-frame deltas; flag the 3 steepest drops.
    drops = []
    for (r0, v0), (r1, v1) in zip(points, points[1:]):
        delta = v1 - v0
        if delta < 0:
            drops.append((delta, r0, r1, v0, v1))
    drops.sort()
    if not drops:
        return '_retention is flat or rising — unusually good_'

    lines = [f'Retention snapshot {latest}; '
             f'first-frame retention {points[0][1]*100:.0f}%, '
             f'last-frame {points[-1][1]*100:.0f}%.']
    lines.append('Steepest drops:')
    for delta, r0, r1, v0, v1 in drops[:3]:
        sec = section_at((r0 + r1) / 2)
        lines.append(
            f'- {r0*100:>4.0f}% → {r1*100:>4.0f}% of video: '
            f'{v0*100:>4.0f}% → {v1*100:>4.0f}% retention '
            f'({delta*100:+.1f} pp) — _{sec}_')
    return '\n'.join(lines)


def generate(repo_root: Path,
             channel: str | None = None,
             lookback_days: int = 30,
             out_path: Path | None = None) -> Path:
    db = store.db_path_for(repo_root)
    if not db.exists():
        raise SystemExit(
            f"No analytics database at {db}. Run --pull-analytics first.")

    since = (date.today() - timedelta(days=lookback_days)).isoformat()
    out_path = Path(out_path or (repo_root / 'output' / 'analytics_report.md'))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    md = []
    title_scope = f"channel={channel}" if channel else 'all channels'
    md.append(f"# Analytics report — {title_scope}, last {lookback_days}d")
    md.append(f"_generated {date.today().isoformat()} from {db.name}_")

    with store.connect(db) as conn:
        videos = store.list_videos(conn, channel=channel)
        if not videos:
            md.append('\n_No videos in store. Run --pull-analytics._')
            out_path.write_text('\n\n'.join(md), encoding='utf-8')
            return out_path

        # ── per-video aggregates ───────────────────────────────────────
        rows = []
        for v in videos:
            agg = _aggregate_video(conn, v['video_id'], since)
            rows.append({**dict(v), **agg})

        rows_with_views = [r for r in rows if (r.get('views') or 0) > 0]

        def top_by(key: str, n: int = 10, fmt=_fmt_num,
                   reverse: bool = True):
            ranked = sorted(rows_with_views,
                            key=lambda r: (r.get(key) or 0),
                            reverse=reverse)[:n]
            out = ['', f'### Top {len(ranked)} by {key}', '',
                   '| Video | Channel | Title | Value |',
                   '|---|---|---|---:|']
            for r in ranked:
                out.append(
                    f"| `{r['video_id']}` "
                    f"| {r.get('channel') or '—'} "
                    f"| {(r.get('title') or '—')[:60]} "
                    f"| {fmt(r.get(key))} |")
            return '\n'.join(out)

        md.append('\n## Rollups (last {}d)'.format(lookback_days))
        md.append(top_by('views'))
        md.append(top_by('avp', fmt=_fmt_pct))
        md.append(top_by('subs_g'))

        # ── per-dataset rollup ─────────────────────────────────────────
        ds_totals: dict[str, dict] = {}
        for r in rows_with_views:
            key = r.get('dataset_indicator') or r.get('dataset_type') or '_unknown_'
            t = ds_totals.setdefault(key, {'videos': 0, 'views': 0,
                                            'avp_sum': 0.0, 'avp_n': 0})
            t['videos'] += 1
            t['views'] += r.get('views') or 0
            if r.get('avp') is not None:
                t['avp_sum'] += r['avp']
                t['avp_n'] += 1
        if ds_totals:
            md.append('\n### By dataset')
            md.append('| Dataset | Videos | Views | Avg view % |')
            md.append('|---|---:|---:|---:|')
            for key, t in sorted(ds_totals.items(),
                                 key=lambda kv: kv[1]['views'],
                                 reverse=True):
                avp = (t['avp_sum'] / t['avp_n']) if t['avp_n'] else None
                md.append(f"| {key} | {t['videos']} | "
                          f"{_fmt_num(t['views'])} | {_fmt_pct(avp)} |")

        # ── per-video bottleneck section ───────────────────────────────
        md.append('\n## Per-video retention drop-offs')
        md.append('_Latest retention snapshot per video, with steepest '
                  'drops labeled by narration section._\n')
        for r in rows:
            narration = {}
            mp = r.get('manifest_path')
            if mp and Path(mp).exists():
                try:
                    narration = manifest_mod.read(Path(mp)).get(
                        'narration') or {}
                except Exception:
                    narration = {}
            if not narration and r.get('script_text'):
                narration = {'script_text': r.get('script_text')}
            md.append(f"### `{r['video_id']}` — "
                      f"{(r.get('title') or '—')[:80]}")
            ds = r.get('dataset_indicator') or r.get('dataset_type') or '—'
            md.append(f"_{r.get('channel') or '?'} · dataset: {ds} · "
                      f"theme: {r.get('theme') or '—'} · "
                      f"render_cfg_hash: `{r.get('render_cfg_hash') or '—'}`_")
            md.append('')
            md.append(_retention_drops(conn, r['video_id'], narration))
            md.append('')

    out_path.write_text('\n'.join(md), encoding='utf-8')
    print(f"[report] wrote {out_path}")
    return out_path
