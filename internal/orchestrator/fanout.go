package orchestrator

import (
	"context"
	"fmt"
	"sync"

	pb "github.com/rsi03/agent-orchestration/internal/gen/orchestrator/v1"
	"github.com/rsi03/agent-orchestration/internal/telemetry"
	"golang.org/x/sync/errgroup"
)

// FanOutResult holds the response from a single agent in a multi-agent dispatch.
type FanOutResult struct {
	AgentID  string
	Response *pb.ExecuteResponse
	Err      error
}

// FanOut dispatches a query to multiple agents concurrently with per-agent timeouts.
// Each agent call gets its own child span; context cancellation propagates on parent cancel.
func (o *Orchestrator) FanOut(ctx context.Context, agentIDs []string, req *pb.RouteTaskRequest) []FanOutResult {
	ctx, span := telemetry.Tracer("orchestrator").Start(ctx, "orchestrator.FanOut")
	defer span.End()

	var mu sync.Mutex
	results := make([]FanOutResult, 0, len(agentIDs))

	g, ctx := errgroup.WithContext(ctx)
	for _, id := range agentIDs {
		agentID := id
		g.Go(func() error {
			resp, err := o.callAgent(ctx, agentID, req)
			mu.Lock()
			results = append(results, FanOutResult{
				AgentID:  agentID,
				Response: resp,
				Err:      err,
			})
			mu.Unlock()
			// Don't return err — we want all agents to run independently.
			// Only context cancellation (from parent) stops the group.
			if err != nil {
				return nil
			}
			return nil
		})
	}

	if err := g.Wait(); err != nil {
		// Only hits if context was cancelled externally.
		_ = fmt.Errorf("orchestrator.FanOut: %w", err)
	}

	return results
}
