package orchestrator

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	pb "github.com/rsi03/agent-orchestration/internal/gen/orchestrator/v1"
	"github.com/rsi03/agent-orchestration/internal/config"
	"github.com/rsi03/agent-orchestration/internal/retry"
	"github.com/rsi03/agent-orchestration/internal/router"
	"github.com/rsi03/agent-orchestration/internal/telemetry"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// Orchestrator routes tasks to agents and aggregates responses.
type Orchestrator struct {
	pb.UnimplementedOrchestratorServiceServer
	router      *router.Router
	cfg         *config.Config
	retrier     *retry.Retrier
	agentClient pb.AgentServiceClient
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

// Connect establishes the gRPC connection to the Python agent service.
func (o *Orchestrator) Connect(ctx context.Context) error {
	ctx, span := telemetry.Tracer("orchestrator").Start(ctx, "orchestrator.Connect")
	defer span.End()

	conn, err := grpc.NewClient(
		o.cfg.Agents.Endpoint,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		return fmt.Errorf("orchestrator.Connect: %w", err)
	}

	o.agentClient = pb.NewAgentServiceClient(conn)
	slog.InfoContext(ctx, "connected to agent service", "endpoint", o.cfg.Agents.Endpoint)
	return nil
}

// Register registers the OrchestratorService on the gRPC server.
func (o *Orchestrator) Register(srv *grpc.Server) {
	pb.RegisterOrchestratorServiceServer(srv, o)
}

// RouteTask implements OrchestratorServiceServer.
func (o *Orchestrator) RouteTask(ctx context.Context, req *pb.RouteTaskRequest) (*pb.RouteTaskResponse, error) {
	ctx, span := telemetry.Tracer("orchestrator").Start(ctx, "orchestrator.RouteTask")
	defer span.End()

	agentID, err := o.router.Route(ctx, req.GetQuery())
	if err != nil {
		return nil, fmt.Errorf("orchestrator.RouteTask: %w", err)
	}

	slog.InfoContext(ctx, "routed task", "agent", agentID, "session_id", req.GetSessionId())

	var resp *pb.ExecuteResponse
	err = o.retrier.Do(ctx, func(ctx context.Context) error {
		var callErr error
		resp, callErr = o.callAgent(ctx, string(agentID), req)
		return callErr
	})
	if err != nil {
		return nil, fmt.Errorf("orchestrator.RouteTask agent=%s: %w", agentID, err)
	}

	return &pb.RouteTaskResponse{
		AgentId:        resp.GetAgentId(),
		Answer:         resp.GetAnswer(),
		ReasoningTrace: resp.GetSteps(),
		ToolCalls:      resp.GetToolCalls(),
		LatencyMs:      resp.GetLatencyMs(),
	}, nil
}

// RouteTaskStream implements OrchestratorServiceServer (streaming).
func (o *Orchestrator) RouteTaskStream(req *pb.RouteTaskStreamRequest, stream grpc.ServerStreamingServer[pb.RouteTaskStreamResponse]) error {
	ctx := stream.Context()
	ctx, span := telemetry.Tracer("orchestrator").Start(ctx, "orchestrator.RouteTaskStream")
	defer span.End()

	agentID, err := o.router.Route(ctx, req.GetQuery())
	if err != nil {
		return fmt.Errorf("orchestrator.RouteTaskStream: %w", err)
	}

	agentStream, err := o.agentClient.ExecuteStream(ctx, &pb.ExecuteStreamRequest{
		AgentId:   string(agentID),
		Query:     req.GetQuery(),
		SessionId: req.GetSessionId(),
		Metadata:  req.GetMetadata(),
	})
	if err != nil {
		return fmt.Errorf("orchestrator.RouteTaskStream agent=%s: %w", agentID, err)
	}

	for {
		event, err := agentStream.Recv()
		if err != nil {
			break
		}
		if sendErr := stream.Send(&pb.RouteTaskStreamResponse{
			EventType: event.GetEventType(),
			Payload:   event.GetPayload(),
			Timestamp: event.GetTimestamp(),
		}); sendErr != nil {
			return fmt.Errorf("orchestrator.RouteTaskStream send: %w", sendErr)
		}
	}

	return nil
}

func (o *Orchestrator) callAgent(ctx context.Context, agentID string, req *pb.RouteTaskRequest) (*pb.ExecuteResponse, error) {
	ctx, span := telemetry.Tracer("orchestrator").Start(ctx, "orchestrator.callAgent")
	defer span.End()

	deadline := time.Duration(o.cfg.Agents.TimeoutSeconds) * time.Second
	ctx, cancel := context.WithTimeout(ctx, deadline)
	defer cancel()

	resp, err := o.agentClient.Execute(ctx, &pb.ExecuteRequest{
		AgentId:   agentID,
		Query:     req.GetQuery(),
		SessionId: req.GetSessionId(),
		Metadata:  req.GetMetadata(),
	})
	if err != nil {
		return nil, fmt.Errorf("callAgent %s: %w", agentID, err)
	}

	return resp, nil
}

// Ensure timestamp import is used.
var _ = timestamppb.Now
