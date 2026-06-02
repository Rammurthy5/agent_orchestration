---
applyTo: "adapters/**/*.py"
description: "Use when editing MCP adapters — enforces retry logic, auth, Pydantic validation, and the adapter boundary pattern"
---

# MCP Adapter Guidelines

- All adapters inherit from `adapters/base.py` (`BaseMCPAdapter`)
- Adapters are the ONLY way to call MCP servers — agents and tools never call MCP directly
- Tool functions in `tools/` raise `NotImplementedError` if invoked without adapter (safety boundary)
- Every adapter `call()` method must have the `@traceable` decorator for LangSmith tracing
- Use `httpx.AsyncClient` with explicit timeouts (from base class)
- Retry config: exponential backoff (100ms→5s), max 3 attempts, ±jitter
- Auth: Bearer token injected by base class in request headers
- Validate all responses with Pydantic models before returning to agent
- Each adapter has a `base_url` class attribute pointing to its MCP server
- Pattern for new adapters: subclass `BaseMCPAdapter`, set `base_url`, implement typed `call()` methods
