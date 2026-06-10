# Agent Orchestration

Multi-agent AI orchestration platform with a Go orchestrator and specialized Python agents (Flights, Stay, Marketplace, Twitter). The system routes natural language queries to the right agent, executes tool-backed reasoning, and returns grounded responses with telemetry.

## What This Repository Solves

- Routes heterogeneous user intents to specialized agents.
- Enforces an adapter boundary between reasoning agents and external data/tool providers.
- Tracks quality through deterministic and judge-based evaluation suites.
- Supports production-oriented observability, retry behavior, and persistence.

## Problem Definition and Evaluation Metrics

This project treats quality as measurable, not descriptive. Evaluation requirements are framed around three problem-definition dimensions:

### 1) Scoping Accuracy

Goal: the correct domain agent handles the request, and out-of-scope requests are refused or rerouted safely.

Primary metrics:

- Routing accuracy (% correct agent selection)
- Scope rejection correctness (% invalid domain queries rejected)
- False-accept rate (out-of-scope accepted as in-scope)

Relevant suites:

- Routing evals
- Agent scope evals

### 2) Clarity and Groundedness

Goal: outputs are useful, traceable to observations, and non-hallucinated.

Primary metrics:

- Hallucination rate / grounding pass rate
- Trajectory quality score (reasoning-action-observation coherence)
- Relevance/helpfulness score (judge-based)

Relevant suites:

- Hallucination evals
- ReAct trajectory evals
- LLM-judge relevance checks

### 3) Reliability and Performance

Goal: system remains dependable under retries, failures, and runtime budgets.

Primary metrics:

- Latency distribution (orchestration, agent, tool)
- MCP transport correctness and retry behavior
- Eval pass-rate threshold for CI gating

Relevant suites:

- Latency evals
- MCP transport evals
- End-to-end domain evals

For complete test strategy and categories, see [EVALS.md](EVALS.md).

## Offline Metrics Snapshot

The following metrics were computed from the local eval artifact [evals/results/eval_run_1780492600.json](evals/results/eval_run_1780492600.json) on 2026-06-10.

| Metric | Value |
|--------|-------|
| Total eval cases | 19 |
| Overall pass rate | 100% |
| Hallucination suite pass rate | 100% (8/8) |
| Hallucination average score | 1.00 |
| Tool correctness suite pass rate | 100% (8/8) |
| Tool correctness average score | 1.00 |
| Trajectory suite pass rate | 100% (3/3) |
| Trajectory average score | 0.978 |

### Snapshot Caveats

- This is an offline snapshot from one local run artifact, not a production trend.
- The artifact includes `latency_ms` values of `0`, so latency claims should not be inferred from this snapshot.
- Tool correctness in the current deterministic suite is a harness-level check and should be complemented with live/integration scoring for release decisions.

## Data Processing: Sources, PII, Guardrails

### Data Sources

- Flights via Kiwi and Skiplagged MCP providers
- Stay via Skiplagged and trivago MCP providers
- Marketplace via ScrapeBadger MCP
- Twitter via Twitter MCP transport
- Internal persistence via PostgreSQL + PgVector (conversations, memory, tool calls, eval records)

### PII and Sensitive Data Handling

- Deterministic redaction of common PII/secrets in request and response paths.
- Redaction applied before persistence in memory and repository layers.
- Structured payload redaction for nested metadata and tool outputs.

### Guardrails

- Query safety checks for prompt injection and secret-retention attempts.
- Out-of-scope refusal behavior per domain agent.
- MCP adapter boundary pattern for external tool access, with retries and validation.

## Documentation Map

- System architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
- Setup instructions: [SETUP.md](SETUP.md)
- Usage and runbook: [USAGE.md](USAGE.md)
- Evaluation strategy: [EVALS.md](EVALS.md)

## Project Structure

```text
cmd/               Go entrypoints
internal/          Go orchestrator/router/retry/telemetry/db
pkg/               Shared Go packages
agents/            Python agent runtime and domains
adapters/          MCP adapters (transport/auth/retries/normalization)
tools/             Tool contracts and models
evals/             Evaluation suites and runners
migrations/        PostgreSQL/PgVector schema
protos/            gRPC protobuf definitions
```

## Quick Start

1. Follow [SETUP.md](SETUP.md).
2. Start services and run commands from [USAGE.md](USAGE.md).
3. Run eval suites from [EVALS.md](EVALS.md).
