---
applyTo: "agents/**/*.py"
description: "Use when editing Python agent code — enforces ReAct pattern, async conventions, and LangSmith tracing"
---

# Python Agent Guidelines

- All agents inherit from `agents/base/` and implement the ReAct loop
- Every public method must be `async`
- Use Pydantic `BaseModel` for all request/response schemas
- Tools live in `tools/` — never embed tool logic in agent classes
- MCP calls go through `adapters/` — never call MCP servers directly
- Add `@traceable` decorator (LangSmith) on every reasoning step and tool call
- Prompts are separate files (not inline strings) — store in agent's directory
