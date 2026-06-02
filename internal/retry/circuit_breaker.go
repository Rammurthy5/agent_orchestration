package retry

import (
	"errors"
	"sync"
	"time"
)

// CircuitState represents the state of the circuit breaker.
type CircuitState int

const (
	StateClosed   CircuitState = iota // Normal operation
	StateOpen                         // Rejecting requests
	StateHalfOpen                     // Allowing a single probe request
)

// ErrCircuitOpen is returned when the circuit breaker is open.
var ErrCircuitOpen = errors.New("circuit breaker is open")

// CircuitBreakerConfig holds circuit breaker settings.
type CircuitBreakerConfig struct {
	FailureThreshold int           // Consecutive failures to trip (default 5)
	ResetTimeout     time.Duration // Time in open state before half-open (default 30s)
}

// CircuitBreaker implements the circuit breaker pattern per agent.
type CircuitBreaker struct {
	mu               sync.Mutex
	state            CircuitState
	failures         int
	lastFailure      time.Time
	failureThreshold int
	resetTimeout     time.Duration
}

// NewCircuitBreaker creates a CircuitBreaker with the given config.
func NewCircuitBreaker(cfg CircuitBreakerConfig) *CircuitBreaker {
	if cfg.FailureThreshold <= 0 {
		cfg.FailureThreshold = 5
	}
	if cfg.ResetTimeout <= 0 {
		cfg.ResetTimeout = 30 * time.Second
	}
	return &CircuitBreaker{
		state:            StateClosed,
		failureThreshold: cfg.FailureThreshold,
		resetTimeout:     cfg.ResetTimeout,
	}
}

// Allow checks whether a request should be permitted.
func (cb *CircuitBreaker) Allow() error {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	switch cb.state {
	case StateClosed:
		return nil
	case StateOpen:
		if time.Since(cb.lastFailure) >= cb.resetTimeout {
			cb.state = StateHalfOpen
			return nil
		}
		return ErrCircuitOpen
	case StateHalfOpen:
		return nil
	}
	return nil
}

// RecordSuccess records a successful call, resetting the breaker to closed.
func (cb *CircuitBreaker) RecordSuccess() {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	cb.failures = 0
	cb.state = StateClosed
}

// RecordFailure records a failed call. If failures exceed the threshold, the circuit opens.
func (cb *CircuitBreaker) RecordFailure() {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	cb.failures++
	cb.lastFailure = time.Now()

	if cb.failures >= cb.failureThreshold {
		cb.state = StateOpen
	}
}

// State returns the current circuit state.
func (cb *CircuitBreaker) State() CircuitState {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	return cb.state
}

// CircuitBreakerRegistry holds per-agent circuit breakers.
type CircuitBreakerRegistry struct {
	mu       sync.Mutex
	breakers map[string]*CircuitBreaker
	cfg      CircuitBreakerConfig
}

// NewCircuitBreakerRegistry creates a registry with shared config for all agents.
func NewCircuitBreakerRegistry(cfg CircuitBreakerConfig) *CircuitBreakerRegistry {
	return &CircuitBreakerRegistry{
		breakers: make(map[string]*CircuitBreaker),
		cfg:      cfg,
	}
}

// Get returns the circuit breaker for the given agent, creating one if needed.
func (r *CircuitBreakerRegistry) Get(agentID string) *CircuitBreaker {
	r.mu.Lock()
	defer r.mu.Unlock()

	if cb, ok := r.breakers[agentID]; ok {
		return cb
	}
	cb := NewCircuitBreaker(r.cfg)
	r.breakers[agentID] = cb
	return cb
}
