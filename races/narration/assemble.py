"""Assemble picked variants (hook + middle + ending) into cache/narration.json.

The TTS pipeline consumes `script_text` as one flowing paragraph, so we
concatenate the three picks with single spaces.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def assemble_text(hook: str, middle: str, ending: str) -> str:
    parts = [hook.strip(), middle.strip(), ending.strip()]
    return " ".join(p for p in parts if p)


def write_narration_json(*, hook: str, middle: str, ending: str,
                         narration_path: Path,
                         tone: str | None = None,
                         words_per_second: float = 2.7,
                         video_duration_seconds: float | None = None,
                         model: str | None = None,
                         source: str = "auto") -> dict[str, Any]:
    """Write an assembled script to cache/narration.json in the schema the
    existing TTS step expects. Preserves any previous `meta.usage` under
    `meta.previous_usage` for reference but overwrites the rest.
    """
    script_text = assemble_text(hook, middle, ending)
    word_count = len(script_text.split())
    est_seconds = word_count / words_per_second if words_per_second else 0.0

    prev: dict[str, Any] = {}
    if narration_path.exists():
        try:
            prev = json.loads(narration_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev = {}

    doc: dict[str, Any] = {
        "script_text": script_text,
        "meta": {
            "generated_at": datetime.now(timezone.utc)
                                    .strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": source,
            "words_per_second": words_per_second,
            "actual_word_count": word_count,
            "estimated_seconds": round(est_seconds, 2),
            "sections": {
                "hook": hook.strip(),
                "middle": middle.strip(),
                "ending": ending.strip(),
            },
        },
    }
    if tone is not None:
        doc["meta"]["tone"] = tone
    if video_duration_seconds is not None:
        doc["meta"]["video_duration_seconds"] = video_duration_seconds
    if model is not None:
        doc["meta"]["model"] = model
    prev_meta = prev.get("meta") or {}
    if "usage" in prev_meta:
        doc["meta"]["previous_usage"] = prev_meta["usage"]

    narration_path.parent.mkdir(parents=True, exist_ok=True)
    with open(narration_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    return doc
