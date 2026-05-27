# Copilot Instructions

## Project Overview

Multi-agent AI orchestration platform: Go CLI + orchestrator routes tasks via gRPC to specialized Python AI agents (Flights, Marketplace, Stay, Twitter). See [ARCHITECTURE.md](../ARCHITECTURE.md) for system flow and [REQUIREMENTS.md](../REQUIREMENTS.md) for full agent specs.

## Project Structure

```
cmd/               # Go CLI entrypoints
internal/          # Go orchestrator, router, gRPC server
pkg/               # Reusable Go packages
agents/            # Python agent runtime
  flights/
  marketplace/
  stay/
  twitter/
  base/            # Base agent class, ReAct loop
tools/             # Python tool implementations
adapters/          # MCP adapters
protos/            # gRPC protobuf definitions
evals/             # Evaluation pipelines
migrations/        # PostgreSQL/PgVector schema
```

## Build & Test

```bash
# Go
go build ./cmd/...
go test ./... -race -count=1

# Python
pip install -e ".[dev]"
pytest --cov agents/ tools/

# Proto generation
buf generate protos/
```

## Code Style

### Go
- Idiomatic Go: `context.Context` first param, explicit error returns, error wrapping
- Interfaces at boundaries only, composition over inheritance
- Structured logging (slog), OpenTelemetry spans on every handler
- Table-driven tests, no global state

### Python
- PEP-8, type hints everywhere, async/await by default
- Pydantic models for all data structures
- Separate prompts from logic, keep tools isolated

## Agent Contract

Every agent MUST implement the ReAct pattern:
- `reasoning()` → `tool_selection()` → `execute()` → `reflect()` → `final_answer()`

## Observability

- **Go**: OpenTelemetry tracing + correlation IDs on all requests
- **Python**: LangSmith tracing on every reasoning step and tool invocation

## Database

PostgreSQL + PgVector. Never inline raw SQL if ORM/query builder exists.

## MCP Rules

- Never call MCP servers directly from agents — always use adapters
- Adapters handle: retries (exponential backoff), auth, telemetry, response normalization
- Validate all MCP payloads with Pydantic

## Evals

Every new capability requires: unit tests, integration tests, eval coverage, regression evals. See [EVALS.md](../EVALS.md) for strategy.