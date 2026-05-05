"""Pull metadata + analytics from YouTube into cache/analytics.db.

Two API surfaces:
    Data API v3        — channel uploads list, video metadata
    YouTube Analytics  — per-day metrics, per-video retention curve

`pull(repo_root, channel)` is the on-demand entry point: it discovers all
videos on the authenticated channel, upserts them into `videos` (preserving
render-side context for ones we uploaded ourselves), refreshes per-day
metrics, and snapshots retention curves at +7d and +30d after publish.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import auth, store

# YouTube Analytics metrics we pull per day. Names per
# https://developers.google.com/youtube/analytics/metrics
# impressions / impressionClickThroughRate aren't available with
# filters=video==X + dimensions=day; pull them via a separate aggregated
# query (LIFETIME_METRICS) that uses dimensions=video.
DAILY_METRICS = (
    'views,estimatedMinutesWatched,averageViewDuration,'
    'averageViewPercentage,'
    'likes,dislikes,comments,shares,subscribersGained,subscribersLost'
)

DAILY_COLS = {
    'views':                          'views',
    'estimatedMinutesWatched':        'watch_time_minutes',
    'averageViewDuration':            'avg_view_duration_s',
    'averageViewPercentage':          'avg_view_percentage',
    'likes':                          'likes',
    'dislikes':                       'dislikes',
    'comments':                       'comments',
    'shares':                         'shares',
    'subscribersGained':              'subscribers_gained',
    'subscribersLost':                'subscribers_lost',
}

LIFETIME_METRICS = 'impressions,impressionClickThroughRate'


def _iso_duration_to_seconds(s: str | None) -> float | None:
    """Convert an ISO 8601 duration (PT#H#M#S) to seconds."""
    if not s:
        return None
    m = re.fullmatch(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?', s)
    if not m:
        return None
    h, mn, sec = m.groups()
    return (int(h or 0) * 3600 + int(mn or 0) * 60 + float(sec or 0))


def _list_uploads(yt_data, channel_id: str) -> list[dict]:
    """List every video on the channel via the uploads playlist."""
    ch = yt_data.channels().list(part='contentDetails',
                                 id=channel_id).execute()
    items = ch.get('items') or []
    if not items:
        return []
    uploads_id = items[0]['contentDetails']['relatedPlaylists']['uploads']
    out = []
    page = None
    while True:
        resp = yt_data.playlistItems().list(
            part='contentDetails,snippet',
            playlistId=uploads_id, maxResults=50, pageToken=page).execute()
        for it in resp.get('items', []):
            out.append({
                'video_id': it['contentDetails']['videoId'],
                'published_at': it['contentDetails'].get('videoPublishedAt'),
                'title': it['snippet'].get('title'),
                'description': it['snippet'].get('description'),
            })
        page = resp.get('nextPageToken')
        if not page:
            break
    return out


def _hydrate_videos(yt_data, video_ids: list[str]) -> dict[str, dict]:
    """Fetch contentDetails + status in batches of 50."""
    out: dict[str, dict] = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        resp = yt_data.videos().list(
            part='contentDetails,status,snippet',
            id=','.join(batch)).execute()
        for it in resp.get('items', []):
            out[it['id']] = {
                'duration_seconds': _iso_duration_to_seconds(
                    (it.get('contentDetails') or {}).get('duration')),
                'privacy_status': (it.get('status') or {}).get(
                    'privacyStatus'),
                'published_at': (it.get('snippet') or {}).get('publishedAt'),
                'title': (it.get('snippet') or {}).get('title'),
                'description': (it.get('snippet') or {}).get('description'),
            }
    return out


def _query_lifetime(yt_analytics, video_id: str,
                    start: date, end: date) -> dict:
    """Pull lifetime impressions / CTR for a single video using
    dimensions=video (the only shape that exposes these metrics)."""
    resp = yt_analytics.reports().query(
        ids='channel==MINE',
        startDate=start.isoformat(),
        endDate=end.isoformat(),
        metrics=LIFETIME_METRICS,
        dimensions='video',
        filters=f'video=={video_id}',
    ).execute()
    headers = [h['name'] for h in resp.get('columnHeaders', [])]
    rows = resp.get('rows') or []
    if not rows:
        return {}
    d = dict(zip(headers, rows[0]))
    return {
        'lifetime_impressions': d.get('impressions'),
        'lifetime_ctr':         d.get('impressionClickThroughRate'),
    }


def _query_daily(yt_analytics, video_id: str,
                 start: date, end: date) -> list[dict]:
    resp = yt_analytics.reports().query(
        ids='channel==MINE',
        startDate=start.isoformat(),
        endDate=end.isoformat(),
        metrics=DAILY_METRICS,
        dimensions='day',
        filters=f'video=={video_id}',
        sort='day',
    ).execute()
    headers = [h['name'] for h in resp.get('columnHeaders', [])]
    rows_out = []
    for row in resp.get('rows') or []:
        d = dict(zip(headers, row))
        rec = {'video_id': video_id, 'date': d.get('day')}
        for api_name, col_name in DAILY_COLS.items():
            rec[col_name] = d.get(api_name)
        rows_out.append(rec)
    return rows_out


def _query_retention(yt_analytics, video_id: str,
                     start: date, end: date) -> list[dict]:
    resp = yt_analytics.reports().query(
        ids='channel==MINE',
        startDate=start.isoformat(),
        endDate=end.isoformat(),
        metrics='audienceWatchRatio,relativeRetentionPerformance',
        dimensions='elapsedVideoTimeRatio',
        filters=f'video=={video_id}',
    ).execute()
    headers = [h['name'] for h in resp.get('columnHeaders', [])]
    snap = date.today().isoformat()
    rows_out = []
    for row in resp.get('rows') or []:
        d = dict(zip(headers, row))
        rows_out.append({
            'video_id': video_id,
            'snapshot_date': snap,
            'elapsed_ratio': d.get('elapsedVideoTimeRatio'),
            'relative_retention': d.get('audienceWatchRatio'),
        })
    return rows_out


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace('Z', '+00:00'))
    except ValueError:
        return None


def pull(repo_root: Path, channel: str, *,
         lookback_days: int = 30) -> None:
    """Discover channel uploads, refresh metrics_daily over the lookback
    window, and snapshot retention curves opportunistically."""
    yt_data = auth.build_data_client(repo_root, channel)
    yt_analytics = auth.build_analytics_client(repo_root, channel)
    channel_id = auth.resolve_channel_id(yt_data)
    print(f"[analytics] channel='{channel}' yt_channel_id={channel_id}")

    uploads = _list_uploads(yt_data, channel_id)
    print(f"[analytics] {len(uploads)} videos on channel")
    hydrated = _hydrate_videos(yt_data, [u['video_id'] for u in uploads])

    today = date.today()
    end = today
    start = today - timedelta(days=lookback_days)

    db = store.db_path_for(repo_root)
    with store.connect(db) as conn:
        # Upsert video rows (NULLs preserve render-side context for
        # videos we uploaded ourselves).
        now_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        for u in uploads:
            h = hydrated.get(u['video_id'], {})
            store.upsert_video(conn, {
                'video_id':         u['video_id'],
                'channel':          channel,
                'published_at':     h.get('published_at') or u.get('published_at'),
                'privacy_status':   h.get('privacy_status'),
                'title':            h.get('title') or u.get('title'),
                'description':      h.get('description') or u.get('description'),
                'duration_seconds': h.get('duration_seconds'),
                'last_pulled_at':   now_iso,
            })

        # metrics_daily for everything published recently
        n_daily = 0
        for u in uploads:
            pub = _parse_iso(hydrated.get(u['video_id'], {}).get(
                'published_at') or u.get('published_at'))
            if pub is None:
                continue
            if pub.date() > end:
                continue
            video_start = max(pub.date(), start)
            try:
                rows = _query_daily(yt_analytics, u['video_id'],
                                    video_start, end)
            except Exception as e:
                print(f"  [warn] daily for {u['video_id']}: {e}")
                continue
            n_daily += store.upsert_metrics_daily(conn, rows)
            # Note: YouTube Analytics `impressions` / `impressionClickThroughRate`
            # aren't available for Shorts (no thumbnail click-through model in
            # the vertical feed). Both channels publish Shorts only, so we skip
            # the lifetime impressions query entirely. If a longform channel
            # is added later, re-enable _query_lifetime for those videos.

        # retention curve: snapshot at +7d (close to ±2d) and +30d
        n_retention = 0
        for u in uploads:
            pub = _parse_iso(hydrated.get(u['video_id'], {}).get(
                'published_at') or u.get('published_at'))
            if pub is None:
                continue
            age = (today - pub.date()).days
            cur = conn.execute(
                "SELECT 1 FROM retention_curve WHERE video_id=? LIMIT 1",
                (u['video_id'],))
            already_snapshotted = cur.fetchone() is not None
            in_window = (5 <= age <= 9) or (28 <= age <= 33)
            backfill = (age > 14) and not already_snapshotted
            if not (in_window or backfill):
                continue
            if in_window:
                cur = conn.execute(
                    "SELECT 1 FROM retention_curve WHERE video_id=? "
                    "AND ABS(JULIANDAY(snapshot_date) - JULIANDAY(?)) <= 2 LIMIT 1",
                    (u['video_id'], today.isoformat()))
                if cur.fetchone():
                    continue
            try:
                rows = _query_retention(yt_analytics, u['video_id'],
                                        pub.date(), end)
            except Exception as e:
                print(f"  [warn] retention for {u['video_id']}: {e}")
                continue
            n_retention += store.upsert_retention(conn, rows)

    print(f"[analytics] upserted {n_daily} daily rows, "
          f"{n_retention} retention points -> {db}")
