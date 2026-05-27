# Evaluation Strategy

## Routing Evals

Input:
"Find cheapest flights to Tokyo"

Expected:
Flights Agent selected

---

## Tool Correctness

Validate:
- correct tool selected
- correct parameters passed
- retries handled

---

## ReAct Trajectory Evals

Validate:
- reasoning quality
- action selection
- observation usage

---

## Hallucination Evals

Detect:
- fabricated APIs
- invented prices
- unsupported claims

---

## Latency Evals

Measure:
- orchestration latency
- agent latency
- tool latency

---

## Regression Suite

Every production bug becomes:
- a regression eval