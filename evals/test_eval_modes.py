"""Tests for deterministic vs judge eval execution modes."""

from __future__ import annotations

import pytest

from evals.runner import EvalSuite
from evals.run_evals import run_all


def _suite(eval_type: str) -> EvalSuite:
    suite = EvalSuite(eval_type=eval_type, agent_id="all")
    suite.add_case(input="test", expected="ok")

    async def scorer(case):
        return "ok", 1.0, {}

    return suite


@pytest.mark.asyncio
async def test_deterministic_mode_skips_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"deterministic": False, "judge": False}

    async def fake_deterministic():
        called["deterministic"] = True
        return [_suite("deterministic")]

    async def fake_judge():
        called["judge"] = True
        raise AssertionError("judge suites should not run in deterministic mode")

    monkeypatch.setattr("evals.run_evals.run_deterministic_suites", fake_deterministic)
    monkeypatch.setattr("evals.run_evals.run_judge_suites", fake_judge)

    result = await run_all(mode="deterministic", persist=False)

    assert called["deterministic"]
    assert not called["judge"]
    assert result["mode"] == "deterministic"


@pytest.mark.asyncio
async def test_judge_mode_skips_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"deterministic": False, "judge": False}

    async def fake_deterministic():
        called["deterministic"] = True
        raise AssertionError("deterministic suites should not run in judge mode")

    async def fake_judge():
        called["judge"] = True
        suite = _suite("judge")
        return [suite], {"judge_cache_hits": 0, "judge_cache_misses": 1, "judge_llm_model": "test"}

    monkeypatch.setattr("evals.run_evals.run_deterministic_suites", fake_deterministic)
    monkeypatch.setattr("evals.run_evals.run_judge_suites", fake_judge)

    result = await run_all(mode="judge", persist=False)

    assert not called["deterministic"]
    assert called["judge"]
    assert result["mode"] == "judge"
    assert result["judge_cache_misses"] == 1
