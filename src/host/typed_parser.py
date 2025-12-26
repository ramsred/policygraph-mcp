from __future__ import annotations
from typing import Any, Dict, Optional, Tuple
from pydantic import BaseModel, ValidationError as PydValidationError

from .tool_schemas import TOOL_OUTPUT_MODELS, ToolKey


class ToolOutputParseError(RuntimeError):
    pass


def extract_structured_content(tool_call_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    FastMCP tool call responses typically look like:
      {"jsonrpc":"2.0","id":...,"result":{"content":[...], "structuredContent":{...}, "isError":false}}
    """
    if not isinstance(tool_call_response, dict):
        raise ToolOutputParseError("tool_call_response must be dict")

    if "error" in tool_call_response:
        raise ToolOutputParseError(f"MCP error response: {tool_call_response['error']}")

    result = tool_call_response.get("result")
    if not isinstance(result, dict):
        raise ToolOutputParseError("Missing/invalid 'result' in tool response")

    if result.get("isError") is True:
        raise ToolOutputParseError(f"Tool returned isError=true: {result}")

    sc = result.get("structuredContent")
    if not isinstance(sc, dict):
        # fall back: sometimes only text exists
        raise ToolOutputParseError("Missing 'structuredContent' (needed for typed parsing).")

    return sc


def parse_typed_tool_output(
    server: str,
    tool: str,
    tool_call_response: Dict[str, Any],
) -> BaseModel:
    key: ToolKey = (server, tool)
    model = TOOL_OUTPUT_MODELS.get(key)
    if model is None:
        raise ToolOutputParseError(
            f"No output schema registered for ({server}, {tool}). "
            f"Add it to TOOL_OUTPUT_MODELS."
        )

    payload = extract_structured_content(tool_call_response)

    try:
        return model.model_validate(payload)
    except PydValidationError as e:
        raise ToolOutputParseError(
            f"Typed parsing failed for ({server}, {tool}) against {model.__name__}: {e}"
        ) from e