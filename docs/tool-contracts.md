# Tool Contracts & Extension Model

This document defines the **required contracts** for MCP tools used by the
`MultiMCPHost`.

All tools must comply with these contracts to ensure:
- Safety (no hallucinations, no unauthorized actions)
- Determinism (typed outputs)
- Contributor scalability

---

## 1. What Is a Tool Contract?

A tool contract is the **formal agreement** between:
- An MCP server (tool provider)
- The Multi MCP Host (tool consumer)

The contract consists of:
1. Tool metadata
2. Input schema
3. Output schema
4. Runtime behavior guarantees

---

## 2. Required Tool Metadata

Every tool **MUST** define:

```json
{
  "name": "fetch_sharepoint_doc",
  "description": "Fetch a SharePoint doc by id and return its content."
}
Rules
	•	name must be unique per server
	•	description must describe what the tool does
	•	No hidden or implicit tools are allowed

⸻

3. Input Schema Contract (MANDATORY)

Every tool MUST provide a valid JSON Schema under inputSchema.

Example:
{
  "type": "object",
  "properties": {
    "doc_id": { "type": "string" }
  },
  "required": ["doc_id"]
}
Rules
	•	All required arguments must be explicitly listed
	•	No free-form or undocumented parameters
	•	Defaults must be declared in schema
⸻

4. Output Schema Contract (MANDATORY)

Every tool MUST provide an outputSchema.

Example:
{
  "type": "object",
  "properties": {
    "doc_id": { "type": "string" },
    "content": { "type": "string" }
  },
  "required": ["doc_id", "content"]
}
Rules
	•	Output schema must describe structuredContent
	•	Free-form text is allowed only inside known fields
	•	additionalProperties: false is strongly recommended
⸻

5. Runtime Tool Response Shape

At runtime, tools return MCP-compliant responses:
{
  "jsonrpc": "2.0",
  "id": 123,
  "result": {
    "structuredContent": { ... },
    "content": [
      { "type": "text", "text": "..." }
    ],
    "isError": false
  }
}
Required fields
	•	structuredContent: machine-parseable payload
	•	isError: explicit success/failure flag
⸻

6. Typed Parsing Requirement (Host-Side)

Every tool must have a typed parser on the host side.

Example (Pydantic):
class SharePointDoc(BaseModel):
    doc_id: str
    content: str
The host will:
	•	Parse structuredContent into a typed object
	•	Reject outputs that do not conform

Failure behavior
	•	Tool output is returned raw
	•	LLM is NOT allowed to reason over invalid output

⸻

7. Tool Allowlisting Model

The host dynamically builds an allowlist using tools/list.

Only tools returned by tools/list are callable.

Implications
	•	No hidden tools
	•	No dynamic tool creation
	•	No internal-only tools callable by the planner
⸻

8. Single-Step Tool Constraint

Each user query may invoke at most one tool.

Why:
	•	Prevents tool chaining attacks
	•	Simplifies safety reasoning
	•	Makes behavior predictable

Multi-step workflows must be implemented explicitly
(e.g., future LangGraph orchestration).
⸻

9. Grounded Summarization Contract (Optional)

If summarization is enabled:
	•	Summaries must include evidence quotes
	•	Every claim must map to source text
	•	Ungrounded claims are rejected

Example schema:
{
  "type": "summary",
  "bullets": [
    { "claim": "...", "evidence": "..." }
  ]
}
⸻

10. How to Add a New MCP Tool (Checklist)

Contributor checklist:
	1.	Implement tool on MCP server
	2.	Define inputSchema (JSON Schema)
	3.	Define outputSchema
	4.	Add typed parser on host
	5.	Add tests:
	•	valid input
	•	invalid input
	•	malformed output
	6.	Verify:
	•	appears in tools/list
	•	passes allowlist
	•	parses correctly
⸻

11. What Is Explicitly NOT Allowed

❌ Tools with side effects without safeguards
❌ Undocumented parameters
❌ Free-form output without schema
❌ Planner-controlled tool logic
❌ Hidden or conditional tool exposure
⸻

12. Summary

The Multi MCP Host treats tools as untrusted boundaries.

Safety and correctness are enforced by:
	•	Explicit schemas
	•	Typed parsing
	•	Allowlists
	•	Single-step execution

If a tool does not conform, it does not run.

This design enables safe scaling to many MCP servers and contributors.

---

## What this gives you immediately

- 📚 Clear contributor onboarding
- 🔐 Strong safety guarantees
- 🧱 Extensible architecture
- ⭐ Big jump in perceived repo maturity

When you’re ready, say **“Step 4”**  
👉 We’ll implement **CI/CD with GitHub Actions** and make the repo *officially production-grade*.