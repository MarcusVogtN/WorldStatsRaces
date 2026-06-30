"""Sports-shaped stat pack for the narration LLM.

Same calculations as `races/narration/stats.py::build_stat_pack`, but the
output dict uses `player` / `players_in_data` instead of `country` /
`countries_in_data`, groups seasons into 5-season eras instead of decades,
and drops world-stats-only fields (`most_volatile_top10`, `early_boring`)
that aren't meaningful for cumulative goal totals.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from races.util import display_name, format_value


ERA_LENGTH = 5  # seasons per era block


def _yearly_from_scores(scores_df: pd.DataFrame, steps_per_year: int) -> pd.DataFrame:
    """Downsample scores_df (sub-frame) to one row per integer season."""
    idx = scores_df.index.to_numpy()
    years = np.round(idx).astype(int)
    first_mask = np.concatenate([[True], np.diff(years) != 0])
    yearly = scores_df.iloc[first_mask].copy()
    yearly.index = years[first_mask]
    return yearly


def _display_ranks(yearly: pd.DataFrame, invert: bool = False) -> pd.DataFrame:
    """Display rank (1 = top of leaderboard)."""
    return yearly.rank(axis=1, method='min', ascending=invert)


def build_stat_pack(scores_df: pd.DataFrame,
                    ranks_df: pd.DataFrame,
                    *,
                    steps_per_year: int,
                    value_format: str,
                    video_title: str,
                    n_on_screen: int = 10,
                    invert_ranking: bool = False) -> dict[str, Any]:
    yearly = _yearly_from_scores(scores_df, steps_per_year)
    ranks = _display_ranks(yearly, invert=invert_ranking)
    years = yearly.index.to_numpy()
    players = list(yearly.columns)

    total_per_year = yearly.fillna(0).sum(axis=1)

    # ── Top-1 share per era (5-season blocks) ───────────────────────────
    top_share_per_era: list[dict[str, Any]] = []
    if len(years):
        start_block = int(years.min()) // ERA_LENGTH * ERA_LENGTH
        for era_start in range(start_block, int(years.max()) + 1, ERA_LENGTH):
            era_end = era_start + ERA_LENGTH - 1
            mask = (years >= era_start) & (years <= era_end)
            if not mask.any():
                continue
            sub = yearly.iloc[mask]
            sub_total = sub.fillna(0).sum(axis=1)
            top1_values = sub.min(axis=1) if invert_ranking else sub.max(axis=1)
            top1_names = sub.idxmin(axis=1) if invert_ranking else sub.idxmax(axis=1)
            share = float((top1_values / sub_total.replace(0, np.nan)).mean())
            dominant = top1_names.mode().iloc[0] if not top1_names.empty else None
            top_share_per_era.append({
                'era_start': int(era_start),
                'era_end': int(era_end),
                'dominant_player': display_name(dominant) if dominant else None,
                'avg_top1_share': round(share, 3),
                'avg_top1_share_pct_str': f"{share * 100:.0f}%",
            })

    # ── Total growth start → end ────────────────────────────────────────
    total_start = float(total_per_year.iloc[0]) if len(total_per_year) else 0.0
    total_end = float(total_per_year.iloc[-1]) if len(total_per_year) else 0.0
    total_growth = {
        'season_start': int(years[0]) if len(years) else None,
        'season_end': int(years[-1]) if len(years) else None,
        'value_start': total_start,
        'value_end': total_end,
        'value_start_str': format_value(total_start, value_format),
        'value_end_str': format_value(total_end, value_format),
        'multiplier': round(total_end / total_start, 2) if total_start > 0 else None,
    }

    # ── Longest reign at rank 1 ─────────────────────────────────────────
    top1_names = yearly.idxmin(axis=1) if invert_ranking else yearly.idxmax(axis=1)
    longest_reign: dict[str, Any] = {'player': None, 'seasons': 0, 'start': None, 'end': None}
    if len(top1_names):
        cur_player = top1_names.iloc[0]
        cur_start = int(years[0])
        run = 1
        for i in range(1, len(top1_names)):
            if top1_names.iloc[i] == cur_player:
                run += 1
            else:
                if run > longest_reign['seasons']:
                    longest_reign = {
                        'player': display_name(cur_player),
                        'seasons': run,
                        'start': cur_start,
                        'end': int(years[i - 1]),
                    }
                cur_player = top1_names.iloc[i]
                cur_start = int(years[i])
                run = 1
        if run > longest_reign['seasons']:
            longest_reign = {
                'player': display_name(cur_player),
                'seasons': run,
                'start': cur_start,
                'end': int(years[-1]),
            }

    # ── Rank-1 crossovers (records broken) ──────────────────────────────
    crossovers: list[dict[str, Any]] = []
    for i in range(1, len(top1_names)):
        a, b = top1_names.iloc[i - 1], top1_names.iloc[i]
        if a != b and pd.notna(a) and pd.notna(b):
            crossovers.append({
                'season': int(years[i]),
                'from': display_name(a),
                'to': display_name(b),
            })

    # ── Top-N entries and exits ─────────────────────────────────────────
    in_top = (ranks <= n_on_screen).fillna(False)
    entries_exits: list[dict[str, Any]] = []
    for player in players:
        col = in_top[player].to_numpy()
        for i in range(1, len(col)):
            if col[i] and not col[i - 1]:
                entries_exits.append({
                    'player': display_name(player),
                    'season': int(years[i]),
                    'kind': 'entered_top_n',
                    'value_str': format_value(float(yearly[player].iloc[i]), value_format),
                })
            elif not col[i] and col[i - 1]:
                entries_exits.append({
                    'player': display_name(player),
                    'season': int(years[i]),
                    'kind': 'exited_top_n',
                    'value_str': format_value(float(yearly[player].iloc[i - 1]), value_format),
                })

    # ── Best single-season hauls (top 20 by |Δ|) ────────────────────────
    diffs = yearly.diff()
    stacked = diffs.stack().dropna()
    stacked = stacked.reindex(stacked.abs().sort_values(ascending=False).index)
    best_single_season_hauls: list[dict[str, Any]] = []
    for (season_val, player), delta in stacked.head(20).items():
        v_now = float(yearly.loc[season_val, player])
        v_prev = (float(yearly.loc[season_val - 1, player])
                  if (season_val - 1) in yearly.index else None)
        best_single_season_hauls.append({
            'player': display_name(player),
            'season': int(season_val),
            'delta': float(delta),
            'delta_str': format_value(abs(float(delta)), value_format),
            'direction': 'up' if delta > 0 else 'down',
            'career_total_after_str': format_value(v_now, value_format),
            'career_total_before_str': (format_value(v_prev, value_format)
                                        if v_prev is not None else None),
        })

    # ── Final-season standings (top-N) ──────────────────────────────────
    final_season = int(round(float(scores_df.index[-1])))
    final_row = scores_df.iloc[-1].dropna().sort_values(ascending=invert_ranking)
    final_standings: list[dict[str, Any]] = []
    for rank_idx, (player, value) in enumerate(final_row.head(n_on_screen).items(), start=1):
        final_standings.append({
            'rank': rank_idx,
            'player': display_name(player),
            'season': final_season,
            'value': float(value),
            'value_str': format_value(float(value), value_format),
        })

    # ── First-season standings (top-N) ──────────────────────────────────
    first_season = int(round(float(scores_df.index[0])))
    first_row = scores_df.iloc[0].dropna().sort_values(ascending=invert_ranking)
    first_standings: list[dict[str, Any]] = []
    for rank_idx, (player, value) in enumerate(first_row.head(n_on_screen).items(), start=1):
        first_standings.append({
            'rank': rank_idx,
            'player': display_name(player),
            'season': first_season,
            'value': float(value),
            'value_str': format_value(float(value), value_format),
        })

    # ── Players that ever appear in the data ────────────────────────────
    # Hard whitelist for the LLM: it MAY NOT name any player not in this list.
    ever_present = sorted({display_name(p) for p in players
                           if yearly[p].notna().any()})

    return {
        'video_title': video_title,
        'seasons': [int(years[0]), int(years[-1])] if len(years) else None,
        'value_format': value_format,
        'players_in_data': ever_present,
        'first_standings': first_standings,
        'final_standings': final_standings,
        'top_share_per_era': top_share_per_era,
        'total_growth': total_growth,
        'longest_reign_at_1': longest_reign,
        'crossovers_at_1': crossovers,
        'entries_exits': entries_exits,
        'best_single_season_hauls': best_single_season_hauls,
    }
