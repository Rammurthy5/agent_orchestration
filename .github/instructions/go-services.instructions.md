---
applyTo: "{cmd,internal,pkg}/**/*.go"
description: "Use when editing Go orchestrator code — enforces context propagation, OpenTelemetry, and error handling patterns"
---

# Go Service Guidelines

- First param is always `context.Context`
- Wrap errors with `fmt.Errorf("operation: %w", err)` — never discard errors
- Every gRPC handler starts an OpenTelemetry span: `ctx, span := tracer.Start(ctx, "handler.Name")`
- Use `slog` for structured logging with trace/span IDs
- Interfaces are defined by consumers, not implementers
- Tests are table-driven with `t.Run()` subtests
- Proto definitions live in `protos/` — regenerate with `buf generate protos/`
