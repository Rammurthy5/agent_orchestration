package retry

import (
	"testing"
	"time"
)

func TestCircuitBreaker_StartsClosedAllows(t *testing.T) {
	cb := NewCircuitBreaker(CircuitBreakerConfig{FailureThreshold: 3, ResetTimeout: 50 * time.Millisecond})

	if err := cb.Allow(); err != nil {
		t.Fatalf("closed breaker should allow: %v", err)
	}
	if cb.State() != StateClosed {
		t.Fatalf("expected StateClosed, got %d", cb.State())
	}
}

func TestCircuitBreaker_OpensAfterThreshold(t *testing.T) {
	cb := NewCircuitBreaker(CircuitBreakerConfig{FailureThreshold: 3, ResetTimeout: 50 * time.Millisecond})

	cb.RecordFailure()
	cb.RecordFailure()
	if err := cb.Allow(); err != nil {
		t.Fatal("should still allow before threshold")
	}

	cb.RecordFailure() // hits threshold
	if cb.State() != StateOpen {
		t.Fatalf("expected StateOpen, got %d", cb.State())
	}
	if err := cb.Allow(); err != ErrCircuitOpen {
		t.Fatalf("expected ErrCircuitOpen, got: %v", err)
	}
}

func TestCircuitBreaker_HalfOpenAfterTimeout(t *testing.T) {
	cb := NewCircuitBreaker(CircuitBreakerConfig{FailureThreshold: 2, ResetTimeout: 20 * time.Millisecond})

	cb.RecordFailure()
	cb.RecordFailure()
	if cb.State() != StateOpen {
		t.Fatal("expected open")
	}

	time.Sleep(25 * time.Millisecond)

	if err := cb.Allow(); err != nil {
		t.Fatalf("should allow after reset timeout: %v", err)
	}
	if cb.State() != StateHalfOpen {
		t.Fatalf("expected StateHalfOpen, got %d", cb.State())
	}
}

func TestCircuitBreaker_SuccessResetsFromHalfOpen(t *testing.T) {
	cb := NewCircuitBreaker(CircuitBreakerConfig{FailureThreshold: 2, ResetTimeout: 10 * time.Millisecond})

	cb.RecordFailure()
	cb.RecordFailure()
	time.Sleep(15 * time.Millisecond)
	_ = cb.Allow() // transitions to half-open

	cb.RecordSuccess()
	if cb.State() != StateClosed {
		t.Fatalf("expected StateClosed after success, got %d", cb.State())
	}
	if err := cb.Allow(); err != nil {
		t.Fatalf("closed breaker should allow: %v", err)
	}
}

func TestCircuitBreaker_FailureInHalfOpenReopens(t *testing.T) {
	cb := NewCircuitBreaker(CircuitBreakerConfig{FailureThreshold: 1, ResetTimeout: 10 * time.Millisecond})

	cb.RecordFailure() // opens (threshold=1)
	time.Sleep(15 * time.Millisecond)
	_ = cb.Allow() // transitions to half-open

	cb.RecordFailure() // should reopen
	if cb.State() != StateOpen {
		t.Fatalf("expected StateOpen after half-open failure, got %d", cb.State())
	}
}

func TestCircuitBreakerRegistry_PerAgent(t *testing.T) {
	reg := NewCircuitBreakerRegistry(CircuitBreakerConfig{FailureThreshold: 2, ResetTimeout: 30 * time.Second})

	cbFlights := reg.Get("flights")
	cbStay := reg.Get("stay")

	cbFlights.RecordFailure()
	cbFlights.RecordFailure()

	if cbFlights.State() != StateOpen {
		t.Fatal("flights breaker should be open")
	}
	if cbStay.State() != StateClosed {
		t.Fatal("stay breaker should be closed (independent)")
	}

	// Same instance returned on subsequent calls
	if reg.Get("flights") != cbFlights {
		t.Fatal("expected same instance for same agent")
	}
}
