# Agent Orchestration

Multi-agent AI orchestration platform. A Go CLI and orchestrator routes natural language tasks via gRPC to specialized Python AI agents (Flights, Marketplace, Stay, Twitter), backed by PostgreSQL/PgVector for memory.

## Prerequisites

- Go 1.23+
- Python 3.11+
- PostgreSQL 15+ with pgvector extension
- [buf](https://buf.build/) (for protobuf generation)
- Docker (optional, for local infra)

## Setup

```bash
# Clone
git clone https://github.com/rsi03/agent-orchestration.git
cd agent-orchestration

# Install Go dependencies
go mod tidy

# Build the orchestrator
go build -o bin/orchestrator ./cmd/orchestrator
```

## Configuration

Set environment variables (or use defaults):

| Variable | Default | Description |
|----------|---------|-------------|
| `ORCHESTRATOR_PORT` | `50051` | gRPC server port |
| `OTEL_SERVICE_NAME` | `orchestrator` | OpenTelemetry service name |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `localhost:4317` | OTLP collector endpoint |
| `AGENT_ENDPOINT` | `localhost:50052` | Python agent gRPC address |
| `AGENT_TIMEOUT_SECONDS` | `30` | Per-agent call timeout |
| `AGENT_MAX_RETRIES` | `3` | Max retry attempts on transient failures |

## Running

```bash
# Start the orchestrator
./bin/orchestrator
```

The server listens on the configured port (default `:50051`) and accepts gRPC requests.

## Tests

```bash
# Run all tests with race detection
go test ./... -race -count=1

# Verbose output
go test ./... -race -count=1 -v
```

## Project Structure

```
cmd/orchestrator/       Go entrypoint (gRPC server + graceful shutdown)
internal/
  config/              Environment-based configuration
  orchestrator/        Task dispatch and response aggregation
  retry/               Exponential backoff with jitter + circuit breaker
  router/              Intent classification → agent routing
  telemetry/           OpenTelemetry provider setup (OTLP exporter)
pkg/grpcutil/          Shared gRPC interceptors (logging, tracing, recovery)
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system design and [REQUIREMENTS.md](REQUIREMENTS.md) for agent specifications.
