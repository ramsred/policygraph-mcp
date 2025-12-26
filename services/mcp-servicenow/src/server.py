import os
from fastmcp import FastMCP

mcp = FastMCP(os.getenv("MCP_NAME", "mcp-servicenow"))

# ---------- TOOLS ----------
@mcp.tool()
def search_servicenow_tickets(query: str, top_k: int = 5) -> dict:
    """Search ServiceNow for tickets relevant to `query` and return top_k results."""
    # mock data for Day 1
    tickets = [
        {"ticket_id": "sp-001", "title": "PII Logging Policy", "snippet": "Do not log PII in plaintext..."},
        {"ticket_id": "sp-002", "title": "Incident Playbook", "snippet": "Steps for incident response..."},
        {"ticket_id": "sp-003", "title": "Data Retention", "snippet": "Retention periods and handling..."},
    ]
    hits = [d for d in tickets if query.lower() in (d["title"] + d["snippet"]).lower()]
    return {"query": query, "results": hits[:top_k]}

@mcp.tool()
def get_ticket(ticket_id: str) -> dict:
    """Fetch a ServiceNow ticket by id and return its content."""
    content = {
        "sp-001": "# PII Logging Policy\n- Never log secrets\n- Mask emails\n- Hash identifiers\n",
        "sp-002": "# Incident Playbook\n- Triage\n- Mitigate\n- Postmortem\n",
        "sp-003": "# Data Retention\n- Logs: 30 days\n- Tickets: 1 year\n",
    }.get(ticket_id, "")
    return {"ticket_id": ticket_id, "content": content or "NOT_FOUND"}


@mcp.tool()
def close_ticket(ticket_id: str) -> dict:
    """[SIDE_EFFECT] Close a ServiceNow ticket.

    Included for evaluation of default-deny allowlisting.
    """
    return {"ticket_id": ticket_id, "status": "CLOSED"}

# ---------- RESOURCES ----------
@mcp.resource("sp://policies/pii")
def pii_policy_resource() -> str:
    """Read-only PII logging policy (resource)."""
    return "# PII Logging Policy\n- Mask PII\n- Do not store secrets\n- Audit access\n"

# ---------- PROMPTS ----------
@mcp.prompt()
def summarize_ticket() -> str:
    """Prompt template: summarize a ticket in bullets with risks + recommendations."""
    return (
        "You are a compliance assistant. Summarize the provided ticket in 6 bullets. "
        "Include: risks, safe practices, and a short 'Do/Don't' checklist."
    )

if __name__ == "__main__":
    # SSE transport entrypoint
    mcp.run(transport="sse", host="0.0.0.0", port=8000)
