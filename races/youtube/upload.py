"""Upload a rendered mp4 to YouTube as a private draft.

v1 scope (locked in design):
    - privacyStatus = 'private' (you publish manually in Studio)
    - madeForKids = False
    - title/description generated from manifest
    - no thumbnail (YouTube auto-picks)
    - #shorts in description (renders are vertical short-form)

After upload completes, writes the videos row to cache/analytics.db so
analytics pulls can find it from day one.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import auth, manifest, store

CATEGORY_BY_CHANNEL = {
    'world': '27',   # Education
    'sports': '17',  # Sports
}


def _youtube_overrides(m: dict) -> dict:
    """Optional `youtube` block from the config snapshot, letting a video set
    its own YouTube title/tags (which can differ from the on-screen title and
    the country-default tags). Absent → {}."""
    return (m.get('config_snapshot') or {}).get('youtube') or {}


def _build_title(m: dict) -> str:
    """Generate a draft title. A config `youtube.title` override wins;
    otherwise fall back to the on-screen video title. You can still edit in
    Studio before promoting from private to public."""
    override = _youtube_overrides(m).get('title')
    if override:
        return override[:100]
    return (m.get('video_title') or m.get('output_stem') or 'Race')[:100]


def _build_description(m: dict) -> str:
    parts = []
    nar = m.get('narration') or {}
    script = nar.get('script_text')
    if script:
        parts.append(script.strip())
    if m.get('source_credit'):
        # source_credit already carries its own "Source: " prefix.
        parts.append(m['source_credit'])
    parts.append('#shorts')
    return ('\n\n'.join(parts))[:5000]


_DEFAULT_TAGS_BY_CHANNEL = {
    'world': [
        'shorts', 'world stats', 'data visualization', 'country comparison',
        'world rankings', 'bar chart race', 'country race', 'data race',
        'world bank', 'history', 'geography',
    ],
    'sports': [
        'shorts', 'soccer', 'football', 'sports stats', 'player comparison',
        'goat debate', 'data visualization', 'bar chart race',
    ],
}


def _build_tags(m: dict, channel: str) -> list[str]:
    """Generate a sensible default tag list. YouTube caps total tag string
    length at ~500 chars; we stay well under by capping at 12 tags.

    A config `youtube.tags` override replaces the channel defaults entirely —
    needed for non-country datasets (e.g. baby names) where the country tags
    don't fit."""
    override = _youtube_overrides(m).get('tags')
    if override:
        return list(override)[:12]
    base = list(_DEFAULT_TAGS_BY_CHANNEL.get(channel, ['shorts']))
    # Mine the title for natural-language tags too.
    title = (m.get('video_title') or '').lower()
    for word in ('tourism', 'tourists', 'gdp', 'population', 'military',
                 'co2', 'patents', 'reserves', 'energy', 'health',
                 'internet', 'trade', 'inflation', 'covid'):
        if word in title and word not in base:
            base.append(word)
    seen = set()
    out: list[str] = []
    for t in base:
        if t not in seen:
            seen.add(t)
            out.append(t)
        if len(out) >= 12:
            break
    return out


def _resumable_upload(yt_data, body: dict, mp4_path: Path):
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    media = MediaFileUpload(str(mp4_path), chunksize=-1, resumable=True,
                            mimetype='video/mp4')
    req = yt_data.videos().insert(
        part=','.join(body.keys()), body=body, media_body=media)
    response = None
    while response is None:
        try:
            status, response = req.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                print(f"  uploading... {pct}%")
        except HttpError as e:
            raise SystemExit(f"[upload] HTTP error: {e}")
    return response


def upload(repo_root: Path,
           channel: str,
           mp4_path: Path,
           manifest_path: Path | None = None,
           *,
           privacy: str = 'private') -> str:
    """Upload `mp4_path` to YouTube. Returns the new video_id.

    `manifest_path` defaults to the sidecar resolved from `mp4_path`.
    """
    mp4_path = Path(mp4_path).resolve()
    if not mp4_path.exists():
        raise SystemExit(f"Video not found: {mp4_path}")

    if manifest_path is None:
        found = manifest.find_for_video(mp4_path.parent, mp4_path.name)
        if found is None:
            raise SystemExit(
                f"No manifest sidecar for {mp4_path.name}. Re-render the "
                "video so the manifest is written, or pass an explicit "
                "--manifest path.")
        manifest_path = found
    m = manifest.read(manifest_path)

    title = _build_title(m)
    description = _build_description(m)
    tags = _build_tags(m, channel)
    body = {
        'snippet': {
            'title': title,
            'description': description,
            'categoryId': CATEGORY_BY_CHANNEL.get(channel, '27'),
            'tags': tags,
            'defaultLanguage': 'en',
            'defaultAudioLanguage': 'en',
        },
        'status': {
            'privacyStatus': privacy,
            'madeForKids': False,
            'selfDeclaredMadeForKids': False,
            'embeddable': True,
            'license': 'youtube',
        },
    }
    print(f"[upload] channel={channel} file={mp4_path.name} "
          f"title={title!r} privacy={privacy} tags={tags}")

    yt_data = auth.build_data_client(repo_root, channel)
    resp = _resumable_upload(yt_data, body, mp4_path)
    video_id = resp['id']
    print(f"[upload] done -- video_id={video_id}")
    print(f"  https://studio.youtube.com/video/{video_id}/edit")

    ds = m.get('dataset') or {}
    nar = m.get('narration') or {}
    transforms = m.get('transforms') or {}
    row = {
        'video_id': video_id,
        'channel': channel,
        'uploaded_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'published_at': None,
        'privacy_status': privacy,
        'title': title,
        'description': description,
        'manifest_path': str(manifest_path),
        'output_filename': mp4_path.name,
        'render_cfg_hash': m.get('render_cfg_hash'),
        'theme': m.get('theme'),
        'dataset_type': ds.get('source_type') or ds.get('type'),
        'dataset_indicator': ds.get('indicator'),
        'dataset_timeframe': json.dumps(ds.get('timeframe'))
                             if ds.get('timeframe') else None,
        'transforms': json.dumps(transforms) if transforms else None,
        'narration_source': nar.get('source'),
        'narration_model': nar.get('model'),
        'narration_tone': nar.get('tone'),
        'script_text': nar.get('script_text'),
        'registered_at': datetime.now(timezone.utc).strftime(
            '%Y-%m-%dT%H:%M:%SZ'),
    }
    with store.connect(store.db_path_for(repo_root)) as conn:
        store.upsert_video(conn, row)
    print(f"[upload] wrote videos row to {store.db_path_for(repo_root).name}")
    return video_id
