# Enforced Invariants (Publication-Ready)

This document converts the project's safety claims into **explicit, testable invariants**.
Each invariant includes:

- **Statement** (precise behavioral claim)
- **Enforcement** (code path)
- **Evidence** (evaluation output)

> If an invariant cannot be enforced by code or demonstrated by evaluation, it should be weakened or removed.

---

## INV-0: Input Policy Gate (Pre-Discovery)

**Statement.** If the user query matches a disallowed safety pattern, PolicyGraph **must halt** before tool discovery and before any tool call.

**Enforcement.**
- `src/host/safety.py::policy_check_user_query`
- `src/host/multi_mcp_host.py::MultiMCPHost.ask_once` (Gate 0)

**Evidence.**
- `python -m src.eval.offline_gate_eval`
- `eval/results/offline_gate_eval.json → policy_gate`

---

## INV-1: Strict JSON-Only Plan Parsing

**Statement.** PolicyGraph accepts planner output **only if** it is a **single JSON object** (no markdown, no extra text). Otherwise execution is blocked before validation/allowlisting.

**Enforcement.**
- `src/host/safety.py::parse_strict_json_plan`
- `src/host/multi_mcp_host.py::MultiMCPHost.ask_once` (planner parse gate)

**Evidence.**
- `eval/results/offline_gate_eval.json → plan_parse`

---

## INV-2: Tool Selection + Argument Schema Conformance

**Statement.** For any `call_tool` plan, PolicyGraph executes the tool **only if**:
1) `(server, tool)` exist in the live-discovered catalog, and  
2) `args` match the tool's `inputSchema` exactly:
   - all `required` keys present,
   - no extra keys,
   - basic JSONSchema type checks.

**Enforcement.**
- `src/host/validator.py::validate_plan`

**Evidence.**
- `eval/results/offline_gate_eval.json → plan_gate` (hand-crafted invalid plans)
- `eval/results/offline_gate_eval.json → plan_fuzz` (property-style fuzzing)

---

## INV-3: Default-Deny Tool Authorization

**Statement.** A tool is executable **only if** it is in the **effective allowlist**:
- discovered live via `tools/list`, **AND**
- present in the operator-configured allowlist (`config/allowlist.json`).

**Enforcement.**
- `src/host/allowlist_config.py::apply_configured_allowlist`
- `src/host/safety.py::enforce_tool_allowlist`

**Evidence.**
- `eval/results/offline_gate_eval.json → plan_gate` (`disallowed_tool_by_allowlist`)
- `eval/results/offline_gate_eval.json → plan_fuzz` (`blocked_by_allowlist`)

---

## INV-4: Typed Tool Output Gate (Structured Output Validation)

**Statement.** For registered tools, PolicyGraph produces a typed payload **only if**:
- the MCP response contains `result.structuredContent`,
- `isError != true`,
- the structured object validates against a tool-specific Pydantic model.

If typed parsing fails, the system **must not** emit a grounded summary, and should return the raw tool response with a `Typed parsing blocked` note.

**Enforcement.**
- `src/host/typed_parser.py::parse_typed_tool_output`
- `src/host/typed_models.py` (tool-specific models)

**Evidence.**
- `eval/results/offline_gate_eval.json → typed_output`

---

## INV-5: Evidence-Locked Summaries (Anti-Hallucination by Construction)

**Statement.** If PolicyGraph emits a summary, every bullet's `evidence` field must be a **verbatim substring** of the canonical source text derived from validated tool output. Otherwise summarization is blocked.

**Enforcement.**
- `src/host/summarizer.py::validate_grounded_summary`

**Evidence.**
- `eval/results/offline_gate_eval.json → grounding`
- `eval/results/offline_gate_eval.json → grounding_fuzz`

---

## INV-6: Single-Step Execution (Bounded Agency)

**Statement.** PolicyGraph executes **at most one tool call** per user request. There is no open-ended multi-tool loop in the core runtime.

**Enforcement.**
- `src/host/multi_mcp_host.py::MultiMCPHost.ask_once` (exactly one call site to `self.call(...)`)
- Optional: `src/graph/langgraph_agent.py` (graph has no tool-call loop)

**Evidence.**
- Structural property (inspectable in code) + end-to-end harness in `src/eval/end_to_end_eval.py`

---

## Terminal Plans: `final_answer` (Needs-More-Info Only)

**Statement.** In this repo's single-step contract, `final_answer` is allowed only when `needs_more_info=true` and must not produce a tool call.

**Enforcement.**
- `src/host/validator.py` (final_answer validation)
- `src/host/multi_mcp_host.py::MultiMCPHost.ask_once` (terminal branch)

**Evidence.**
- `eval/results/offline_gate_eval.json → plan_gate` (`final_answer_needs_more_info_true`)
