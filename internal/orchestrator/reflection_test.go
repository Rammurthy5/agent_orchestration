package orchestrator

import (
	"context"
	"fmt"
	"net"
	"testing"

	"github.com/rsi03/agent-orchestration/internal/config"
	pb "github.com/rsi03/agent-orchestration/internal/gen/orchestrator/v1"
	"github.com/rsi03/agent-orchestration/internal/router"
	"github.com/rsi03/agent-orchestration/internal/telemetry"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/reflection"
	rpb "google.golang.org/grpc/reflection/grpc_reflection_v1alpha"
)

func TestServerReflection(t *testing.T) {
	// Start a gRPC server with the orchestrator registered + reflection
	fake := &fakeAgentServer{}
	agentLis, err := net.Listen("tcp", "localhost:0")
	if err != nil {
		t.Fatalf("agent listen: %v", err)
	}
	agentSrv := grpc.NewServer()
	pb.RegisterAgentServiceServer(agentSrv, fake)
	go func() { _ = agentSrv.Serve(agentLis) }()
	t.Cleanup(agentSrv.GracefulStop)

	cfg := &config.Config{
		Port: 0,
		Telemetry: config.TelemetryConfig{
			ServiceName:  "test",
			OTLPEndpoint: "localhost:4317",
		},
		Agents: config.AgentsConfig{
			Endpoint:       agentLis.Addr().String(),
			TimeoutSeconds: 5,
			MaxRetries:     1,
		},
	}
	metrics, _ := telemetry.InitMetrics()
	r := router.New()
	orch := New(r, cfg, metrics, nil)

	// Create the orchestrator server WITH reflection (mimics cmd/orchestrator/main.go)
	orchSrv := grpc.NewServer()
	orch.Register(orchSrv)
	reflection.Register(orchSrv)

	orchLis, err := net.Listen("tcp", "localhost:0")
	if err != nil {
		t.Fatalf("orch listen: %v", err)
	}
	go func() { _ = orchSrv.Serve(orchLis) }()
	t.Cleanup(orchSrv.GracefulStop)

	// Connect a client and query the reflection API
	conn, err := grpc.NewClient(
		orchLis.Addr().String(),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer conn.Close()

	client := rpb.NewServerReflectionClient(conn)
	stream, err := client.ServerReflectionInfo(context.Background())
	if err != nil {
		t.Fatalf("reflection stream: %v", err)
	}

	// Request the list of services
	err = stream.Send(&rpb.ServerReflectionRequest{
		MessageRequest: &rpb.ServerReflectionRequest_ListServices{ListServices: ""},
	})
	if err != nil {
		t.Fatalf("send list services: %v", err)
	}

	resp, err := stream.Recv()
	if err != nil {
		t.Fatalf("recv: %v", err)
	}

	listResp := resp.GetListServicesResponse()
	if listResp == nil {
		t.Fatal("expected list services response, got nil")
	}

	found := false
	for _, svc := range listResp.GetService() {
		if svc.GetName() == "orchestrator.v1.OrchestratorService" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("OrchestratorService not found in reflection; got services: %v",
			fmt.Sprintf("%v", listResp.GetService()))
	}
}
