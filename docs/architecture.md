# Architecture

This repo implements a **Multi-MCP Host** that connects to multiple **MCP Servers** over **SSE transport**.
The Host can list tools and call tools, and includes a guarded single-step “ask” mode.

## Components

### MCP Servers (FastMCP + SSE)
Each server exposes a small tool surface:
- **mcp-sharepoint**: search/fetch documents
- **mcp-servicenow**: search/get tickets
- **mcp-policy-kb**: search/fetch policy entries

Some servers also include **explicit side-effect tools** (e.g., delete/close) purely for
evaluation. The SAFE host is expected to block these by default via operator allowlisting.

All use:
- `GET /sse` (SSE stream)
- receive an `endpoint` event with `messages_url`
- `POST /messages/?session_id=...` for JSON-RPC

### Host (MultiMCPHost)
The host maintains **one MCP client session per server**:
- Each `MCPSSESession` connects to exactly **one** MCP server
- `MultiMCPHost` manages multiple sessions and routes calls

### LLM (vLLM OpenAI-compatible)
The host can call an LLM for planning:
- `POST /v1/chat/completions`
- model configured with `LLM_MODEL`

The LLM does **not** execute tools directly. It outputs a strict JSON plan, which is validated and gated.

---

## Data Flow: Connection + Initialization (per server)

1. Host opens SSE stream:
   - `GET /sse`
2. Server emits:
   - `event: endpoint`
   - `data: /messages/?session_id=...`
3. Host POSTs MCP handshake:
   - `initialize` (JSON-RPC request)
   - `notifications/initialized` (JSON-RPC notification)
4. Host can now call:
   - `tools/list`
   - `tools/call`

---

## Ask Flow (Single Step)

User:
- `ask "<natural language>"`

Host:
1. Input policy gate (block unsafe requests early)
2. Tools ground truth:
   - `tools/list` per server (discover tools)
   - compute effective allowlist = discovered tools ∩ `config/allowlist.json`
3. Planner:
   - send system+tools to LLM
   - LLM returns strict JSON plan: `{type:"call_tool", server, tool, args}`
4. Validation gates:
   - JSON strict parsing
   - schema validation vs live tool catalog
   - allowlist enforcement (operator-approved tools only)
5. Execute exactly one tool:
   - `tools/call`
6. Typed parsing:
   - parse `structuredContent` into Pydantic models
7. Optional grounded summary:
   - only from tool output text
   - each claim must include evidence snippet

All stages can emit structured trace events to `SAFE_TRACE_DIR`.

---

## Mermaid Diagram

```mermaid
flowchart LR
  U[User CLI] --> H[MultiMCPHost]

  subgraph MCP Servers
    SP[mcp-sharepoint]
    SN[mcp-servicenow]
    KB[mcp-policy-kb]
  end

  subgraph LLM
    V[vLLM OpenAI API]
  end

  H <-- SSE + JSON-RPC --> SP
  H <-- SSE + JSON-RPC --> SN
  H <-- SSE + JSON-RPC --> KB

  H -->|plan request| V
  V -->|strict JSON plan| H

  H -->|tools/call| SP
  H -->|tools/call| SN
  H -->|tools/call| KB

  H -->|typed parse + optional grounded summary| U