# Copilot Instructions

## Project Overview

Multi-agent AI orchestration platform: Go CLI + orchestrator routes tasks via gRPC to specialized Python AI agents (Flights, Marketplace, Stay, Twitter). See [ARCHITECTURE.md](../ARCHITECTURE.md) for system flow and [REQUIREMENTS.md](../REQUIREMENTS.md) for full agent specs.

## Project Structure

```
cmd/               # Go CLI entrypoints
internal/          # Go orchestrator, router, gRPC server
pkg/               # Reusable Go packages
agents/            # Python agent runtime
  base/            # Base agent class, ReAct loop
  flights/         # Domain agents (each has agent.py, tools.py, prompts/)
  marketplace/
  stay/
  twitter/
tools/             # Python tool implementations (never call directly — use adapters)
adapters/          # MCP adapters (retries, auth, telemetry)
protos/            # gRPC protobuf definitions
evals/             # Evaluation pipelines (pytest)
migrations/        # PostgreSQL/PgVector schema
```

## Build & Test

```bash
# Go
go build ./cmd/...
go test ./... -race -count=1

# Python (requires Python 3.11+)
pip install -e ".[dev]"
pytest --cov agents/ tools/

# Proto generation (requires buf CLI)
buf generate protos/
```

## Local Development

Start services in order:
1. Python agent service: `python -m agents.server` (listens :50052)
2. Go orchestrator: `go run ./cmd/orchestrator` (listens :50051, connects to :50052)

Key environment variables (all have defaults):
- `ORCHESTRATOR_PORT` (50051), `AGENT_ENDPOINT` (localhost:50052)
- `AGENT_TIMEOUT_SECONDS` (30), `AGENT_MAX_RETRIES` (3)
- `OTEL_SERVICE_NAME` (orchestrator), `OTEL_EXPORTER_OTLP_ENDPOINT` (localhost:4317)

## Code Style

### Go
- Idiomatic Go: `context.Context` first param, explicit error returns, error wrapping
- Interfaces at boundaries only, composition over inheritance
- Structured logging (slog), OpenTelemetry spans on every handler
- Table-driven tests, no global state

### Python
- PEP-8, type hints everywhere, async/await by default
- Pydantic models for all data structures
- Separate prompts from logic (prompts in `agents/<domain>/prompts/`)
- Tools are isolated in `tools/` — never embed tool logic in agent classes
- Linting: `ruff` (line-length 100, target py311)

## Agent Contract

Every agent MUST inherit from `agents/base/agent.py` and implement the ReAct loop:
- `reasoning()` → `tool_selection()` → `execute()` → `reflect()` → `final_answer()`
- All methods are `async` and decorated with `@traceable` (LangSmith)
- Agent validates query via `_domain_keywords()` — raises `OutOfScopeError` if no keyword match
- Max 10 reasoning iterations per request

## Observability

- **Go**: OpenTelemetry tracing + correlation IDs on all requests
- **Python**: LangSmith `@traceable` decorator on every reasoning step and tool call

## Database

PostgreSQL + PgVector. Never inline raw SQL if ORM/query builder exists. Schema in [migrations/](../migrations/).

## MCP Rules

- Never call MCP servers directly from agents — always use `adapters/`
- Tool functions in `tools/` raise `NotImplementedError` if called directly (enforces adapter usage)
- Adapters handle: retries (exponential backoff), auth, telemetry, response normalization
- Validate all MCP payloads with Pydantic

## Evals

Every new capability requires: unit tests, integration tests, eval coverage, regression evals. See [EVALS.md](../EVALS.md) for strategy.
Tests live in `evals/` (not `tests/`). pytest config: `asyncio_mode = "auto"`, `testpaths = ["evals"]`.

## Proto Workflow

When modifying `protos/orchestrator/v1/orchestrator.proto`:
1. Run `buf generate protos/`
2. Go stubs regenerate to `internal/gen/`
3. Python stubs regenerate to `agents/gen/`
4. Commit generated code alongside proto changes