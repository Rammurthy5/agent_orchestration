package orchestrator

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/rsi03/agent-orchestration/internal/config"
	"github.com/rsi03/agent-orchestration/internal/retry"
	"github.com/rsi03/agent-orchestration/internal/router"
	"github.com/rsi03/agent-orchestration/internal/telemetry"
	"google.golang.org/grpc"
)

// Orchestrator routes tasks to agents and aggregates responses.
type Orchestrator struct {
	router  *router.Router
	cfg     *config.Config
	retrier *retry.Retrier
}

// New creates an Orchestrator with the given router and config.
func New(r *router.Router, cfg *config.Config) *Orchestrator {
	return &Orchestrator{
		router: r,
		cfg:    cfg,
		retrier: retry.New(retry.Policy{
			MaxAttempts:  cfg.Agents.MaxRetries,
			InitialDelay: 100 * time.Millisecond,
			MaxDelay:     5 * time.Second,
			Multiplier:   2.0,
		}),
	}
}

// Register registers gRPC services on the server.
func (o *Orchestrator) Register(srv *grpc.Server) {
	// TODO: Register OrchestratorService once proto stubs are generated.
	_ = srv
}

// Execute routes the query to the appropriate agent and returns the response.
func (o *Orchestrator) Execute(ctx context.Context, query string, sessionID string) (string, error) {
	ctx, span := telemetry.Tracer("orchestrator").Start(ctx, "orchestrator.Execute")
	defer span.End()

	agentID, err := o.router.Route(ctx, query)
	if err != nil {
		return "", fmt.Errorf("orchestrator.Execute: %w", err)
	}

	slog.InfoContext(ctx, "routed task", "agent", agentID, "session_id", sessionID)

	var result string
	err = o.retrier.Do(ctx, func(ctx context.Context) error {
		var callErr error
		result, callErr = o.callAgent(ctx, agentID, query, sessionID)
		return callErr
	})
	if err != nil {
		return "", fmt.Errorf("orchestrator.Execute agent=%s: %w", agentID, err)
	}

	return result, nil
}

func (o *Orchestrator) callAgent(ctx context.Context, agent router.AgentID, query string, sessionID string) (string, error) {
	ctx, span := telemetry.Tracer("orchestrator").Start(ctx, "orchestrator.callAgent")
	defer span.End()

	// TODO: Implement gRPC call to Python agent service once proto stubs are generated.
	_ = agent
	_ = query
	_ = sessionID
	return "", fmt.Errorf("agent call not implemented: awaiting proto generation")
}
