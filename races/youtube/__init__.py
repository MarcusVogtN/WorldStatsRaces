"""YouTube integration: OAuth, upload, analytics ingestion, reporting.

Implements requirements 27 (auto-post) and 28 (ingest performance metrics)
from CLAUDE.md. Both channels share this code; per-channel state (OAuth
refresh tokens, channel ID resolution) is keyed by the `--channel` flag.
"""
