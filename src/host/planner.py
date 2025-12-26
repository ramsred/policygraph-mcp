import json
import re
from typing import Any, Dict, List


SYSTEM_RULES = """You are a tool-routing planner inside an agentic platform.

Hard rules:
- You MUST respond with ONLY valid JSON (no markdown, no extra text).
- You must choose exactly ONE of:
  1) {"type":"call_tool","server":"<server>","tool":"<tool>","args":{...}}
  2) {"type":"final_answer","answer":"...","needs_more_info":true}

Tool use rules:
- You may ONLY choose tools that appear in the provided TOOL_CATALOG.
- Tool arguments MUST match the tool's inputSchema (keys and types).
- If you cannot answer without tool output, choose final_answer with needs_more_info=true.
- Do NOT hallucinate facts. Do NOT invent tools. Do NOT guess IDs. Use search tools first when needed.

Routing rules (MUST follow):
- If the user mentions a SharePoint doc id matching: sp-<digits> (example: sp-001),
  then you MUST use mcp-sharepoint.fetch_sharepoint_doc with {"doc_id": "<that id>"}.
- If the user mentions a Policy KB policy id matching: policy-<digits> (example: policy-001),
  then you MUST use mcp-policy-kb.fetch_policy_entry with {"policy_id": "<that id>"}.
- If the user mentions a ServiceNow ticket id matching common patterns like:
  INC<digits>, RITM<digits>, TASK<digits>, CHG<digits> (case-insensitive),
  then you MUST use mcp-servicenow.get_ticket with {"ticket_id": "<that id>"}.
- If the user asks to "summarize" and provides an id, you MUST first fetch the document/policy/ticket
  using the correct fetch tool above (still only one tool call total).
- If the user asks to "find/search" but does NOT provide a concrete id, use the relevant search tool first:
  - SharePoint: mcp-sharepoint.search_sharepoint {"query": "...", "top_k": N}
  - Policy KB:  mcp-policy-kb.search_policy_kb {"query": "...", "top_k": N}
  - ServiceNow: mcp-servicenow.search_servicenow_tickets {"query": "...", "top_k": N}
"""


def build_tool_catalog(servers_to_tools: Dict[str, Any]) -> str:
    """
    servers_to_tools:
      { server_name: {"result": {"tools":[...]}} } where tools come from tools/list.
    """
    catalog = {}
    for server, resp in servers_to_tools.items():
        tools = resp.get("result", {}).get("tools", [])
        catalog[server] = [
            {
                "name": t["name"],
                "description": t.get("description", ""),
                "inputSchema": t.get("inputSchema", {}),
            }
            for t in tools
            if isinstance(t, dict) and "name" in t
        ]
    return json.dumps(catalog, ensure_ascii=False)


def _extract_id_hints(user_query: str) -> Dict[str, str]:
    """
    Optional: include hints in the prompt to reduce planner mistakes.
    This does NOT execute anything; it just helps the model route correctly.
    """
    q = user_query.strip()

    sp = re.search(r"\b(sp-\d+)\b", q, re.IGNORECASE)
    pol = re.search(r"\b(policy-\d+)\b", q, re.IGNORECASE)
    sn = re.search(r"\b((?:INC|RITM|TASK|CHG)\d+)\b", q, re.IGNORECASE)

    hints: Dict[str, str] = {}
    if sp:
        hints["sharepoint_doc_id"] = sp.group(1)
    if pol:
        hints["policy_id"] = pol.group(1)
    if sn:
        hints["servicenow_ticket_id"] = sn.group(1)
    return hints


def build_planner_messages(user_query: str, servers_to_tools: Dict[str, Any]) -> List[Dict[str, str]]:
    catalog_json = build_tool_catalog(servers_to_tools)
    hints = _extract_id_hints(user_query)

    user_msg = f"""USER_QUERY:
{user_query}

ID_HINTS (best-effort, may be empty):
{json.dumps(hints, ensure_ascii=False)}

TOOL_CATALOG (JSON):
{catalog_json}

Return ONLY one JSON object following the schema.
"""

    return [
        {"role": "system", "content": SYSTEM_RULES},
        {"role": "user", "content": user_msg},
    ]