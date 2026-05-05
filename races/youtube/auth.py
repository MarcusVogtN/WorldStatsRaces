"""OAuth 2.0 for YouTube Data + Analytics APIs.

One Google Cloud OAuth client (`cache/youtube/client_secret.json`), one
refresh-token file per channel (`credentials_<channel>.json`). Use the
`installed` (desktop-app) flow — local server callback on a free port.
"""
from __future__ import annotations

import json
from pathlib import Path

SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/yt-analytics.readonly',
]


def _yt_dir(repo_root: Path) -> Path:
    p = Path(repo_root) / 'cache' / 'youtube'
    p.mkdir(parents=True, exist_ok=True)
    return p


def client_secret_path(repo_root: Path) -> Path:
    return _yt_dir(repo_root) / 'client_secret.json'


def credentials_path(repo_root: Path, channel: str) -> Path:
    return _yt_dir(repo_root) / f'credentials_{channel}.json'


def _require_libs():
    try:
        from google.oauth2.credentials import Credentials  # noqa: F401
        from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: F401
        from google.auth.transport.requests import Request  # noqa: F401
        from googleapiclient.discovery import build  # noqa: F401
    except ImportError as e:
        raise SystemExit(
            "YouTube integration requires google-api-python-client and "
            "google-auth-oauthlib. Install with:\n"
            "    pip install google-api-python-client google-auth-oauthlib\n"
            f"(import error: {e})")


def authorize(repo_root: Path, channel: str) -> None:
    """Run the OAuth installed-app flow for a channel and save the refresh
    token. Opens a browser; you must sign in with the Google account that
    owns the YouTube channel and grant the requested scopes."""
    _require_libs()
    from google_auth_oauthlib.flow import InstalledAppFlow

    cs = client_secret_path(repo_root)
    if not cs.exists():
        raise SystemExit(
            f"Missing OAuth client at {cs}.\n\n"
            "Create one in Google Cloud Console:\n"
            "  1. APIs & Services → Library → enable 'YouTube Data API v3' "
            "and 'YouTube Analytics API'.\n"
            "  2. APIs & Services → Credentials → Create Credentials → "
            "OAuth client ID → application type 'Desktop app'.\n"
            f"  3. Download the JSON and save it as {cs}\n")
    flow = InstalledAppFlow.from_client_secrets_file(str(cs), SCOPES)
    creds = flow.run_local_server(port=0,
                                  prompt='consent',
                                  authorization_prompt_message=(
                                      f"\nSign in with the Google account "
                                      f"that owns the '{channel}' YouTube "
                                      f"channel.\n"))
    out = credentials_path(repo_root, channel)
    out.write_text(creds.to_json(), encoding='utf-8')
    print(f"[auth] saved credentials for channel='{channel}' to {out}")


def load_credentials(repo_root: Path, channel: str):
    """Load saved credentials, refreshing if expired. Raises SystemExit if
    no credentials exist for this channel."""
    _require_libs()
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    p = credentials_path(repo_root, channel)
    if not p.exists():
        raise SystemExit(
            f"No YouTube credentials for channel='{channel}'. Run:\n"
            f"    python run.py --channel {channel} --auth-youtube\n")
    creds = Credentials.from_authorized_user_info(
        json.loads(p.read_text(encoding='utf-8')), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        p.write_text(creds.to_json(), encoding='utf-8')
    return creds


def build_data_client(repo_root: Path, channel: str):
    _require_libs()
    from googleapiclient.discovery import build
    return build('youtube', 'v3',
                 credentials=load_credentials(repo_root, channel),
                 cache_discovery=False)


def build_analytics_client(repo_root: Path, channel: str):
    _require_libs()
    from googleapiclient.discovery import build
    return build('youtubeAnalytics', 'v2',
                 credentials=load_credentials(repo_root, channel),
                 cache_discovery=False)


def resolve_channel_id(yt_data) -> str:
    """Return the YouTube channel ID for the authenticated user."""
    resp = yt_data.channels().list(part='id', mine=True).execute()
    items = resp.get('items') or []
    if not items:
        raise SystemExit("Authenticated account owns no YouTube channel.")
    return items[0]['id']
