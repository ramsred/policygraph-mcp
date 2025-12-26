# Contributing

Thanks for considering contributing!

## How to run
See `docs/quickstart.md`.

## What we accept
- Bug fixes
- Docs improvements
- New MCP server examples (small tool surface)
- Safety / validation improvements
- Tests and CI enhancements

## Guardrails
- Do not commit model weights or `models/` artifacts.
- All tool outputs must have:
  - `structuredContent` for typed parsing
  - a registered Pydantic schema in `src/host/tool_schemas.py`

## Dev workflow
1. Create a branch
2. Make change + add/adjust tests
3. Run locally:
   - `ruff` (lint)
   - `mypy` (types)
   - `pytest` (tests)
4. Open PR with:
   - what changed
   - how to reproduce / validate
   - any backwards-compat notes