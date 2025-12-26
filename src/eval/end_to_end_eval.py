"""End-to-end evaluation harness.

This script runs the same evaluation cases through:
- the SAFE host (MultiMCPHost.ask_once) and
- a deliberately naive baseline (src.eval.naive_agent.naive_ask_once)

Requirements:
- MCP servers running (via docker compose)
- An OpenAI-compatible chat endpoint (vLLM, OpenAI, etc.) configured via env:
    LLM_BASE_URL, LLM_MODEL, (optional) LLM_API_KEY

Run:
  SAFE_TRACE_DIR=eval/traces \
  python -m src.eval.end_to_end_eval \
    --cases eval/cases_end_to_end.jsonl

Outputs:
  eval/results/<timestamp>_metrics.json
  eval/results/<timestamp>_runs.jsonl
  eval/results/<timestamp>_table.md

Notes:
- This is designed for paper-ready reproducibility. All runs can be traced via SAFE_TRACE_DIR.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.host.allowlist_config import load_allowlist_json
from src.host.multi_mcp_host import MultiMCPHost
from src.eval.naive_agent import naive_ask_once


def _now_tag() -> str:
    return time.strftime("%Y%m%d_%H%M%S", time.gmtime())


def _read_jsonl(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            rows.append(json.loads(line))
    return rows


def _classify(out: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a few consistent fields for metrics."""
    otype = out.get("type", "unknown")
    plan = out.get("plan") if isinstance(out.get("plan"), dict) else {}
    server = plan.get("server")
    tool = plan.get("tool")
    return {
        "type": otype,
        "blocked": otype == "blocked",
        "server": server,
        "tool": tool,
        "has_summary": "summary" in out,
        "trace_id": out.get("trace_id"),
        "trace_path": out.get("trace_path"),
    }


def _write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wt", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _write_jsonl(path: str, rows: Iterable[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wt", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="eval/cases_end_to_end.jsonl")
    ap.add_argument("--out_dir", default=os.path.join("eval", "results"))
    ap.add_argument("--mode", choices=["both", "safe", "baseline"], default="both")
    args = ap.parse_args()

    cases = _read_jsonl(args.cases)

    # Load configured allowlist so we can detect "disallowed tool executed" in baseline.
    cfg = load_allowlist_json()
    configured_allowlist = cfg.allowlist or {}

    servers = {
        "mcp-sharepoint": os.getenv("MCP_SP_URL", "http://localhost:5101/sse"),
        "mcp-servicenow": os.getenv("MCP_SN_URL", "http://localhost:5102/sse"),
        "mcp-policy-kb": os.getenv("MCP_KB_URL", "http://localhost:5103/sse"),
    }
    servers = {k: v for k, v in servers.items() if v}

    host = MultiMCPHost(servers)
    host.connect_all()

    runs: List[Dict[str, Any]] = []

    # Aggregate metrics
    m = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cases": len(cases),
        "allowlist_mode": cfg.mode,
        "allowlist_warning": cfg.warning,
        "safe": {"blocked": 0, "tool_calls": 0, "summaries": 0},
        "baseline": {"blocked": 0, "tool_calls": 0, "summaries": 0, "disallowed_tools_executed": 0},
    }

    try:
        for case in cases:
            cid = case.get("id")
            query = case.get("query")
            if not isinstance(query, str):
                continue

            row: Dict[str, Any] = {"id": cid, "query": query}

            if args.mode in ("both", "safe"):
                safe_out = host.ask_once(query)
                safe_c = _classify(safe_out)
                row["safe"] = safe_c
                row["safe_raw"] = safe_out  # keep full output for debugging

                if safe_c["blocked"]:
                    m["safe"]["blocked"] += 1
                else:
                    m["safe"]["tool_calls"] += 1
                if safe_c["has_summary"]:
                    m["safe"]["summaries"] += 1

            if args.mode in ("both", "baseline"):
                base_out = naive_ask_once(host, query)
                base_c = _classify(base_out)
                row["baseline"] = base_c
                row["baseline_raw"] = base_out

                if base_c["blocked"]:
                    m["baseline"]["blocked"] += 1
                else:
                    m["baseline"]["tool_calls"] += 1
                if base_c["has_summary"]:
                    m["baseline"]["summaries"] += 1

                # Detect disallowed tool execution
                srv = base_c.get("server")
                tool = base_c.get("tool")
                if isinstance(srv, str) and isinstance(tool, str):
                    allowed_tools = set(configured_allowlist.get(srv, []))
                    if tool and tool not in allowed_tools:
                        m["baseline"]["disallowed_tools_executed"] += 1

            runs.append(row)

    finally:
        host.close()

    tag = _now_tag()
    metrics_path = os.path.join(args.out_dir, f"{tag}_metrics.json")
    runs_path = os.path.join(args.out_dir, f"{tag}_runs.jsonl")
    table_path = os.path.join(args.out_dir, f"{tag}_table.md")

    _write_json(metrics_path, m)
    _write_jsonl(runs_path, runs)

    # Simple markdown table
    lines = []
    lines.append("| id | safe.type | safe.tool | baseline.type | baseline.tool | baseline.disallowed |")
    lines.append("|---|---|---|---|---|---|")
    for r in runs:
        sid = r.get("id", "")
        safe = r.get("safe", {})
        base = r.get("baseline", {})
        disallowed = ""
        if base and isinstance(base, dict):
            srv = base.get("server")
            tool = base.get("tool")
            if isinstance(srv, str) and isinstance(tool, str):
                allowed_tools = set(configured_allowlist.get(srv, []))
                disallowed = "YES" if tool and tool not in allowed_tools else ""
        lines.append(
            f"| {sid} | {safe.get('type','')} | {safe.get('tool','')} | {base.get('type','')} | {base.get('tool','')} | {disallowed} |"
        )

    os.makedirs(args.out_dir, exist_ok=True)
    with open(table_path, "wt", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("Wrote:")
    print("  ", metrics_path)
    print("  ", runs_path)
    print("  ", table_path)


if __name__ == "__main__":
    main()
