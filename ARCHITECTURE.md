# System Architecture

## High-Level Flow

User
  ↓
Go CLI
  ↓
Go Orchestrator
  ↓
Intent Router
  ↓
Python Agent Runtime
  ↓
Tool Execution
  ↓
PgVector Memory
  ↓
Response Aggregation
  ↓
CLI Output

---

## Communication

Preferred:
- gRPC between Go and Python

Alternative:
- REST

---

## Observability

### Go
OpenTelemetry exporter:
- Jaeger
- OTLP

### Python
LangSmith:
- traces
- spans
- evaluations

---

## Memory

PgVector stores:
- embeddings
- conversation history
- agent memory
- retrieval context

---

## Agent Runtime

Each agent:
- owns tools
- owns prompts
- owns evals
- remains independently deployable

# MCP Architecture

## Tool Execution Flow

Agent
  ↓
Tool Interface
  ↓
MCP Adapter
  ↓
MCP Server
  ↓
External Service

---

## MCP Responsibilities

Adapters handle:
- request translation
- retries
- authentication
- telemetry
- response normalization
- error mapping

Agents handle:
- reasoning
- tool selection
- planning
- reflection