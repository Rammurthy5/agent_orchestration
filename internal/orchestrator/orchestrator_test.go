package orchestrator

import (
	"context"
	"net"
	"testing"
	"time"

	pb "github.com/rsi03/agent-orchestration/internal/gen/orchestrator/v1"
	"github.com/rsi03/agent-orchestration/internal/config"
	"github.com/rsi03/agent-orchestration/internal/router"
	"github.com/rsi03/agent-orchestration/internal/telemetry"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// fakeAgentServer implements AgentServiceServer for testing.
type fakeAgentServer struct {
	pb.UnimplementedAgentServiceServer
	response *pb.ExecuteResponse
	err      error
}

func (f *fakeAgentServer) Execute(ctx context.Context, req *pb.ExecuteRequest) (*pb.ExecuteResponse, error) {
	if f.err != nil {
		return nil, f.err
	}
	if f.response != nil {
		return f.response, nil
	}
	return &pb.ExecuteResponse{
		AgentId:   req.GetAgentId(),
		Answer:    "Mock answer for: " + req.GetQuery(),
		LatencyMs: 42,
	}, nil
}

func startFakeAgentServer(t *testing.T, srv *fakeAgentServer) string {
	t.Helper()
	lis, err := net.Listen("tcp", "localhost:0")
	if err != nil {
		t.Fatalf("failed to listen: %v", err)
	}
	s := grpc.NewServer()
	pb.RegisterAgentServiceServer(s, srv)
	go func() { _ = s.Serve(lis) }()
	t.Cleanup(s.GracefulStop)
	return lis.Addr().String()
}

func newTestOrchestrator(t *testing.T, agentAddr string) *Orchestrator {
	t.Helper()
	cfg := &config.Config{
		Port: 0,
		Telemetry: config.TelemetryConfig{
			ServiceName:  "test",
			OTLPEndpoint: "localhost:4317",
		},
		Agents: config.AgentsConfig{
			Endpoint:       agentAddr,
			TimeoutSeconds: 5,
			MaxRetries:     2,
		},
	}
	metrics, _ := telemetry.InitMetrics()
	r := router.New()
	orch := New(r, cfg, metrics)

	conn, err := grpc.NewClient(agentAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatalf("failed to connect: %v", err)
	}
	orch.agentClient = pb.NewAgentServiceClient(conn)
	return orch
}

func TestRouteTask_Success(t *testing.T) {
	fake := &fakeAgentServer{}
	addr := startFakeAgentServer(t, fake)
	orch := newTestOrchestrator(t, addr)

	tests := []struct {
		name    string
		query   string
		wantAgent string
	}{
		{"flights", "Find flights to Tokyo", "flights"},
		{"stay", "Book a hotel in Paris", "stay"},
		{"marketplace", "Best price for a laptop", "marketplace"},
		{"twitter", "Trending hashtags on Twitter", "twitter"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			resp, err := orch.RouteTask(context.Background(), &pb.RouteTaskRequest{
				Query:     tt.query,
				SessionId: "test-session",
			})
			if err != nil {
				t.Fatalf("RouteTask error: %v", err)
			}
			if resp.GetAgentId() != tt.wantAgent {
				t.Errorf("AgentId = %q, want %q", resp.GetAgentId(), tt.wantAgent)
			}
			if resp.GetAnswer() == "" {
				t.Error("expected non-empty answer")
			}
		})
	}
}

func TestRouteTask_UnknownQuery(t *testing.T) {
	fake := &fakeAgentServer{}
	addr := startFakeAgentServer(t, fake)
	orch := newTestOrchestrator(t, addr)

	_, err := orch.RouteTask(context.Background(), &pb.RouteTaskRequest{
		Query:     "What is the meaning of life?",
		SessionId: "test-session",
	})
	if err == nil {
		t.Fatal("expected error for unroutable query")
	}
}

func TestRouteTask_AgentError(t *testing.T) {
	fake := &fakeAgentServer{
		err: grpc.ErrServerStopped,
	}
	addr := startFakeAgentServer(t, fake)
	orch := newTestOrchestrator(t, addr)

	_, err := orch.RouteTask(context.Background(), &pb.RouteTaskRequest{
		Query:     "Find flights to London",
		SessionId: "test-session",
	})
	if err == nil {
		t.Fatal("expected error when agent fails")
	}
}

func TestRouteTask_Timeout(t *testing.T) {
	// Simulate a slow agent
	fake := &fakeAgentServer{}
	addr := startFakeAgentServer(t, fake)

	cfg := &config.Config{
		Port: 0,
		Telemetry: config.TelemetryConfig{
			ServiceName:  "test",
			OTLPEndpoint: "localhost:4317",
		},
		Agents: config.AgentsConfig{
			Endpoint:       addr,
			TimeoutSeconds: 5,
			MaxRetries:     1,
		},
	}
	r := router.New()
	metrics, _ := telemetry.InitMetrics()
	orch := New(r, cfg, metrics)
	conn, _ := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	orch.agentClient = pb.NewAgentServiceClient(conn)

	ctx, cancel := context.WithTimeout(context.Background(), 1*time.Millisecond)
	defer cancel()
	time.Sleep(5 * time.Millisecond) // Ensure context is already expired

	_, err := orch.RouteTask(ctx, &pb.RouteTaskRequest{
		Query:     "Find flights to Tokyo",
		SessionId: "test-session",
	})
	if err == nil {
		t.Fatal("expected timeout error")
	}
}

func TestRouteTask_ResponseMapping(t *testing.T) {
	fake := &fakeAgentServer{
		response: &pb.ExecuteResponse{
			AgentId:   "flights",
			Answer:    "Flight found: UA123 $450",
			LatencyMs: 150,
			Steps: []*pb.Step{
				{Thought: "Need to search flights", Action: "search_flights", Observation: "Found UA123"},
			},
			ToolCalls: []*pb.ToolCall{
				{ToolName: "search_flights", Result: "UA123 $450", LatencyMs: 100},
			},
		},
	}
	addr := startFakeAgentServer(t, fake)
	orch := newTestOrchestrator(t, addr)

	resp, err := orch.RouteTask(context.Background(), &pb.RouteTaskRequest{
		Query:     "Find flights to Tokyo",
		SessionId: "test-session",
	})
	if err != nil {
		t.Fatalf("RouteTask error: %v", err)
	}

	if resp.GetAnswer() != "Flight found: UA123 $450" {
		t.Errorf("Answer = %q, want %q", resp.GetAnswer(), "Flight found: UA123 $450")
	}
	if resp.GetLatencyMs() != 150 {
		t.Errorf("LatencyMs = %d, want 150", resp.GetLatencyMs())
	}
	if len(resp.GetReasoningTrace()) != 1 {
		t.Fatalf("expected 1 step, got %d", len(resp.GetReasoningTrace()))
	}
	if resp.GetReasoningTrace()[0].GetThought() != "Need to search flights" {
		t.Errorf("step thought = %q", resp.GetReasoningTrace()[0].GetThought())
	}
	if len(resp.GetToolCalls()) != 1 {
		t.Fatalf("expected 1 tool call, got %d", len(resp.GetToolCalls()))
	}
	if resp.GetToolCalls()[0].GetToolName() != "search_flights" {
		t.Errorf("tool name = %q", resp.GetToolCalls()[0].GetToolName())
	}
}
