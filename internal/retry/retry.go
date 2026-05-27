package retry

import (
	"context"
	"fmt"
	"math"
	"math/rand/v2"
	"time"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// Policy defines the retry behavior.
type Policy struct {
	MaxAttempts  int
	InitialDelay time.Duration
	MaxDelay     time.Duration
	Multiplier   float64
}

// Retrier executes operations with exponential backoff and jitter.
type Retrier struct {
	policy Policy
}

// New creates a Retrier with the given policy.
func New(p Policy) *Retrier {
	if p.MaxAttempts <= 0 {
		p.MaxAttempts = 3
	}
	if p.InitialDelay <= 0 {
		p.InitialDelay = 100 * time.Millisecond
	}
	if p.MaxDelay <= 0 {
		p.MaxDelay = 5 * time.Second
	}
	if p.Multiplier <= 0 {
		p.Multiplier = 2.0
	}
	return &Retrier{policy: p}
}

// Do executes fn, retrying on transient gRPC errors with exponential backoff.
func (r *Retrier) Do(ctx context.Context, fn func(ctx context.Context) error) error {
	var lastErr error

	for attempt := range r.policy.MaxAttempts {
		lastErr = fn(ctx)
		if lastErr == nil {
			return nil
		}

		if !isRetryable(lastErr) {
			return lastErr
		}

		if attempt == r.policy.MaxAttempts-1 {
			break
		}

		delay := r.backoff(attempt)
		select {
		case <-ctx.Done():
			return fmt.Errorf("retry cancelled: %w", ctx.Err())
		case <-time.After(delay):
		}
	}

	return fmt.Errorf("max retries (%d) exceeded: %w", r.policy.MaxAttempts, lastErr)
}

func (r *Retrier) backoff(attempt int) time.Duration {
	delay := float64(r.policy.InitialDelay) * math.Pow(r.policy.Multiplier, float64(attempt))
	if delay > float64(r.policy.MaxDelay) {
		delay = float64(r.policy.MaxDelay)
	}
	// Add ±25% jitter
	jitter := delay * 0.25 * (2*rand.Float64() - 1)
	return time.Duration(delay + jitter)
}

func isRetryable(err error) bool {
	st, ok := status.FromError(err)
	if !ok {
		return false
	}
	switch st.Code() {
	case codes.Unavailable, codes.DeadlineExceeded, codes.ResourceExhausted:
		return true
	default:
		return false
	}
}
