# Agent Contract

## Purpose

The Agentic Platform MCP host implements a **controlled, single-step agent** that
uses an LLM strictly as a planner and reasoner, while delegating all side effects
and data access to MCP tools.

The agent **does not autonomously act**, **does not chain tools**, and **does not produce ungrounded summaries** (summaries must carry verbatim evidence; otherwise summarization is rejected).

---

## Core Principles

This agent follows five hard guarantees:

1. **Single-Step Execution**
   - At most **one tool call per user request**
2. **Grounded Outputs**
   - Tool payloads are returned verbatim or summarized with evidence. If a tool call cannot be safely executed, the agent returns a *needs-more-info* response instead of guessing.
3. **Strict JSON Planning**
   - The LLM must emit machine-validated JSON plans
4. **Host-Enforced Safety**
   - The host, not the LLM, enforces policies and constraints
5. **Deterministic Control Flow**
   - No self-loops, retries, or autonomous reasoning chains

---

## Execution Model

Each user request follows this fixed pipeline:

1. User query received
2. Input safety policy check
3. Tool catalog fetched live from MCP servers
4. LLM generates a **single JSON plan**
5. Plan is validated against tool schemas
6. Exactly **one tool is executed** (or none)
7. Typed parsing of tool output
8. Optional grounded summarization
9. Response returned

The agent **cannot** bypass or reorder these steps.

---

## In Scope

The agent **is allowed to**:
- Select exactly one MCP tool
- Provide arguments strictly matching tool schemas
- Return tool output verbatim or summarized with evidence
- Reject requests that violate safety or policy constraints

---

## Out of Scope (Explicit Non-Goals)

The agent **will NOT**:
- Perform multi-step reasoning across tools
- Call multiple tools in a single request
- Modify external systems
- Write data back to MCP servers
- Maintain long-term memory
- Self-correct or retry plans autonomously
- Execute arbitrary code
- Answer questions without tool grounding

These are **intentional design exclusions**, not missing features.

---

## LLM Responsibilities

The LLM is treated as a **pure function** that:
- Interprets user intent
- Selects a tool and arguments
- Produces strict JSON output

The LLM **does not**:
- Execute tools
- Enforce safety
- Decide execution order
- Validate schemas
- Produce final authoritative answers

---

## Host Responsibilities

The host **must always**:
- Enforce safety policies
- Validate all LLM outputs
- Enforce tool allowlists
- Enforce single-step execution
- Parse tool outputs into typed schemas
- Reject ungrounded or malformed responses

---

## Failure Modes

If any step fails, the agent must:
- Stop execution immediately
- Return a structured error or blocked response
- Never guess or hallucinate missing data

Failures include:
- Invalid JSON from LLM
- Tool not found
- Schema mismatch
- Safety policy violation
- Output parsing failure

---

## Future Extensions (Not Implemented)

The following may be added later but are **not part of this contract**:
- Multi-step planning
- Tool retries
- Memory
- Background agents
- Parallel tool execution
- Autonomous workflows

Any future extension **must explicitly update this contract**.

---

## Summary

This agent is a **controlled orchestration layer**, not an autonomous system.

Predictability, auditability, and safety are prioritized over flexibility.