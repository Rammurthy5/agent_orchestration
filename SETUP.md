# Setup

This guide covers local setup for the multi-agent orchestration platform.

## Prerequisites

- Go 1.23+
- Python 3.11+
- PostgreSQL 15+ with pgvector extension
- [buf](https://buf.build/) for protobuf generation
- Docker (optional)

## 1. Clone and Build Go Orchestrator

```bash
git clone https://github.com/rsi03/agent-orchestration.git
cd agent-orchestration

go mod tidy
go build -o bin/orchestrator ./cmd/orchestrator
```

## 2. Setup Python Agent Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 3. Generate Python gRPC Stubs

```bash
python -m grpc_tools.protoc \
  -I protos \
  --python_out=agents/gen \
  --grpc_python_out=agents/gen \
  protos/orchestrator/v1/orchestrator.proto

sed -i '' 's/from orchestrator\.v1 import/from agents.gen.orchestrator.v1 import/' \
  agents/gen/orchestrator/v1/orchestrator_pb2_grpc.py
```

## 4. Generate Go Stubs

```bash
buf generate protos/
```

## 5. Configure Environment Variables

Most variables have defaults, but set at least `LLM_API_KEY` and ensure PostgreSQL is reachable.

### Core Service Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ORCHESTRATOR_PORT` | `50051` | Go orchestrator gRPC listen port |
| `AGENT_ENDPOINT` | `localhost:50052` | Python agent gRPC target |
| `AGENT_TIMEOUT_SECONDS` | `30` | Per-agent timeout |
| `AGENT_MAX_RETRIES` | `3` | Retry attempts for transient failures |
| `DATABASE_URL` | `postgresql://localhost:5432/orchestrator` | PostgreSQL connection |

### Telemetry Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_SERVICE_NAME` | `orchestrator` | OpenTelemetry service name |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `localhost:4317` | OTLP collector endpoint |

### LLM Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_API_BASE` | `https://api.openai.com/v1` | OpenAI-compatible base URL |
| `LLM_API_KEY` | empty | API key for model calls |
| `LLM_MODEL` | `gpt-5.4-mini` | Model used for agent reasoning |

### MCP Adapter Variables (Fallback)

MCP adapters first load config from `.vscode/mcp.json`, `.mcp.json`, or `_mcp.json`.

| Variable | Default | Used by |
|----------|---------|---------|
| `SCRAPE_BADGER_MCP_URL` | `https://mcp.scrapebadger.com/mcp` | Marketplace adapter |
| `SCRAPE_BADGER_API_KEY` | empty | Marketplace adapter |
| `TWITTER_MCP_URL` | `http://localhost:8101/mcp` | Twitter adapter fallback |
| `TWITTER_MCP_API_KEY` | empty | Twitter adapter fallback |
| `TWITTER_API_KEY` | empty | Twitter direct-search fallback |
| `TWITTER_API_SECRET_KEY` | empty | Twitter direct-search fallback |
| `TWITTER_ACCESS_TOKEN` | empty | Twitter direct-search fallback |
| `TWITTER_ACCESS_TOKEN_SECRET` | empty | Twitter direct-search fallback |

## 6. Optional Docker Compose Setup

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
```

Service endpoints:

- Orchestrator gRPC: `localhost:50051`
- Agent service gRPC: `localhost:50052`
- PostgreSQL: `localhost:5432`

To stop:

```bash
docker compose down
# or include volumes
docker compose down -v
```
