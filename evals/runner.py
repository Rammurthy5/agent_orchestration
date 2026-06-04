"""Evaluation runner — orchestrates eval execution and persists results.

Provides fixtures and utilities for running evals with result persistence
to the eval_results table.
"""

from __future__ import annotations

import os
import time
from typing import Any

from pydantic import BaseModel, Field

from agents.base.repository import EvalRecord


class EvalCase(BaseModel):
    """A single evaluation test case."""

    eval_type: str
    agent_id: str
    input: str
    expected: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvalResult(BaseModel):
    """Result of running an eval case."""

    case: EvalCase
    actual: str
    score: float
    passed: bool
    latency_ms: int
    details: dict[str, Any] = Field(default_factory=dict)

    def to_record(self) -> EvalRecord:
        """Convert to a persistable EvalRecord."""
        return EvalRecord(
            eval_type=self.case.eval_type,
            agent_id=self.case.agent_id,
            input=self.case.input,
            expected=self.case.expected,
            actual=self.actual,
            score=self.score,
            metadata={
                "passed": self.passed,
                "latency_ms": self.latency_ms,
                **self.details,
            },
        )


class EvalSuite:
    """Collection of eval cases with execution and scoring logic.

    Usage:
        suite = EvalSuite(eval_type="hallucination", agent_id="flights")
        suite.add_case(input="...", expected="grounded")
        results = await suite.run(scorer_fn)
    """

    def __init__(self, eval_type: str, agent_id: str):
        self.eval_type = eval_type
        self.agent_id = agent_id
        self.cases: list[EvalCase] = []
        self.results: list[EvalResult] = []

    def add_case(self, input: str, expected: str | None = None, **metadata: Any) -> None:
        """Add an eval case to the suite."""
        self.cases.append(
            EvalCase(
                eval_type=self.eval_type,
                agent_id=self.agent_id,
                input=input,
                expected=expected,
                metadata=metadata,
            )
        )

    async def run(self, scorer, threshold: float = 0.7) -> list[EvalResult]:
        """Run all cases through the scorer function.

        Args:
            scorer: Async callable(EvalCase) -> tuple[str, float, dict]
                    Returns (actual_output, score, details)
            threshold: Score >= threshold means passed.

        Returns:
            List of EvalResult objects.
        """
        self.results = []
        for case in self.cases:
            start = time.perf_counter()
            actual, score, details = await scorer(case)
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            result = EvalResult(
                case=case,
                actual=actual,
                score=score,
                passed=score >= threshold,
                latency_ms=elapsed_ms,
                details=details,
            )
            self.results.append(result)
        return self.results

    @property
    def pass_rate(self) -> float:
        """Compute pass rate across all results."""
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.passed) / len(self.results)

    @property
    def average_score(self) -> float:
        """Compute average score across all results."""
        if not self.results:
            return 0.0
        return sum(r.score for r in self.results) / len(self.results)

    def summary(self) -> dict[str, Any]:
        """Return a summary of the eval run."""
        return {
            "eval_type": self.eval_type,
            "agent_id": self.agent_id,
            "total_cases": len(self.cases),
            "passed": sum(1 for r in self.results if r.passed),
            "failed": sum(1 for r in self.results if not r.passed),
            "pass_rate": self.pass_rate,
            "average_score": self.average_score,
        }
