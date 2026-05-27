package retry

import (
	"context"
	"errors"
	"testing"
	"time"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestDo_Success(t *testing.T) {
	r := New(Policy{MaxAttempts: 3, InitialDelay: time.Millisecond})
	calls := 0

	err := r.Do(context.Background(), func(ctx context.Context) error {
		calls++
		return nil
	})

	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if calls != 1 {
		t.Errorf("expected 1 call, got %d", calls)
	}
}

func TestDo_RetryOnTransient(t *testing.T) {
	r := New(Policy{MaxAttempts: 3, InitialDelay: time.Millisecond, MaxDelay: 5 * time.Millisecond})
	calls := 0

	err := r.Do(context.Background(), func(ctx context.Context) error {
		calls++
		if calls < 3 {
			return status.Error(codes.Unavailable, "temporarily unavailable")
		}
		return nil
	})

	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if calls != 3 {
		t.Errorf("expected 3 calls, got %d", calls)
	}
}

func TestDo_NoRetryOnNonTransient(t *testing.T) {
	r := New(Policy{MaxAttempts: 3, InitialDelay: time.Millisecond})
	calls := 0

	err := r.Do(context.Background(), func(ctx context.Context) error {
		calls++
		return status.Error(codes.InvalidArgument, "bad request")
	})

	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if calls != 1 {
		t.Errorf("expected 1 call (no retry), got %d", calls)
	}
}

func TestDo_ExhaustsRetries(t *testing.T) {
	r := New(Policy{MaxAttempts: 3, InitialDelay: time.Millisecond, MaxDelay: 5 * time.Millisecond})
	calls := 0

	err := r.Do(context.Background(), func(ctx context.Context) error {
		calls++
		return status.Error(codes.Unavailable, "down")
	})

	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if calls != 3 {
		t.Errorf("expected 3 calls, got %d", calls)
	}
}

func TestDo_ContextCancelled(t *testing.T) {
	r := New(Policy{MaxAttempts: 5, InitialDelay: 50 * time.Millisecond})
	ctx, cancel := context.WithCancel(context.Background())
	calls := 0

	go func() {
		time.Sleep(10 * time.Millisecond)
		cancel()
	}()

	err := r.Do(ctx, func(ctx context.Context) error {
		calls++
		return status.Error(codes.Unavailable, "down")
	})

	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !errors.Is(err, context.Canceled) {
		t.Errorf("expected context.Canceled in error chain, got: %v", err)
	}
}

func TestDo_RetryableGRPCCodes(t *testing.T) {
	tests := []struct {
		name      string
		code      codes.Code
		retryable bool
	}{
		{"Unavailable", codes.Unavailable, true},
		{"DeadlineExceeded", codes.DeadlineExceeded, true},
		{"ResourceExhausted", codes.ResourceExhausted, true},
		{"InvalidArgument", codes.InvalidArgument, false},
		{"NotFound", codes.NotFound, false},
		{"PermissionDenied", codes.PermissionDenied, false},
		{"Internal", codes.Internal, false},
		{"Unimplemented", codes.Unimplemented, false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			r := New(Policy{MaxAttempts: 2, InitialDelay: time.Millisecond})
			calls := 0

			_ = r.Do(context.Background(), func(ctx context.Context) error {
				calls++
				return status.Error(tt.code, "error")
			})

			if tt.retryable && calls != 2 {
				t.Errorf("code %s should be retryable: expected 2 calls, got %d", tt.code, calls)
			}
			if !tt.retryable && calls != 1 {
				t.Errorf("code %s should NOT be retryable: expected 1 call, got %d", tt.code, calls)
			}
		})
	}
}

func TestNew_DefaultPolicy(t *testing.T) {
	r := New(Policy{})

	if r.policy.MaxAttempts != 3 {
		t.Errorf("default MaxAttempts = %d, want 3", r.policy.MaxAttempts)
	}
	if r.policy.InitialDelay != 100*time.Millisecond {
		t.Errorf("default InitialDelay = %v, want 100ms", r.policy.InitialDelay)
	}
	if r.policy.MaxDelay != 5*time.Second {
		t.Errorf("default MaxDelay = %v, want 5s", r.policy.MaxDelay)
	}
	if r.policy.Multiplier != 2.0 {
		t.Errorf("default Multiplier = %f, want 2.0", r.policy.Multiplier)
	}
}
