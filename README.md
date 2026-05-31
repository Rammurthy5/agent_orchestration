# Agent Orchestration

Multi-agent AI orchestration platform. A Go CLI and orchestrator routes natural language tasks via gRPC to specialized Python AI agents (Flights, Marketplace, Stay, Twitter), backed by PostgreSQL/PgVector for memory.

## Prerequisites

- Go 1.23+
- Python 3.11+
- PostgreSQL 15+ with pgvector extension
- [buf](https://buf.build/) (for protobuf generation)
- Docker (optional, for local infra)

## Setup

### Go (Orchestrator)

```bash
# Clone
git clone https://github.com/rsi03/agent-orchestration.git
cd agent-orchestration

# Install Go dependencies
go mod tidy

# Build the orchestrator binary
go build -o bin/orchestrator ./cmd/orchestrator
```

### Python (Agents)

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the package in editable mode with dev dependencies
pip install -e ".[dev]"

# Generate Python gRPC stubs (requires grpcio-tools)
python -m grpc_tools.protoc \
  -I protos \
  --python_out=agents/gen \
  --grpc_python_out=agents/gen \
  protos/orchestrator/v1/orchestrator.proto

# Fix import paths in generated stubs
sed -i '' 's/from orchestrator\.v1 import/from agents.gen.orchestrator.v1 import/' \
  agents/gen/orchestrator/v1/orchestrator_pb2_grpc.py
```

### Protobuf (Go stubs)

```bash
# Requires buf CLI (https://buf.build/docs/installation)
buf generate protos/
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

## Usage

### Running Locally

Start the Python agent service first, then the Go orchestrator:

```bash
# Terminal 1 — Python agent service (port 50052)
source .venv/bin/activate
python -m agents.server

# Terminal 2 — Go orchestrator (port 50051)
./bin/orchestrator
```

The orchestrator accepts gRPC requests on `:50051` and forwards them to the agent service on `:50052`.

### Running Tests

#### Go

```bash
# Run all Go tests with race detection
go test ./... -race -count=1

# Verbose output
go test ./... -race -count=1 -v

# Run a specific package
go test ./internal/orchestrator/ -race -count=1 -v
```

#### Python

```bash
# Activate the virtual environment
source .venv/bin/activate

# Run all Python tests with coverage
pytest --cov agents/ tools/ evals/

# Run a specific test file
pytest evals/test_agent_scope.py -v

# Run tests matching a keyword
pytest -k "out_of_scope" -v
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
