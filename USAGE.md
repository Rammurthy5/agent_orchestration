# Usage

This guide covers local run flows, test commands, and quick integration checks.

## Run Services Locally

Start Python first, then Go orchestrator.

```bash
# Terminal 1
source .venv/bin/activate
python -m agents.server

# Terminal 2
./bin/orchestrator
```

## Run with Docker Compose

```bash
docker compose up --build -d
docker compose logs -f orchestrator
```

## Send Requests with grpcurl

```bash
# Flights query
grpcurl -plaintext -d '{
  "query": "Find flights from NYC to London",
  "session_id": "e2e-test-1"
}' localhost:50051 orchestrator.v1.OrchestratorService/RouteTask

# Stay query
grpcurl -plaintext -d '{
  "query": "Book a hotel in Tokyo for 3 nights",
  "session_id": "e2e-test-2"
}' localhost:50051 orchestrator.v1.OrchestratorService/RouteTask

# Marketplace query
grpcurl -plaintext -d '{
  "query": "Best price for noise-cancelling headphones",
  "session_id": "e2e-test-3"
}' localhost:50051 orchestrator.v1.OrchestratorService/RouteTask

# Twitter query
grpcurl -plaintext -d '{
  "query": "What is trending on Twitter right now?",
  "session_id": "e2e-test-4"
}' localhost:50051 orchestrator.v1.OrchestratorService/RouteTask
```

## Directly Call Python Agent Service

```bash
grpcurl -plaintext -d '{
  "agent_id": "flights",
  "query": "Cheapest flight to San Francisco",
  "session_id": "direct-test"
}' localhost:50052 orchestrator.v1.AgentService/Execute
```

## Run Tests

### Go

```bash
go test ./... -race -count=1
go test ./internal/orchestrator/ -race -count=1 -v
go test ./internal/orchestrator -run TestRouteTaskStream_PropagatesRecvError -count=1
```

### Python

```bash
source .venv/bin/activate
python -m pytest --cov agents/ tools/
python -m pytest evals/test_agent_scope.py -v
python -m pytest -k "out_of_scope" -v
```

### Evaluation Suites

```bash
source .venv/bin/activate
python -m evals.run_evals --mode deterministic
python -m evals.run_evals --mode judge
python -m evals.run_evals --mode all
```

## Outputs and Evaluation Artifacts

- Structured eval outputs are written under `evals/results/`.
- Optional DB persistence is available via `--persist` if `DATABASE_URL` is set.
