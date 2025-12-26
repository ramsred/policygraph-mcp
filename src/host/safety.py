from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Tuple
import json
import re


# ---------- Gate 0: Input policy gate ----------

_UNSAFE_PATTERNS = [
    # keep this strict initially; we can tune later
    r"\b(hack|exploit|malware|ransomware|phishing)\b",
    r"\b(build a bomb|explosive|detonator)\b",
    r"\b(suicide|self-harm|kill myself)\b",
    r"\b(credit card dump|steal password|credential)\b",
]

def policy_check_user_query(q: str) -> Tuple[bool, str]:
    """Return (allowed, reason_if_blocked)."""
    text = q.lower()
    for pat in _UNSAFE_PATTERNS:
        if re.search(pat, text):
            return False, f"Blocked by policy (matched pattern: {pat})"
    return True, ""


# ---------- Gate 1: Strict JSON plan parsing ----------

@dataclass
class Plan:
    type: str  # "tool_call" | "final_answer" | "needs_more_info"
    server: str | None = None
    tool: str | None = None
    args: Dict[str, Any] | None = None
    question: str | None = None
    answer: str | None = None


class PlanParseError(Exception):
    pass


def parse_strict_json_plan(raw: Any) -> Dict[str, Any]:
    """
    Accept either:
      - dict (already parsed), or
      - string containing JSON only.
    Reject anything else.
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        # Reject if it looks like extra text around JSON
        if not (s.startswith("{") and s.endswith("}")):
            raise PlanParseError("LLM output must be ONLY a JSON object.")
        try:
            return json.loads(s)
        except Exception as e:
            raise PlanParseError(f"Invalid JSON: {e}")
    raise PlanParseError("LLM output must be JSON object or JSON string.")


# ---------- Gate 2: Tool allowlist enforcement ----------

class ToolNotAllowed(Exception):
    pass


def enforce_tool_allowlist(server: str, tool: str, allowlist: Dict[str, set[str]]) -> None:
    """
    allowlist example:
      {"mcp-sharepoint": {"search_sharepoint", "fetch_sharepoint_doc"}, ...}
    """
    if server not in allowlist:
        raise ToolNotAllowed(f"Server not allowed: {server}")
    if tool not in allowlist[server]:
        raise ToolNotAllowed(f"Tool not allowed: {server}.{tool}")