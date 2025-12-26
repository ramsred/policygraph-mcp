"""
Multi MCP Host (SSE)

Connects to multiple FastMCP servers via SSE transport,
performs MCP initialization handshake, lists tools, calls tools,
and can do a single-step "ask" flow using a local LLM planner.

Usage:
  python -m src.host.multi_mcp_host

Commands:
  tools
  call <server> <tool> '<json_args>'
  ask "<natural language question>"
  quit
"""

from __future__ import annotations

import json
import os
import shlex
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests

from .llm_client import LLMClient
from .planner import build_planner_messages, build_tool_catalog
from .validator import validate_plan, ValidationError

from .allowlist_config import (
    apply_configured_allowlist,
    as_pretty_allowlist,
    load_allowlist_json,
)

from .safety import (
    policy_check_user_query,
    parse_strict_json_plan,
    enforce_tool_allowlist,
    PlanParseError,
    ToolNotAllowed,
)

from .summarizer import (
    _to_source_text,
    build_summarizer_messages,
    validate_grounded_summary,
    GroundingError,
)
# LangGraph runner (Option A)
try:
    from src.graph.langgraph_agent import run_once as run_langgraph_once
except Exception:
    run_langgraph_once = None
    
from .typed_parser import parse_typed_tool_output, ToolOutputParseError

from .trace import TraceRecorder, get_trace_dir

# -----------------------------
# Utilities
# -----------------------------


class MCPProtocolError(RuntimeError):
    pass


def _now_ms() -> int:
    return int(time.time() * 1000)


def _origin(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _join_url(base_or_origin: str, path: str) -> str:
    base = base_or_origin.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return base + path


# -----------------------------
# SSE reader
# -----------------------------


@dataclass
class MCPEvent:
    event: str
    data: str


class SSEReader(threading.Thread):
    """
    Minimal SSE client that parses event/data lines and calls on_event(ev).
    """

    def __init__(self, url: str, on_event, name: str):
        super().__init__(daemon=True, name=name)
        self.url = url
        self.on_event = on_event
        self._stop = threading.Event()
        self._session = requests.Session()

    def stop(self):
        self._stop.set()
        try:
            self._session.close()
        except Exception:
            pass

    def run(self):
        headers = {
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        }
        try:
            # decode_unicode=True ensures we get strings, not bytes
            with self._session.get(self.url, headers=headers, stream=True, timeout=(5, None)) as resp:
                resp.raise_for_status()

                event_type = "message"
                data_lines: list[str] = []

                for raw in resp.iter_lines(decode_unicode=True):
                    if self._stop.is_set():
                        return
                    if raw is None:
                        continue

                    line = raw.strip("\r")

                    # Blank line => dispatch accumulated event
                    if line == "":
                        if data_lines:
                            data = "\n".join(data_lines)
                            try:
                                self.on_event(MCPEvent(event=event_type, data=data))
                            except Exception:
                                pass
                        event_type = "message"
                        data_lines = []
                        continue

                    # SSE comment / ping
                    if line.startswith(":"):
                        continue

                    if line.startswith("event:"):
                        event_type = line.split(":", 1)[1].strip()
                        continue

                    if line.startswith("data:"):
                        data_lines.append(line.split(":", 1)[1].lstrip())
                        continue

        except Exception as e:
            try:
                self.on_event(MCPEvent(event="__error__", data=str(e)))
            except Exception:
                pass


# -----------------------------
# MCP SSE Session
# -----------------------------


class MCPSSESession:
    """
    A single MCP client session connected to exactly ONE MCP server via SSE.
    """

    def __init__(self, name: str, sse_url: str):
        self.name = name
        self.sse_url = sse_url.rstrip("/")  # e.g. http://localhost:5101/sse
        self.messages_url: Optional[str] = None

        self._reader: Optional[SSEReader] = None
        self._lock = threading.Lock()
        self._inbox: Dict[int, Dict[str, Any]] = {}
        self._errors: list[str] = []
        self._http = requests.Session()

    def connect(self):
        """
        1) Start SSE reader
        2) Wait for "endpoint" event -> messages_url
        3) Perform MCP initialization handshake
        """

        def on_event(ev: MCPEvent):
            if ev.event == "__error__":
                with self._lock:
                    self._errors.append(ev.data)
                return

            if ev.event == "endpoint":
                rel = ev.data.strip()  # like /messages/?session_id=...
                self.messages_url = _join_url(_origin(self.sse_url), rel)
                return

            if ev.event == "message":
                try:
                    msg = json.loads(ev.data)
                except Exception:
                    return

                # Only responses with an id are tracked for request/response
                if isinstance(msg, dict) and "id" in msg:
                    try:
                        rid = int(msg["id"])
                    except Exception:
                        return
                    with self._lock:
                        self._inbox[rid] = msg

        self._reader = SSEReader(self.sse_url, on_event, name=f"SSEReader[{self.name}]")
        self._reader.start()

        # Wait for endpoint -> messages_url
        deadline = time.time() + 10
        while self.messages_url is None and time.time() < deadline:
            time.sleep(0.05)

        if self.messages_url is None:
            raise TimeoutError(f"[{self.name}] did not receive endpoint event from {self.sse_url}")

        print(f"  -> messages_url: {self.messages_url}")

        # Must handshake before tools/list, tools/call, etc.
        self.initialize_handshake()

    def close(self):
        try:
            if self._reader:
                self._reader.stop()
        finally:
            try:
                self._http.close()
            except Exception:
                pass

    # ---------- JSON-RPC helpers ----------

    def rpc(self, method: str, params: Optional[dict] = None) -> int:
        """
        JSON-RPC request (expects a response on SSE stream).
        Returns request id.
        """
        if self.messages_url is None:
            raise MCPProtocolError(f"[{self.name}] Not connected (messages_url missing).")

        rid = _now_ms()
        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": rid,
            "method": method,
            "params": params if params is not None else {},
        }

        r = self._http.post(
            self.messages_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )

        # With MCP SSE, responses come over SSE; POST often returns 202 Accepted.
        if r.status_code not in (200, 202):
            raise MCPProtocolError(f"[{self.name}] POST {method} failed: {r.status_code} {r.text}")

        return rid

    def notify(self, method: str, params: Optional[dict] = None) -> None:
        """
        JSON-RPC notification (no id, no response expected).
        """
        if self.messages_url is None:
            raise MCPProtocolError(f"[{self.name}] Not connected (messages_url missing).")

        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params if params is not None else {},
        }

        r = self._http.post(
            self.messages_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if r.status_code not in (200, 202):
            raise MCPProtocolError(f"[{self.name}] POST notify {method} failed: {r.status_code} {r.text}")

    def wait_for_id(self, rpc_id: int, timeout_s: float = 10) -> Dict[str, Any]:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            with self._lock:
                if rpc_id in self._inbox:
                    return self._inbox.pop(rpc_id)
                if self._errors:
                    raise MCPProtocolError(f"[{self.name}] SSE reader error: {self._errors[-1]}")
            time.sleep(0.05)
        raise TimeoutError(f"[{self.name}] Timed out waiting for response id={rpc_id}")

    # ---------- MCP handshake ----------

    def initialize_handshake(self):
        init_id = self.rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                "clientInfo": {"name": "agentic-platform-mcp", "version": "0.1.0"},
            },
        )

        init_resp = self.wait_for_id(init_id, timeout_s=10)
        if "error" in init_resp:
            raise MCPProtocolError(f"[{self.name}] initialize failed: {init_resp}")

        # Correct: notification (no id)
        self.notify("notifications/initialized", {})

    # ---------- Convenience wrappers ----------

    def list_tools(self) -> Dict[str, Any]:
        rid = self.rpc("tools/list", {})
        return self.wait_for_id(rid, timeout_s=10)

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        rid = self.rpc("tools/call", {"name": tool_name, "arguments": arguments})
        return self.wait_for_id(rid, timeout_s=20)


# -----------------------------
# Multi MCP Host
# -----------------------------


class MultiMCPHost:
    """
    A host that manages multiple MCP client sessions (one per server).
    """

    def __init__(self, servers: Dict[str, str]):
        self.sessions: Dict[str, MCPSSESession] = {
            name: MCPSSESession(name, url) for name, url in servers.items()
        }

        # Operator-configured allowlist (recommended). If missing/invalid, we fall
        # back to "discovered tools" mode for developer convenience.
        self._allowlist_cfg = load_allowlist_json()
        if self._allowlist_cfg.warning:
            # Keep this as a print for now (CLI-first repo). In a service,
            # route to structured logging.
            print(f"[WARN] {self._allowlist_cfg.warning}")

    def connect_all(self):
        for name, sess in self.sessions.items():
            print(f"Connecting to {name} ({sess.sse_url})...")
            sess.connect()

    def close(self):
        for sess in self.sessions.values():
            sess.close()

    def tools_all(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for name, sess in self.sessions.items():
            try:
                out[name] = sess.list_tools()
            except Exception as e:
                out[name] = {"error": str(e)}
        return out

    def call(self, server: str, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if server not in self.sessions:
            raise KeyError(f"Unknown server '{server}'. Available: {list(self.sessions.keys())}")
        return self.sessions[server].call_tool(tool, args)

    def call_typed(self, server: str, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        raw = self.call(server, tool, args)
        try:
            typed = parse_typed_tool_output(server, tool, raw)
            return {"raw": raw, "typed": typed.model_dump()}
        except ToolOutputParseError as e:
            return {"raw": raw, "typed_error": str(e)}

    def build_allowlist_from_tools_payload(self, servers_to_tools: dict) -> dict[str, set[str]]:
        """
        Build allowlist from tools/list results, but only from servers
        that successfully returned a tools list.
        """
        allow: dict[str, set[str]] = {}
        for srv, resp in servers_to_tools.items():
            tools = []
            if isinstance(resp, dict) and "result" in resp and isinstance(resp["result"], dict):
                tools = resp["result"].get("tools", [])
            allow[srv] = {t["name"] for t in tools if isinstance(t, dict) and "name" in t}
        return allow

    def summarize_tool_result(self, tool_result_obj: dict) -> dict:
        """
        Produce grounded summary with evidence quotes.
        Input MUST already be schema-validated (typed output preferred).
        Raises GroundingError if claims are not supported by evidence.
        """
        llm = LLMClient()

        source_text = _to_source_text(tool_result_obj)

        msgs = build_summarizer_messages(source_text)
        raw = llm.chat_json(messages=msgs, max_tokens=512, temperature=0.0)

        # Strict JSON gate
        summary = parse_strict_json_plan(raw)

        # Grounding gate (claims must quote source_text)
        validate_grounded_summary(summary, source_text)

        return summary

    def ask_once(self, user_query: str) -> dict:
        trace_dir = get_trace_dir()
        trace = TraceRecorder(meta={"component": "MultiMCPHost.ask_once"})

        def finish(out: dict) -> dict:
            if trace_dir:
                # Attach trace metadata to response for easy debugging.
                path = trace.write(trace_dir, final_output=out)
                out = dict(out)
                out["trace_id"] = trace.trace_id
                out["trace_path"] = path
            return out

        trace.event("request", {"user_query": user_query})

        # Gate 0: input policy
        ok, reason = policy_check_user_query(user_query)
        trace.event("policy_gate", {"allowed": ok, "reason": reason})
        if not ok:
            return finish({"type": "blocked", "reason": reason})

        llm = LLMClient()

        # Live ground truth tools
        servers_to_tools = self.tools_all()
        ok_tools = {srv: resp for srv, resp in servers_to_tools.items()
                    if isinstance(resp, dict) and "result" in resp}

        trace.event(
            "tools_discovered",
            {
                "servers": sorted(list(ok_tools.keys())),
                "tools": {
                    srv: [t.get("name") for t in resp.get("result", {}).get("tools", []) if isinstance(t, dict)]
                    for srv, resp in ok_tools.items()
                },
            },
        )

        # Gate 1: allowlist from discovery
        discovered_allowlist = self.build_allowlist_from_tools_payload(ok_tools)

        # Gate 2: operator-configured allowlist (recommended)
        allowlist = apply_configured_allowlist(discovered_allowlist, self._allowlist_cfg.allowlist)
        trace.event(
            "allowlist",
            {
                "mode": self._allowlist_cfg.mode,
                "warning": self._allowlist_cfg.warning,
                "discovered": as_pretty_allowlist(discovered_allowlist),
                "effective": as_pretty_allowlist(allowlist),
            },
        )

        # Planner messages
        messages = build_planner_messages(user_query, ok_tools)

        # Planner must return strict JSON
        raw_plan = llm.chat_json(messages=messages, max_tokens=256, temperature=0.0)
        trace.event("planner_raw", {"raw": raw_plan})
        try:
            plan = parse_strict_json_plan(raw_plan)
        except PlanParseError as e:
            trace.event("planner_rejected", {"error": str(e)})
            return finish(
                {
                    "type": "blocked",
                    "reason": f"Planner output rejected: {str(e)}",
                    "raw": str(raw_plan)[:400],
                }
            )

        trace.event("planner_plan", {"plan": plan})

        # Validate plan against live catalog
        catalog_dict = json.loads(build_tool_catalog(ok_tools))
        try:
            server, tool, args = validate_plan(plan, catalog_dict)
        except ValidationError as e:
            trace.event("plan_validation_failed", {"error": str(e), "plan": plan})
            return finish(
                {"type": "blocked", "reason": f"Plan validation failed: {str(e)}", "plan": plan}
            )

        # Terminal path: "final_answer" is allowed only to request more info.
        # In PolicyGraph's single-step contract, this produces NO tool call.
        if plan.get("type") == "final_answer":
            answer = str(plan.get("answer", "")).strip()
            trace.event("final_answer", {"answer": answer})
            return finish(
                {
                    "type": "final_answer",
                    "answer": answer,
                    "needs_more_info": True,
                    "plan": plan,
                }
            )

        trace.event("plan_validated", {"server": server, "tool": tool, "args": args})

        # Enforce allowlist
        try:
            enforce_tool_allowlist(server, tool, allowlist)
        except ToolNotAllowed as e:
            trace.event("tool_not_allowed", {"error": str(e), "server": server, "tool": tool})
            return finish({"type": "blocked", "reason": str(e), "plan": plan})

        # Gate 3: execute at most one tool
        trace.event("tool_call", {"server": server, "tool": tool, "args": args})
        tool_result = self.call(server, tool, args)
        trace.event("tool_result_raw", {"raw": tool_result})

        # Typed parsing (output schema gate)
        typed_payload = None
        try:
            typed = parse_typed_tool_output(server, tool, tool_result)
            typed_payload = typed.model_dump()
        except ToolOutputParseError as e:
            trace.event("typed_parse_failed", {"error": str(e)})
            return finish(
                {
                    "type": "tool_result",
                    "plan": plan,
                    "note": f"Typed parsing blocked: {str(e)}",
                    "raw": tool_result,
                }
            )

        trace.event("typed_payload", {"typed": typed_payload})

        # Decide whether to summarize (query intent OR env flag)
        wants_summary = "summarize" in user_query.lower()
        summarize_enabled = os.getenv("SAFE_SUMMARIZE", "0").strip() == "1"
        trace.event("summarize_decision", {"wants_summary": wants_summary, "enabled": summarize_enabled})

        if wants_summary or summarize_enabled:
            try:
                summary = self.summarize_tool_result(typed_payload)
                trace.event("summary", {"summary": summary})
                return finish(
                    {
                        "type": "tool_result_with_summary",
                        "plan": plan,
                        "typed": typed_payload,
                        "summary": summary,
                        "raw": tool_result,
                    }
                )
            except GroundingError as e:
                trace.event("summary_blocked", {"error": str(e)})
                return finish(
                    {
                        "type": "tool_result",
                        "plan": plan,
                        "typed": typed_payload,
                        "note": f"Summary blocked (grounding failed): {str(e)}",
                        "raw": tool_result,
                    }
                )

        # Default: return tool result only
        return finish(
            {
                "type": "tool_result",
                "plan": plan,
                "typed": typed_payload,
                "raw": tool_result,
            }
        )


# -----------------------------
# CLI
# -----------------------------


def main():
    # Prefer env vars when running in docker-compose host container
    # Fallback to localhost ports for local dev.
    servers = {
        "mcp-sharepoint": os.getenv("MCP_SP_URL", "http://localhost:5101/sse"),
        "mcp-servicenow": os.getenv("MCP_SN_URL", "http://localhost:5102/sse"),
        "mcp-policy-kb": os.getenv("MCP_KB_URL", "http://localhost:5103/sse"),
    }
    servers = {k: v for k, v in servers.items() if v}  # drop empty

    host = MultiMCPHost(servers)
    try:
        host.connect_all()

        print("\nCommands:")
        print("  tools")
        print("  call <server> <tool> '<json_args>'")
        print('  ask "<question>"')
        print("  quit\n")

        while True:
            try:
                line = input("mcp> ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not line:
                continue
            if line in ("quit", "exit"):
                break

            if line == "tools":
                print(json.dumps(host.tools_all(), indent=2))
                continue

            if line.startswith("call "):
                parts = shlex.split(line)
                if len(parts) != 4:
                    print("Usage: call <server> <tool> '<json_args>'")
                    continue

                _, server, tool, json_args = parts
                try:
                    args = json.loads(json_args)
                    if not isinstance(args, dict):
                        raise ValueError("args must be a JSON object")
                except Exception as e:
                    print(f"Invalid JSON args: {e}")
                    continue

                resp = host.call(server, tool, args)
                print(json.dumps(resp, indent=2))
                continue

            if line.startswith("ask "):
                q = line[len("ask "):].strip().strip('"').strip("'")

                # Prefer LangGraph path (single source of truth)
                if run_langgraph_once is not None:
                    out = run_langgraph_once(host, q)
                else:
                    # Fallback to legacy planner path if graph module not available
                    out = host.ask_once(q)

                print(json.dumps(out, indent=2))
                continue

            print("Unknown command. Try: tools | call ... | ask ... | quit")

    finally:
        host.close()


if __name__ == "__main__":
    main()