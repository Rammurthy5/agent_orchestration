---
applyTo: "evals/**/*.py"
description: "Use when writing or editing evaluation tests — enforces pytest patterns, fixture usage, and eval categories"
---

# Eval Guidelines

- Tests live in `evals/` (not `tests/`) — pytest discovers via `testpaths = ["evals"]`
- Use `asyncio_mode = "auto"` — no need for `@pytest.mark.asyncio`
- Fixtures in `evals/conftest.py` provide `sample_requests` keyed by `AgentID`
- Parametrize with descriptive IDs: `@pytest.mark.parametrize("query,expected", CASES, ids=[...])`
- Integration tests use gRPC fixtures (server + stub) — see `test_server.py` for pattern
- Every production bug becomes a regression eval case
- Eval categories: routing, tool correctness, trajectory, hallucination, latency, scope rejection
- For LLM-as-judge evals, assert on score thresholds (not exact string matches)
- Latency evals measure orchestration, agent, and tool layers separately
