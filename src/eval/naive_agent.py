"""A deliberately naive baseline agent for evaluation.

This agent exists to quantify the value of SAFE-AGENT-style gates.
It:
- uses the same tool catalog prompt to plan a tool call
- executes whatever tool/args the model outputs
- does NOT enforce an operator allowlist
- does NOT validate args against input schemas
- does NOT validate/parse tool outputs into typed models
- can optionally summarize without evidence grounding

Do not deploy this agent.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from src.host.llm_client import LLMClient
from src.host.planner import build_planner_messages
from src.host.multi_mcp_host import MultiMCPHost


def naive_ask_once(host: MultiMCPHost, user_query: str) -> Dict[str, Any]:
    """Run one naive "agent" step.

    Notes:
    - This function intentionally skips safety validations.
    - It is meant only as a baseline for experiments.
    """

    llm = LLMClient()

    servers_to_tools = host.tools_all()
    ok_tools = {srv: resp for srv, resp in servers_to_tools.items()
                if isinstance(resp, dict) and "result" in resp}

    messages = build_planner_messages(user_query, ok_tools)

    # Still expects JSON because we re-use the same planner prompt, but we do
    # not enforce strict schema or allowlist constraints.
    plan = llm.chat_json(messages=messages, max_tokens=256, temperature=0.0)

    if not isinstance(plan, dict):
        return {"type": "error", "reason": "planner did not return a dict", "raw": str(plan)[:400]}

    if plan.get("type") != "call_tool":
        return {
            "type": "final_answer",
            "answer": str(plan.get("answer", "")),
            "needs_more_info": bool(plan.get("needs_more_info", False)),
            "note": "baseline: no tool call",
        }

    server = plan.get("server")
    tool = plan.get("tool")
    args = plan.get("args")
    if not isinstance(args, dict):
        args = {}

    if not isinstance(server, str) or not isinstance(tool, str):
        return {"type": "error", "reason": "invalid plan shape", "plan": plan}

    # WARNING: intentionally no allowlist / schema checks
    raw = host.call(server, tool, args)

    out: Dict[str, Any] = {
        "type": "tool_result",
        "plan": plan,
        "raw": raw,
        "note": "baseline: executed without schema/allowlist/typing",
    }

    # Optional naive summarization (no grounding)
    if "summarize" in user_query.lower() or os.getenv("BASELINE_SUMMARIZE", "0") == "1":
        # Keep it extremely simple: return the first text content if present.
        result = raw.get("result", {}) if isinstance(raw, dict) else {}
        content = result.get("content", []) if isinstance(result, dict) else []
        if content and isinstance(content, list):
            first = content[0]
            if isinstance(first, dict) and first.get("type") == "text":
                out["summary"] = first.get("text", "")
        out["note"] += " + naive_summary"

    return out
