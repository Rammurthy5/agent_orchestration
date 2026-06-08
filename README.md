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

### Environment Variables (Local Development)

Most variables are optional because defaults are provided. For real local runs, set at least `LLM_API_KEY` (for LLM calls) and ensure PostgreSQL is reachable via `DATABASE_URL`.

#### Core service variables

| Variable | Default | Required? | Used by | Description |
|----------|---------|-----------|---------|-------------|
| `ORCHESTRATOR_PORT` | `50051` | No | Go orchestrator | gRPC server listen port |
| `AGENT_ENDPOINT` | `localhost:50052` | No | Go orchestrator | Python agent gRPC target |
| `AGENT_TIMEOUT_SECONDS` | `30` | No | Go orchestrator | Per-agent call timeout |
| `AGENT_MAX_RETRIES` | `3` | No | Go orchestrator | Retry attempts for transient failures |
| `DATABASE_URL` | `postgresql://localhost:5432/orchestrator` | Usually | Go + Python | PostgreSQL connection string for memory, conversations, eval persistence |

#### Telemetry variables

| Variable | Default | Required? | Used by | Description |
|----------|---------|-----------|---------|-------------|
| `OTEL_SERVICE_NAME` | `orchestrator` | No | Go orchestrator | OpenTelemetry service name |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `localhost:4317` | No | Go orchestrator | OTLP collector endpoint |

#### LLM variables (Python agents)

| Variable | Default | Required? | Used by | Description |
|----------|---------|-----------|---------|-------------|
| `LLM_API_BASE` | `https://api.openai.com/v1` | No | Python agent service | OpenAI-compatible API base URL |
| `LLM_API_KEY` | empty | Yes (for real model calls) | Python agent service | API key for chat completions |
| `LLM_MODEL` | `gpt-5.4-mini` | No | Python agent service | Model name used for agent reasoning |

#### MCP adapter fallback variables

MCP adapters first read server config from `.vscode/mcp.json`. If a server entry is missing, these environment variables are used as fallback.

| Variable | Default | Used by |
|----------|---------|---------|
| `SCRAPE_BADGER_MCP_URL` | `https://mcp.scrapebadger.com/mcp` | Marketplace / ScrapeBadger adapter |
| `SCRAPE_BADGER_API_KEY` | empty | Marketplace / ScrapeBadger adapter |
| `TRAVEL_HACKING_MCP_URL` | `http://localhost:8100/mcp` | Flights + Stay adapter |
| `TRAVEL_HACKING_API_KEY` | empty | Flights + Stay adapter |
| `TWITTER_MCP_URL` | `http://localhost:8101/mcp` | Twitter adapter fallback for older HTTP setups |
| `TWITTER_MCP_API_KEY` | empty | Twitter adapter fallback for older HTTP setups |
| `TWITTER_API_KEY` | empty | Twitter adapter direct-search fallback |
| `TWITTER_API_SECRET_KEY` | empty | Twitter adapter direct-search fallback |
| `TWITTER_ACCESS_TOKEN` | empty | Twitter adapter direct-search fallback |
| `TWITTER_ACCESS_TOKEN_SECRET` | empty | Twitter adapter direct-search fallback |

The Twitter agent prefers the `twitter-mcp` stdio server defined in `.vscode/mcp.json`:

```json
{
  "command": "npx",
  "args": ["-y", "@enescinar/twitter-mcp"],
  "env": {
    "API_KEY": "...",
    "API_SECRET_KEY": "...",
    "ACCESS_TOKEN": "...",
    "ACCESS_TOKEN_SECRET": "..."
  }
}
```

The travel agents now mirror the toolkit-style split:

- Flights prefers `skiplagged`, then `kiwi`, then the legacy `travel-hacking` fallback.
- Stay prefers `airbnb`, then `trivago`, then the legacy `travel-hacking` fallback.
- Ferryhopper is available in the workspace config for future ferry-specific travel work.

Those toolkit servers can be configured directly in `.vscode/mcp.json` using the same pattern as the existing `travel-hacking` entry.

Example local exports:

```bash
export DATABASE_URL="postgresql://localhost:5432/orchestrator"
export LLM_API_KEY="<your-api-key>"
export LLM_MODEL="gpt-5.4-mini"

# Optional MCP fallback vars (if not using .vscode/mcp.json)
export SCRAPE_BADGER_API_KEY="<scrapebadger-key>"
export TWITTER_API_KEY="<twitter-api-key>"
export TWITTER_API_SECRET_KEY="<twitter-api-secret>"
export TWITTER_ACCESS_TOKEN="<twitter-access-token>"
export TWITTER_ACCESS_TOKEN_SECRET="<twitter-access-token-secret>"
```

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

### Running with Docker Compose

Use Docker Compose to run PostgreSQL (with pgvector), Python agents, and the Go orchestrator together.

Note: the agents image now includes Node.js so it can launch stdio MCP servers such as `airbnb` and `twitter-mcp`. Docker Compose still falls back to the Twitter OAuth credentials directly if the stdio server is unavailable, so the four `TWITTER_*` variables above need to be set in your environment or `.env` before `docker compose up`.
Docker Compose also mounts `.vscode/` into the agents container so the travel and marketplace agents can read the workspace MCP config at runtime.

```bash
# Copy example environment and set secrets (at least LLM_API_KEY)
cp .env.example .env

# Build and start all services
docker compose up --build -d

# Check service status
docker compose ps

# View logs (example: orchestrator)
docker compose logs -f orchestrator
```

Service endpoints:

- Orchestrator gRPC: `localhost:50051`
- Agent service gRPC: `localhost:50052`
- PostgreSQL: `localhost:5432`

Stop and clean up:

```bash
docker compose down

# Remove volumes too (deletes local postgres data)
docker compose down -v
```

### Building Images Directly

```bash
# Go orchestrator image
docker build -f Dockerfile.orchestrator -t agent-orchestration-orchestrator:local .

# Python agent image
docker build -f Dockerfile.agents -t agent-orchestration-agents:local .
```

### Running Tests

#### Go

```bash
# Run all Go tests with race detection
go test ./... -race -count=1

# Verbose output
go test ./... -race -count=1 -v

# Run a specific package
go test ./internal/orchestrator/ -race -count=1 -v

# Run a single test
go test ./internal/orchestrator -run TestRouteTaskStream_PropagatesRecvError -count=1
```

#### Python

```bash
# Activate the virtual environment
source .venv/bin/activate

# Run all Python package tests with coverage
python -m pytest --cov agents/ tools/

# Run a specific test file
python -m pytest evals/test_agent_scope.py -v

# Run tests matching a keyword
python -m pytest -k "out_of_scope" -v
```

#### Evals

```bash
# Keep the virtual environment active
source .venv/bin/activate

# Run the evaluation suite
python -m pytest evals/ -v

# Run a specific eval file
python -m pytest evals/test_marketplace_e2e.py -v

# Run one eval by name
python -m pytest evals/test_routing.py -k "routing_eval_suite" -v
```

#### End-to-End

With both services running (see [Running Locally](#running-locally)), use `grpcurl` to send requests to the orchestrator:

```bash
# Install grpcurl (if not already installed)
brew install grpcurl   # macOS
# or: go install github.com/fullstorydev/grpcurl/cmd/grpcurl@latest

# Route a flights query
grpcurl -plaintext -d '{
  "query": "Find flights from NYC to London",
  "session_id": "e2e-test-1"
}' localhost:50051 orchestrator.v1.OrchestratorService/RouteTask

# Route a hotel query
grpcurl -plaintext -d '{
  "query": "Book a hotel in Tokyo for 3 nights",
  "session_id": "e2e-test-2"
}' localhost:50051 orchestrator.v1.OrchestratorService/RouteTask

# Route a marketplace query
grpcurl -plaintext -d '{
  "query": "Best price for noise-cancelling headphones",
  "session_id": "e2e-test-3"
}' localhost:50051 orchestrator.v1.OrchestratorService/RouteTask

# Route a twitter query
grpcurl -plaintext -d '{
  "query": "What is trending on Twitter right now?",
  "session_id": "e2e-test-4"
}' localhost:50051 orchestrator.v1.OrchestratorService/RouteTask

# Verify out-of-scope rejection (should return INVALID_ARGUMENT)
grpcurl -plaintext -d '{
  "query": "What is the meaning of life?",
  "session_id": "e2e-test-5"
}' localhost:50051 orchestrator.v1.OrchestratorService/RouteTask
```

You can also test the Python agent service directly:

```bash
# Call the agent service without the orchestrator
grpcurl -plaintext -d '{
  "agent_id": "flights",
  "query": "Cheapest flight to San Francisco",
  "session_id": "direct-test"
}' localhost:50052 orchestrator.v1.AgentService/Execute
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
