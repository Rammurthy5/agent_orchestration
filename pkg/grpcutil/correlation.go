package grpcutil

import (
	"context"

	"github.com/google/uuid"
	"google.golang.org/grpc"
	"google.golang.org/grpc/metadata"
)

const correlationIDKey = "x-correlation-id"

// CorrelationIDUnaryInterceptor extracts or generates a correlation ID and injects it into context metadata.
func CorrelationIDUnaryInterceptor(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
	ctx = ensureCorrelationID(ctx)
	return handler(ctx, req)
}

// CorrelationIDStreamInterceptor extracts or generates a correlation ID for streaming RPCs.
func CorrelationIDStreamInterceptor(srv any, ss grpc.ServerStream, info *grpc.StreamServerInfo, handler grpc.StreamHandler) error {
	ctx := ensureCorrelationID(ss.Context())
	wrapped := &wrappedServerStream{ServerStream: ss, ctx: ctx}
	return handler(srv, wrapped)
}

// CorrelationIDFromContext extracts the correlation ID from context metadata.
func CorrelationIDFromContext(ctx context.Context) string {
	md, ok := metadata.FromIncomingContext(ctx)
	if !ok {
		return ""
	}
	vals := md.Get(correlationIDKey)
	if len(vals) == 0 {
		return ""
	}
	return vals[0]
}

// WithCorrelationID returns outgoing context metadata with the correlation ID set.
func WithCorrelationID(ctx context.Context, correlationID string) context.Context {
	return metadata.AppendToOutgoingContext(ctx, correlationIDKey, correlationID)
}

func ensureCorrelationID(ctx context.Context) context.Context {
	md, ok := metadata.FromIncomingContext(ctx)
	if !ok {
		md = metadata.New(nil)
	}

	vals := md.Get(correlationIDKey)
	var corrID string
	if len(vals) > 0 && vals[0] != "" {
		corrID = vals[0]
	} else {
		corrID = uuid.New().String()
		md = md.Copy()
		md.Set(correlationIDKey, corrID)
		ctx = metadata.NewIncomingContext(ctx, md)
	}

	// Also set on outgoing so downstream calls propagate the correlation ID
	ctx = metadata.AppendToOutgoingContext(ctx, correlationIDKey, corrID)
	return ctx
}

// wrappedServerStream overrides Context() to return the enriched context.
type wrappedServerStream struct {
	grpc.ServerStream
	ctx context.Context
}

func (w *wrappedServerStream) Context() context.Context {
	return w.ctx
}
