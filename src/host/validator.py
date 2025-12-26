from __future__ import annotations

from typing import Any, Dict, Tuple


class ValidationError(Exception):
    pass


def _type_ok(jsonschema_type: str, value: Any) -> bool:
    if jsonschema_type == "string":
        return isinstance(value, str)
    if jsonschema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if jsonschema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if jsonschema_type == "boolean":
        return isinstance(value, bool)
    if jsonschema_type == "object":
        return isinstance(value, dict)
    if jsonschema_type == "array":
        return isinstance(value, list)
    # Unknown type => be conservative.
    return False


def validate_plan(plan: Dict[str, Any], tool_catalog: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any]]:
    """Validate a planner plan against a tool catalog.

    tool_catalog format:
      { server: [ {name, inputSchema, ...}, ... ] }

    Returns:
      (server, tool, args) for call_tool plans.

    Special case:
      For final_answer plans (needs_more_info=true), returns ("", "", {}).
      The caller MUST treat this as a terminal, no-tool-call path.
    """
    if not isinstance(plan, dict):
        raise ValidationError("Plan must be a JSON object")

    ptype = plan.get("type")
    if ptype not in ("call_tool", "final_answer"):
        raise ValidationError("Plan.type must be call_tool or final_answer")

    if ptype == "final_answer":
        # In single-step mode, final_answer is allowed only as a "needs more info" response.
        if plan.get("needs_more_info") is not True:
            raise ValidationError("final_answer requires needs_more_info=true in this phase")

        answer = plan.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise ValidationError("final_answer requires a non-empty 'answer' string")

        return ("", "", {})

    # call_tool path
    server = plan.get("server")
    tool = plan.get("tool")
    args = plan.get("args")

    if server not in tool_catalog:
        raise ValidationError(f"Unknown server: {server}")

    tools = {t["name"]: t for t in tool_catalog[server]}
    if tool not in tools:
        raise ValidationError(f"Unknown tool '{tool}' on server '{server}'")

    if not isinstance(args, dict):
        raise ValidationError("args must be an object")

    schema = tools[tool].get("inputSchema", {})
    props = schema.get("properties", {}) or {}
    required = schema.get("required", []) or []

    # required keys
    for k in required:
        if k not in args:
            raise ValidationError(f"Missing required arg '{k}' for tool '{tool}'")

    # disallow unexpected keys (strict)
    for k in args.keys():
        if k not in props:
            raise ValidationError(f"Unexpected arg '{k}' for tool '{tool}'")

    # basic type checks
    for k, v in args.items():
        expected_type = props.get(k, {}).get("type")
        if expected_type and not _type_ok(expected_type, v):
            raise ValidationError(f"Arg '{k}' expected type '{expected_type}', got '{type(v).__name__}'")

    return (server, tool, args)
