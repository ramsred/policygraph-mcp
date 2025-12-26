![CI](https://github.com/ramsred/policygraph-mcp/actions/workflows/ci.yml/badge.svg)

# PolicyGraph: A Policy-Gated MCP Runtime for Safe Tool Execution

PolicyGraph is a **safety-first MCP host and single-step agent runtime for tool-mediated LLM interactions** designed for enterprise-style and regulated environments.  
It enforces safety and governance guarantees **by construction**, rather than relying on model behavior alone.

Key properties:
- **default-deny** tool execution (operator-controlled allowlist)
- **schema-constrained planning** (LLM must output a strict JSON plan)
- **typed tool outputs** (Pydantic parsing)
- **evidence-locked summaries** (summaries must quote verbatim evidence)
- **deterministic control flow** (workflow-level determinism with replayable execution traces)
- **audit-friendly traces** (structured per-run trace artifacts)

The design is intentionally **narrow**:
- **at most one tool call per user request**
- **read-only tools** are the default assumption
- no autonomous multi-step loops, memory, or background jobs

This scope supports a **publishable research artifact** with:
- a concrete threat model,
- enforceable safety guarantees,
- and reproducible evaluations.

---

## Quickstart
See `docs/quickstart.md`.

---

## What is novel here?

PolicyGraph is not a new LLM or agent framework.  
Its contribution is a **governed execution model** for MCP tools that enforces safety properties *independently of model correctness*:

- **Default-deny tool execution** using an operator-controlled allowlist
- **Schema-constrained planning and execution** that rejects malformed or unauthorized plans before tool invocation
- **Evidence-locked summarization**, where every generated claim must include verbatim evidence from tool output
- **Audit-ready trace artifacts** emitted for every run

These guarantees hold even if the planner model is compromised or adversarial.

---

## Key guarantees

1) **Policy gate (input)**
- Blocks obviously unsafe requests before any tool discovery or execution.

2) **Operator allowlist (default deny)**
- A tool is callable only if it is:
  - discovered live from MCP servers (`tools/list`), **and**
  - explicitly listed in `config/allowlist.json`.

3) **Strict JSON plan**
- The planner must emit exactly one of:
  - `{ "type": "call_tool", "server": "...", "tool": "...", "args": {...} }`
  - `{ "type": "final_answer", "answer": "...", "needs_more_info": true }`

4) **Schema validation**
- Tool arguments must match the MCP `inputSchema` exactly:
  - required fields present
  - no extra keys
  - correct types

5) **Typed output parsing**
- Tool outputs are parsed into tool-specific Pydantic models.
- Invalid or unexpected outputs are rejected.

6) **Grounded summaries**
- Each summary bullet must include an `evidence` field that is a **verbatim substring** of the tool output.
- Unsupported claims are rejected by construction.

---

## Non-goals

This project intentionally does **not** address:
- multi-step autonomous agents
- long-term memory or learning
- retrieval routing or RAG optimization
- Kubernetes orchestration or observability pipelines

These are deferred to future work and a separate platform-level implementation.

---

## Configuration

- **Tool allowlist**
  - Path: `config/allowlist.json`
  - Override with: `SAFE_ALLOWLIST_PATH`

- **Tracing**
  - Set `SAFE_TRACE_DIR=eval/traces` to persist per-run JSON traces

- **Summarization**
  - Set `SAFE_SUMMARIZE=1` (or ask a query containing “summarize”)

---

## Evaluation

### Offline (LLM-independent) gate tests

Runs locally **without MCP servers or an LLM**.

These tests validate safety gates independently of model behavior,
demonstrating enforcement even under adversarial or malformed inputs.

```bash
python -m src.eval.offline_gate_eval
```

Writes results to:
- `eval/results/offline_gate_eval.json`

### End-to-end eval (requires MCP servers + LLM endpoint)

```bash
SAFE_TRACE_DIR=eval/traces \
python -m src.eval.end_to_end_eval --cases eval/cases_end_to_end.jsonl
```

This compares:
- `MultiMCPHost.ask_once` (SAFE) vs
- `src.eval.naive_agent.naive_ask_once` (baseline)

Outputs:
- `eval/results/<timestamp>_metrics.json`
- `eval/results/<timestamp>_runs.jsonl`
- `eval/results/<timestamp>_table.md`

---

## Repository structure

- `src/host/` — MCP host, policy gate, planner/validator, typed parsing, grounded summarization, tracing
- `src/graph/` — LangGraph single-step state machine (optional)
- `services/` — toy MCP servers (SharePoint, ServiceNow, Policy KB)
- `config/` — operator allowlist
- `eval/` — evaluation cases + results output
- `docs/` — architecture + threat model + contracts

---

## Docs

- `docs/architecture.md`
- `docs/agent-contract.md`
- `docs/safety-threat-model.md`
- `docs/tool-contracts.md`

---


## License
Apache-2.0
