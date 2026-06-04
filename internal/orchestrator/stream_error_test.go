package orchestrator

import (
	"context"
	"errors"
	"testing"

	"github.com/rsi03/agent-orchestration/internal/config"
	pb "github.com/rsi03/agent-orchestration/internal/gen/orchestrator/v1"
	"github.com/rsi03/agent-orchestration/internal/router"
	"google.golang.org/grpc"
	"google.golang.org/grpc/metadata"
)

type failingExecuteStream struct{}

func (f *failingExecuteStream) Recv() (*pb.ExecuteStreamResponse, error) {
	return nil, errStreamRecvFailed
}

func (f *failingExecuteStream) Header() (metadata.MD, error) { return nil, nil }
func (f *failingExecuteStream) Trailer() metadata.MD         { return nil }
func (f *failingExecuteStream) CloseSend() error             { return nil }
func (f *failingExecuteStream) Context() context.Context     { return context.Background() }
func (f *failingExecuteStream) SendMsg(any) error            { return nil }
func (f *failingExecuteStream) RecvMsg(any) error            { return nil }

type fakeStreamingAgentClient struct {
	stream grpc.ServerStreamingClient[pb.ExecuteStreamResponse]
}

func (f *fakeStreamingAgentClient) Execute(context.Context, *pb.ExecuteRequest, ...grpc.CallOption) (*pb.ExecuteResponse, error) {
	return nil, nil
}

func (f *fakeStreamingAgentClient) ExecuteStream(context.Context, *pb.ExecuteStreamRequest, ...grpc.CallOption) (grpc.ServerStreamingClient[pb.ExecuteStreamResponse], error) {
	return f.stream, nil
}

type recordingRouteTaskStream struct {
	sent []*pb.RouteTaskStreamResponse
}

var errStreamRecvFailed = errors.New("stream recv failed")

func (s *recordingRouteTaskStream) Send(resp *pb.RouteTaskStreamResponse) error {
	s.sent = append(s.sent, resp)
	return nil
}

func (s *recordingRouteTaskStream) SetHeader(metadata.MD) error  { return nil }
func (s *recordingRouteTaskStream) SendHeader(metadata.MD) error { return nil }
func (s *recordingRouteTaskStream) SetTrailer(metadata.MD)       {}
func (s *recordingRouteTaskStream) Context() context.Context     { return context.Background() }
func (s *recordingRouteTaskStream) SendMsg(any) error            { return nil }
func (s *recordingRouteTaskStream) RecvMsg(any) error            { return nil }

func TestRouteTaskStream_PropagatesRecvError(t *testing.T) {
	orch := &Orchestrator{
		router:      router.New(),
		cfg:         &config.Config{},
		agentClient: &fakeStreamingAgentClient{stream: &failingExecuteStream{}},
	}

	stream := &recordingRouteTaskStream{}
	err := orch.RouteTaskStream(&pb.RouteTaskStreamRequest{
		Query:     "Find flights to Tokyo",
		SessionId: "stream-test",
	}, stream)

	if err == nil {
		t.Fatal("expected stream recv error")
	}
	if !errors.Is(err, errStreamRecvFailed) {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(stream.sent) != 0 {
		t.Fatalf("expected no streamed responses, got %d", len(stream.sent))
	}
}
