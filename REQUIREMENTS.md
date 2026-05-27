# Multi-Agent AI Orchestrator

## Goal

Build a production-grade multi-agent orchestration system.

The system accepts natural language commands from users via a Go CLI.

The Go orchestrator routes tasks to specialized Python AI agents.

## Agents

### Flights Agent
Responsibilities:
- Search flights
- Compare routes
- Optimize cost/time

### Marketplace Agent
Responsibilities:
- Product search
- Price comparison
- Recommendation generation

### Stay Agent
Responsibilities:
- Hotel recommendations
- Availability lookup
- Budget optimization

### Twitter Agent
Responsibilities:
- Social trend analysis
- Tweet generation
- Sentiment extraction

## Architecture

- Go handles:
  - CLI
  - orchestration
  - routing
  - telemetry
  - concurrency
  - API gateway responsibilities

- Python handles:
  - agent reasoning
  - tool execution
  - ReAct workflows
  - memory
  - evaluation pipelines

## Observability

### Golang
- OpenTelemetry
- Structured logging
- Context propagation
- Trace IDs

### Python
- LangSmith tracing
- Agent spans
- Tool-level observability

## Database

Use PostgreSQL with PgVector.

Capabilities:
- vector embeddings
- semantic retrieval
- memory storage
- evaluation history

## Standards

### Golang
- Idiomatic Go
- Small interfaces
- Composition over inheritance
- Context-aware APIs
- Error wrapping
- Table-driven tests

### Python
- PEP-8
- Type hints everywhere
- Async-first architecture
- Dataclasses/Pydantic models
- Modular tools

## Agent Design Pattern

All agents MUST follow ReAct architecture:
- Thought
- Action
- Observation
- Final Answer

## Evaluation Requirements

Strong eval framework required:
- hallucination detection
- tool correctness
- routing correctness
- latency metrics
- answer quality scoring
- regression testing
- trajectory evaluation

## Non-Goals

- No UI initially
- No fine-tuning pipeline
- No distributed training

# MCP Integration Requirements

All external integrations MUST be accessed through MCP-compatible tool adapters.

Agents MUST NOT directly call external APIs.

## MCP Providers

### Flights + Stay
Provider:
- travel-hacking-toolkit

### Twitter
Provider:
- twitter-mcp-server

### Marketplace
Provider:
- ScrapeBadger MCP

## MCP Design Rules

- Tool interfaces must remain provider-agnostic
- MCP clients must support retries
- MCP calls must be observable
- MCP latency must be measured
- MCP failures must be recoverable
- All MCP responses must be validated