"""Allowlist configuration and enforcement utilities.

Why this exists
---------------
MCP discovery (tools/list) tells us what tools *exist* on each server.
That is not the same as an operator-approved allowlist.

This module makes the allowlist an explicit, operator-controlled decision.

SAFE default
------------
A tool is callable only if it is BOTH:
  (a) discovered live via tools/list, and
  (b) present in the configured allowlist file.

If the allowlist file is missing (or disabled), the host can fall back to
"discovered tools" mode for developer convenience, but that is NOT the
recommended production configuration.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Set


DEFAULT_ALLOWLIST_PATH = os.getenv("SAFE_ALLOWLIST_PATH", "config/allowlist.json")


@dataclass(frozen=True)
class AllowlistLoadResult:
    """Result of loading an allowlist."""

    allowlist: Optional[Dict[str, Set[str]]]
    mode: str  # "configured" | "discovered"
    warning: str = ""


def load_allowlist_json(path: str = DEFAULT_ALLOWLIST_PATH) -> AllowlistLoadResult:
    """Load an operator-configured allowlist from JSON.

    Expected shape:
        {
          "mcp-sharepoint": ["tool_a", "tool_b"],
          "mcp-policy-kb": ["tool_c"]
        }

    Returns:
        AllowlistLoadResult
            - allowlist: dict[str, set[str]] if loaded, else None
            - mode: "configured" when file loaded, else "discovered"
            - warning: non-empty when file missing/invalid
    """
    try:
        with open(path, "rt", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("allowlist JSON must be an object")

        allow: Dict[str, Set[str]] = {}
        for server, tools in data.items():
            if not isinstance(server, str) or not server.strip():
                continue
            if not isinstance(tools, list):
                continue
            allow[server] = {t for t in tools if isinstance(t, str) and t.strip()}

        return AllowlistLoadResult(allowlist=allow, mode="configured")

    except FileNotFoundError:
        return AllowlistLoadResult(
            allowlist=None,
            mode="discovered",
            warning=f"Allowlist file not found at '{path}'. Falling back to discovered tools.",
        )
    except Exception as e:
        return AllowlistLoadResult(
            allowlist=None,
            mode="discovered",
            warning=f"Allowlist file '{path}' invalid ({e}). Falling back to discovered tools.",
        )


def apply_configured_allowlist(
    discovered: Dict[str, Set[str]],
    configured: Optional[Dict[str, Set[str]]],
) -> Dict[str, Set[str]]:
    """Compute the effective allowlist.

    If configured is None -> return discovered.
    Else -> return discovered ∩ configured (per-server).

    This ensures that a tool cannot become callable merely by being exposed by
    an MCP server.
    """

    if configured is None:
        return discovered

    effective: Dict[str, Set[str]] = {}
    for server, discovered_tools in discovered.items():
        effective[server] = set(discovered_tools) & set(configured.get(server, set()))
    return effective


def as_pretty_allowlist(allowlist: Dict[str, Set[str]]) -> Dict[str, list[str]]:
    """Convert allowlist sets into JSON-serializable lists."""
    return {srv: sorted(list(tools)) for srv, tools in allowlist.items()}
