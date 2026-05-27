package grpcutil

import (
	"context"
	"log/slog"
	"time"

	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"go.opentelemetry.io/otel/trace"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// ServerOptions returns gRPC server options with tracing, logging, and recovery interceptors.
func ServerOptions() []grpc.ServerOption {
	return []grpc.ServerOption{
		grpc.StatsHandler(otelgrpc.NewServerHandler()),
		grpc.ChainUnaryInterceptor(
			loggingUnaryInterceptor,
			recoveryUnaryInterceptor,
		),
		grpc.ChainStreamInterceptor(
			loggingStreamInterceptor,
		),
	}
}

func loggingUnaryInterceptor(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
	start := time.Now()

	spanCtx := trace.SpanContextFromContext(ctx)
	logger := slog.With(
		"method", info.FullMethod,
		"trace_id", spanCtx.TraceID().String(),
		"span_id", spanCtx.SpanID().String(),
	)

	resp, err := handler(ctx, req)
	duration := time.Since(start)

	if err != nil {
		logger.ErrorContext(ctx, "rpc failed", "error", err, "duration_ms", duration.Milliseconds())
	} else {
		logger.InfoContext(ctx, "rpc completed", "duration_ms", duration.Milliseconds())
	}

	return resp, err
}

func recoveryUnaryInterceptor(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (resp any, err error) {
	defer func() {
		if r := recover(); r != nil {
			slog.ErrorContext(ctx, "panic recovered", "method", info.FullMethod, "panic", r)
			err = status.Errorf(codes.Internal, "internal error")
		}
	}()
	return handler(ctx, req)
}

func loggingStreamInterceptor(srv any, ss grpc.ServerStream, info *grpc.StreamServerInfo, handler grpc.StreamHandler) error {
	start := time.Now()

	spanCtx := trace.SpanContextFromContext(ss.Context())
	logger := slog.With(
		"method", info.FullMethod,
		"trace_id", spanCtx.TraceID().String(),
		"span_id", spanCtx.SpanID().String(),
	)

	err := handler(srv, ss)
	duration := time.Since(start)

	if err != nil {
		logger.ErrorContext(ss.Context(), "stream failed", "error", err, "duration_ms", duration.Milliseconds())
	} else {
		logger.InfoContext(ss.Context(), "stream completed", "duration_ms", duration.Milliseconds())
	}

	return err
}
