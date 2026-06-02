package telemetry

import (
	"context"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
)

// Metrics holds the OTel metric instruments for the orchestrator.
type Metrics struct {
	RequestCount   metric.Int64Counter
	RequestLatency metric.Float64Histogram
	ErrorCount     metric.Int64Counter
}

// InitMetrics creates and registers OTel metric instruments.
func InitMetrics() (*Metrics, error) {
	meter := otel.Meter("orchestrator")

	requestCount, err := meter.Int64Counter("orchestrator.requests.total",
		metric.WithDescription("Total number of requests per agent"),
		metric.WithUnit("{request}"),
	)
	if err != nil {
		return nil, err
	}

	requestLatency, err := meter.Float64Histogram("orchestrator.requests.duration",
		metric.WithDescription("Request latency distribution per agent"),
		metric.WithUnit("ms"),
		metric.WithExplicitBucketBoundaries(5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000),
	)
	if err != nil {
		return nil, err
	}

	errorCount, err := meter.Int64Counter("orchestrator.errors.total",
		metric.WithDescription("Total number of errors per agent"),
		metric.WithUnit("{error}"),
	)
	if err != nil {
		return nil, err
	}

	return &Metrics{
		RequestCount:   requestCount,
		RequestLatency: requestLatency,
		ErrorCount:     errorCount,
	}, nil
}

// RecordRequest records a completed request with agent attribution.
func (m *Metrics) RecordRequest(ctx context.Context, agentID string, duration time.Duration, err error) {
	attrs := metric.WithAttributes(attribute.String("agent_id", agentID))

	m.RequestCount.Add(ctx, 1, attrs)
	m.RequestLatency.Record(ctx, float64(duration.Milliseconds()), attrs)

	if err != nil {
		m.ErrorCount.Add(ctx, 1, attrs)
	}
}
