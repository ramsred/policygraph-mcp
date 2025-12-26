# Quickstart

This repo provides:
- 3 toy MCP servers (SharePoint, ServiceNow, Policy KB) over **SSE transport**
- a **Multi-MCP Host** that can:
  - list tools
  - call tools
  - run a single-step `ask` flow (LLM planner -> validated plan -> one tool call)
  - optionally summarize with evidence locking

---

## Prereqs

- Docker + Docker Compose v2
- For the `llm` service (GPU):
  - NVIDIA drivers + NVIDIA Container Toolkit
- `curl` (and optionally `jq`)

---

## 1) Start everything

From repo root:

```bash
docker compose up -d --build
docker compose ps
```

---

## 2) Verify the LLM health (vLLM)

```bash
curl -s http://localhost:8008/v1/models | jq
```

Test chat:

```bash
curl -s http://localhost:8008/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-7B-Instruct",
    "messages": [{"role":"user","content":"Reply with only the number: 12*17"}],
    "max_tokens": 20
  }' | jq -r '.choices[0].message.content'
```

---

## 3) Run the host locally (recommended for development)

If you run the host locally (not inside Compose), set:

```bash
export LLM_BASE_URL=http://localhost:8008/v1
export LLM_MODEL=Qwen/Qwen2.5-7B-Instruct

export MCP_SP_URL=http://localhost:5101/sse
export MCP_SN_URL=http://localhost:5102/sse
export MCP_KB_URL=http://localhost:5103/sse

# Optional:
export SAFE_ALLOWLIST_PATH=config/allowlist.json
export SAFE_TRACE_DIR=eval/traces
export SAFE_SUMMARIZE=0
```

Then:

```bash
python -m src.host.multi_mcp_host
```

---

## 4) Try the CLI

List tools:

```text
mcp> tools
```

Direct tool call:

```text
mcp> call mcp-sharepoint search_sharepoint '{"query":"PII Logging","top_k":5}'
```

Single-step ask:

```text
mcp> ask "Find the PII Logging policy"
mcp> ask "Fetch SharePoint doc sp-001"
mcp> ask "Summarize policy policy-002"
```

Summarization runs when:
- your query contains the word `summarize`, or
- `SAFE_SUMMARIZE=1`.

---

## 5) Run evaluation

Offline gate tests (no servers / no LLM needed):

```bash
python -m src.eval.offline_gate_eval
```

End-to-end eval (servers + LLM required):

```bash
SAFE_TRACE_DIR=eval/traces \
python -m src.eval.end_to_end_eval --cases eval/cases_end_to_end.jsonl
```

---

## Shutdown

```bash
docker compose down
```

To remove volumes too:

```bash
docker compose down -v
```
