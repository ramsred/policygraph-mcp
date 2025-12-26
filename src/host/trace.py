"""Trace artifacts for auditability.

This repo is CLI-first, so we keep tracing simple:
- Collect structured events during a run
- Optionally write them as a single JSON file to SAFE_TRACE_DIR

The goal is to make experiments reproducible and audit-friendly.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def now_ms() -> int:
    return int(time.time() * 1000)


def _truncate(obj: Any, max_chars: int = 20_000) -> Any:
    """Best-effort truncation for large nested payloads."""
    try:
        s = json.dumps(obj, ensure_ascii=False)
    except Exception:
        s = str(obj)

    if len(s) <= max_chars:
        return obj

    # If it's serializable, return a truncated string representation.
    return s[:max_chars] + "\n...[TRUNCATED]..."


@dataclass
class TraceEvent:
    ts_ms: int
    name: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceRecorder:
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    meta: Dict[str, Any] = field(default_factory=dict)
    events: List[TraceEvent] = field(default_factory=list)

    def event(self, name: str, payload: Optional[Dict[str, Any]] = None) -> None:
        self.events.append(
            TraceEvent(ts_ms=now_ms(), name=name, payload=_truncate(payload or {}))
        )

    def to_dict(self, final_output: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "meta": self.meta,
            "events": [
                {"ts_ms": e.ts_ms, "name": e.name, "payload": e.payload} for e in self.events
            ],
            "final_output": _truncate(final_output or {}),
        }

    def write(self, directory: str, final_output: Optional[Dict[str, Any]] = None) -> str:
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"trace_{self.trace_id}.json")
        with open(path, "wt", encoding="utf-8") as f:
            json.dump(self.to_dict(final_output=final_output), f, ensure_ascii=False, indent=2)
        return path


def get_trace_dir() -> Optional[str]:
    """Returns SAFE_TRACE_DIR if set and non-empty."""
    d = os.getenv("SAFE_TRACE_DIR", "").strip()
    return d or None
