package db

import (
	"context"
	"testing"
	"time"
)

// TestConversation_Struct verifies Conversation fields.
func TestConversation_Struct(t *testing.T) {
	now := time.Now()
	expires := now.Add(24 * time.Hour)
	c := &Conversation{
		ID:        "test-id",
		SessionID: "session-1",
		AgentID:   "flights",
		Query:     "Find flights to Tokyo",
		Response:  "Found 3 flights",
		LatencyMs: 150,
		ExpiresAt: &expires,
		CreatedAt: now,
	}

	if c.ID != "test-id" {
		t.Errorf("unexpected ID: %s", c.ID)
	}
	if c.AgentID != "flights" {
		t.Errorf("unexpected AgentID: %s", c.AgentID)
	}
	if c.ExpiresAt == nil || c.ExpiresAt.IsZero() {
		t.Error("expected non-nil ExpiresAt")
	}
}

// TestToolCall_Struct verifies ToolCall fields.
func TestToolCall_Struct(t *testing.T) {
	tc := &ToolCall{
		ID:             "tc-1",
		ConversationID: "conv-1",
		ToolName:       "search_flights",
		Params:         map[string]any{"origin": "NYC", "dest": "TKY"},
		Result:         map[string]any{"flights": 3},
		Error:          "",
		Success:        true,
		LatencyMs:      42,
	}

	if tc.ToolName != "search_flights" {
		t.Errorf("unexpected ToolName: %s", tc.ToolName)
	}
	if !tc.Success {
		t.Error("expected success=true")
	}
}

// TestEvalResult_Struct verifies EvalResult fields.
func TestEvalResult_Struct(t *testing.T) {
	e := &EvalResult{
		ID:       "eval-1",
		EvalType: "hallucination",
		AgentID:  "flights",
		Input:    "Find flights to Mars",
		Expected: "out-of-scope",
		Actual:   "out-of-scope",
		Score:    1.0,
		Metadata: map[string]any{"model": "gpt-4"},
	}

	if e.Score != 1.0 {
		t.Errorf("unexpected score: %f", e.Score)
	}
	if e.EvalType != "hallucination" {
		t.Errorf("unexpected eval type: %s", e.EvalType)
	}
}

// TestMaskDSN verifies DSN masking for logs.
func TestMaskDSN(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  string
	}{
		{"short", "short", "***"},
		{"long", "postgresql://user:pass@localhost:5432/db", "postgresql://***:5432/db"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := maskDSN(tt.input)
			if tt.name == "short" && got != "***" {
				t.Errorf("maskDSN(%q) = %q, want %q", tt.input, got, tt.want)
			}
			if tt.name == "long" && len(got) < 10 {
				t.Errorf("maskDSN(%q) too short: %q", tt.input, got)
			}
		})
	}
}

// TestConfig_Struct verifies Config fields.
func TestConfig_Struct(t *testing.T) {
	cfg := Config{DSN: "postgresql://localhost:5432/orchestrator"}
	if cfg.DSN == "" {
		t.Error("expected non-empty DSN")
	}
}

// TestConnect_InvalidDSN verifies that Connect fails with a bad DSN.
func TestConnect_InvalidDSN(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	_, err := Connect(ctx, Config{DSN: "postgresql://invalid:5432/noexist"})
	if err == nil {
		t.Fatal("expected error for invalid DSN")
	}
}
