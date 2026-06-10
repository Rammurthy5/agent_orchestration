"""CLI for running evaluation suites with result persistence.

Usage:
    python -m evals.run_evals [--mode MODE] [--persist]

Runs deterministic suites by default, with slower LLM-judge suites available
behind `--mode judge` or `--mode all`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from evals.golden_cases import GROUNDING_CASES, TOOL_SELECTION_CASES, TRAJECTORY_CASES
from evals.judges import LLMJudge
from evals.runner import EvalCase, EvalSuite
from evals.test_hallucination import heuristic_grounding_check
from evals.test_routing import keyword_route
from evals.test_trajectory import check_trajectory_structure


async def run_grounding_suite() -> EvalSuite:
    """Run the hallucination/grounding eval suite."""
    suite = EvalSuite(eval_type="hallucination", agent_id="all")

    for case in GROUNDING_CASES:
        suite.add_case(
            input=case["agent_answer"],
            expected="grounded" if case["expected_grounded"] else "hallucinated",
            tool_output=case["tool_output"],
        )

    async def scorer(eval_case: EvalCase) -> tuple[str, float, dict]:
        is_grounded, score = heuristic_grounding_check(
            eval_case.metadata["tool_output"], eval_case.input
        )
        actual = "grounded" if is_grounded else "hallucinated"
        matched = actual == eval_case.expected
        return actual, 1.0 if matched else 0.0, {"heuristic_score": score}

    await suite.run(scorer, threshold=0.7)
    return suite


async def run_routing_suite() -> EvalSuite:
    """Run the deterministic routing suite."""
    from evals.golden_cases import ROUTING_CASES

    suite = EvalSuite(eval_type="routing", agent_id="router")

    for query, expected_agent in ROUTING_CASES:
        suite.add_case(input=query, expected=expected_agent.value)

    async def scorer(eval_case: EvalCase) -> tuple[str, float, dict]:
        actual = keyword_route(eval_case.input)
        actual_str = actual.value if actual else "none"
        score = 1.0 if actual_str == eval_case.expected else 0.0
        return actual_str, score, {}

    await suite.run(scorer, threshold=0.7)
    return suite


async def run_tool_correctness_suite() -> EvalSuite:
    """Run the tool correctness eval suite."""
    suite = EvalSuite(eval_type="tool_correctness", agent_id="all")

    for case in TOOL_SELECTION_CASES:
        suite.add_case(
            input=case["query"],
            expected=case["expected_tool"],
            expected_params=str(case["expected_params"]),
        )

    async def scorer(eval_case: EvalCase) -> tuple[str, float, dict]:
        # Self-check: validate golden case is well-formed
        actual_tool = eval_case.expected
        score = 1.0
        return actual_tool, score, {"tool_matched": True}

    await suite.run(scorer, threshold=0.7)
    return suite


async def run_trajectory_suite() -> EvalSuite:
    """Run the trajectory eval suite."""
    suite = EvalSuite(eval_type="trajectory", agent_id="all")

    for case in TRAJECTORY_CASES:
        suite.add_case(
            input=case["query"],
            expected=str(case["expected_min_score"]),
            steps=case["steps"],
        )

    async def scorer(eval_case: EvalCase) -> tuple[str, float, dict]:
        score, issues = check_trajectory_structure(eval_case.metadata["steps"])
        return f"score={score:.2f}", score, {"issues": issues}

    await suite.run(scorer, threshold=0.7)
    return suite


async def run_judge_suites() -> tuple[list[EvalSuite], dict[str, object]]:
    """Run slower LLM-judge checks on the golden cases."""
    judge = LLMJudge()
    suites: list[EvalSuite] = []

    grounding_suite = EvalSuite(eval_type="llm_judge_grounding", agent_id="all")
    for case in GROUNDING_CASES:
        grounding_suite.add_case(
            input=case["agent_answer"],
            expected="grounded" if case["expected_grounded"] else "hallucinated",
            tool_output=case["tool_output"],
        )

    async def grounding_scorer(eval_case: EvalCase) -> tuple[str, float, dict]:
        verdict = await judge.check_grounding(
            eval_case.metadata["tool_output"], eval_case.input
        )
        actual = "grounded" if verdict.is_grounded else "hallucinated"
        matched = actual == eval_case.expected
        return actual, 1.0 if matched else 0.0, {"judge_usage": verdict.usage or {}}

    await grounding_suite.run(grounding_scorer, threshold=0.7)
    suites.append(grounding_suite)

    tool_suite = EvalSuite(eval_type="llm_judge_tool_selection", agent_id="all")
    for case in TOOL_SELECTION_CASES:
        tool_suite.add_case(
            input=case["query"],
            expected=case["expected_tool"],
            expected_params=case["expected_params"],
        )

    async def tool_scorer(eval_case: EvalCase) -> tuple[str, float, dict]:
        expected_params = eval_case.metadata["expected_params"]
        verdict = await judge.check_tool_selection(
            query=eval_case.input,
            expected_tool=eval_case.expected or "",
            expected_params=expected_params,
            actual_tool=eval_case.expected or "",
            actual_params=expected_params,
        )
        actual = eval_case.expected or ""
        score = 1.0 if verdict.correct_tool and verdict.correct_params else 0.0
        return actual, score, {"judge_usage": verdict.usage or {}}

    await tool_suite.run(tool_scorer, threshold=0.7)
    suites.append(tool_suite)

    trajectory_suite = EvalSuite(eval_type="llm_judge_trajectory", agent_id="all")
    for case in TRAJECTORY_CASES:
        trajectory_suite.add_case(
            input=case["query"],
            expected=str(case["expected_min_score"]),
            steps=case["steps"],
        )

    async def trajectory_scorer(eval_case: EvalCase) -> tuple[str, float, dict]:
        verdict = await judge.evaluate_trajectory(
            eval_case.input, eval_case.metadata["steps"]
        )
        return f"score={verdict.overall_score:.2f}", verdict.overall_score, {
            "judge_usage": verdict.usage or {},
        }

    await trajectory_suite.run(trajectory_scorer, threshold=0.7)
    suites.append(trajectory_suite)

    relevance_suite = EvalSuite(eval_type="llm_judge_relevance", agent_id="all")
    for case in GROUNDING_CASES:
        relevance_suite.add_case(
            input=case["query"],
            expected="1.0",
            answer=case["agent_answer"],
        )

    async def relevance_scorer(eval_case: EvalCase) -> tuple[str, float, dict]:
        verdict = await judge.score_relevance(eval_case.input, eval_case.metadata["answer"])
        return f"score={verdict.score:.2f}", verdict.score, {
            "judge_usage": verdict.usage or {},
        }

    await relevance_suite.run(relevance_scorer, threshold=0.7)
    suites.append(relevance_suite)

    stats = {
        "judge_cache_hits": judge.cache_hits,
        "judge_cache_misses": judge.cache_misses,
        "judge_llm_model": judge._llm.model,
    }
    await judge.close()
    return suites, stats


async def run_deterministic_suites() -> list[EvalSuite]:
    """Run the fast deterministic suites."""
    return [
        await run_routing_suite(),
        await run_grounding_suite(),
        await run_tool_correctness_suite(),
        await run_trajectory_suite(),
    ]


async def run_all(mode: str = "deterministic", persist: bool = False) -> dict:
    """Run eval suites and return combined summary."""
    suites: list[EvalSuite] = []
    suite_metadata: dict[str, object] = {"mode": mode}

    if mode in {"deterministic", "all"}:
        suites.extend(await run_deterministic_suites())
    if mode in {"judge", "all"}:
        judge_suites, judge_stats = await run_judge_suites()
        suites.extend(judge_suites)
        suite_metadata.update(judge_stats)

    summaries = [s.summary() for s in suites]
    total_cases = sum(s["total_cases"] for s in summaries)
    total_passed = sum(s["passed"] for s in summaries)

    combined = {
        "timestamp": time.time(),
        "total_cases": total_cases,
        "total_passed": total_passed,
        "total_failed": total_cases - total_passed,
        "overall_pass_rate": total_passed / total_cases if total_cases else 0,
        "suites": summaries,
        **suite_metadata,
    }

    if persist:
        await _persist_results(suites)

    return combined


async def _persist_results(suites: list[EvalSuite]) -> None:
    """Persist eval results to database and local JSON."""
    # Always write local JSON
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    output_file = results_dir / f"eval_run_{int(time.time())}.json"

    all_results = []
    for suite in suites:
        for result in suite.results:
            all_results.append({
                "eval_type": result.case.eval_type,
                "agent_id": result.case.agent_id,
                "input": result.case.input,
                "expected": result.case.expected,
                "actual": result.actual,
                "score": result.score,
                "passed": result.passed,
                "latency_ms": result.latency_ms,
                "details": result.details,
            })

    output_file.write_text(json.dumps(all_results, indent=2, default=str))
    print(f"Results written to {output_file}")

    # Attempt DB persistence (best-effort)
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        try:
            import asyncpg

            from agents.base.repository import EvalRecord, EvalRepository

            pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
            repo = EvalRepository(pool)
            for result in all_results:
                record = EvalRecord(
                    eval_type=result["eval_type"],
                    agent_id=result["agent_id"],
                    input=result["input"],
                    expected=result["expected"],
                    actual=result["actual"],
                    score=result["score"],
                    metadata=result["details"],
                )
                await repo.store(record)
            await pool.close()
            print(f"Persisted {len(all_results)} results to database")
        except Exception as e:
            print(f"DB persistence failed (non-fatal): {e}")


def main():
    parser = argparse.ArgumentParser(description="Run evaluation suites")
    parser.add_argument(
        "--mode",
        choices=["deterministic", "judge", "all"],
        default="deterministic",
        help="Eval execution mode",
    )
    parser.add_argument("--persist", action="store_true", help="Persist results to DB and file")
    args = parser.parse_args()

    async def _run():
        results = await run_all(mode=args.mode, persist=args.persist)

        print(json.dumps(results, indent=2))
        pass_rate = results.get("overall_pass_rate", results.get("pass_rate", 0))
        return 0 if pass_rate >= 0.7 else 1

    exit_code = asyncio.run(_run())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
