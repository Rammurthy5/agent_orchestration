package main

import (
	"context"
	"fmt"
	"log/slog"
	"net"
	"os"
	"os/signal"
	"syscall"

	"github.com/rsi03/agent-orchestration/internal/config"
	"github.com/rsi03/agent-orchestration/internal/orchestrator"
	"github.com/rsi03/agent-orchestration/internal/router"
	"github.com/rsi03/agent-orchestration/internal/telemetry"
	"github.com/rsi03/agent-orchestration/pkg/grpcutil"
	"google.golang.org/grpc"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	cfg, err := config.Load()
	if err != nil {
		slog.Error("failed to load config", "error", err)
		os.Exit(1)
	}

	shutdown, err := telemetry.Init(ctx, cfg.Telemetry)
	if err != nil {
		slog.Error("failed to init telemetry", "error", err)
		os.Exit(1)
	}
	defer func() {
		if err := shutdown(context.Background()); err != nil {
			slog.Error("telemetry shutdown error", "error", err)
		}
	}()

	r := router.New()
	orch := orchestrator.New(r, cfg)

	srv := grpc.NewServer(grpcutil.ServerOptions()...)
	orch.Register(srv)

	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", cfg.Port))
	if err != nil {
		slog.Error("failed to listen", "error", err, "port", cfg.Port)
		os.Exit(1)
	}

	go func() {
		slog.Info("orchestrator started", "port", cfg.Port)
		if err := srv.Serve(lis); err != nil {
			slog.Error("server error", "error", err)
		}
	}()

	<-ctx.Done()
	slog.Info("shutting down gracefully")
	srv.GracefulStop()
}
