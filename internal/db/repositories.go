package db

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// Conversation represents a stored user interaction.
type Conversation struct {
	ID        string
	SessionID string
	AgentID   string
	Query     string
	Response  string
	LatencyMs int64
	ExpiresAt *time.Time
	CreatedAt time.Time
}

// ConversationRepo handles CRUD operations for conversations.
type ConversationRepo struct {
	pool *pgxpool.Pool
}

// Store inserts a new conversation record.
func (r *ConversationRepo) Store(ctx context.Context, c *Conversation) error {
	_, err := r.pool.Exec(ctx,
		`INSERT INTO conversations (id, session_id, agent_id, query, response, latency_ms, expires_at)
		 VALUES ($1, $2, $3, $4, $5, $6, $7)`,
		c.ID, c.SessionID, c.AgentID, c.Query, c.Response, c.LatencyMs, c.ExpiresAt,
	)
	if err != nil {
		return fmt.Errorf("conversations.Store: %w", err)
	}
	return nil
}

// GetBySession retrieves recent conversations for a session.
func (r *ConversationRepo) GetBySession(ctx context.Context, sessionID string, limit int) ([]Conversation, error) {
	rows, err := r.pool.Query(ctx,
		`SELECT id, session_id, agent_id, query, response, latency_ms, expires_at, created_at
		 FROM conversations
		 WHERE session_id = $1 AND deleted_at IS NULL
		 ORDER BY created_at DESC
		 LIMIT $2`,
		sessionID, limit,
	)
	if err != nil {
		return nil, fmt.Errorf("conversations.GetBySession: %w", err)
	}
	defer rows.Close()

	var convos []Conversation
	for rows.Next() {
		var c Conversation
		if err := rows.Scan(&c.ID, &c.SessionID, &c.AgentID, &c.Query, &c.Response, &c.LatencyMs, &c.ExpiresAt, &c.CreatedAt); err != nil {
			return nil, fmt.Errorf("conversations.GetBySession scan: %w", err)
		}
		convos = append(convos, c)
	}
	return convos, rows.Err()
}

// GetByAgent retrieves recent conversations for an agent.
func (r *ConversationRepo) GetByAgent(ctx context.Context, agentID string, limit int) ([]Conversation, error) {
	rows, err := r.pool.Query(ctx,
		`SELECT id, session_id, agent_id, query, response, latency_ms, expires_at, created_at
		 FROM conversations
		 WHERE agent_id = $1 AND deleted_at IS NULL
		 ORDER BY created_at DESC
		 LIMIT $2`,
		agentID, limit,
	)
	if err != nil {
		return nil, fmt.Errorf("conversations.GetByAgent: %w", err)
	}
	defer rows.Close()

	var convos []Conversation
	for rows.Next() {
		var c Conversation
		if err := rows.Scan(&c.ID, &c.SessionID, &c.AgentID, &c.Query, &c.Response, &c.LatencyMs, &c.ExpiresAt, &c.CreatedAt); err != nil {
			return nil, fmt.Errorf("conversations.GetByAgent scan: %w", err)
		}
		convos = append(convos, c)
	}
	return convos, rows.Err()
}

// ToolCall represents a stored tool execution record.
type ToolCall struct {
	ID             string
	ConversationID string
	ToolName       string
	Params         map[string]any
	Result         map[string]any
	Error          string
	Success        bool
	LatencyMs      int32
	CreatedAt      time.Time
}

// ToolCallRepo handles CRUD operations for tool calls.
type ToolCallRepo struct {
	pool *pgxpool.Pool
}

// Store inserts a new tool call record.
func (r *ToolCallRepo) Store(ctx context.Context, tc *ToolCall) error {
	paramsJSON, err := json.Marshal(tc.Params)
	if err != nil {
		return fmt.Errorf("toolcalls.Store marshal params: %w", err)
	}
	resultJSON, err := json.Marshal(tc.Result)
	if err != nil {
		return fmt.Errorf("toolcalls.Store marshal result: %w", err)
	}

	_, err = r.pool.Exec(ctx,
		`INSERT INTO tool_calls (id, conversation_id, tool_name, params, result, error, success, latency_ms)
		 VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8)`,
		tc.ID, tc.ConversationID, tc.ToolName, paramsJSON, resultJSON, tc.Error, tc.Success, tc.LatencyMs,
	)
	if err != nil {
		return fmt.Errorf("toolcalls.Store: %w", err)
	}
	return nil
}

// GetByConversation retrieves tool calls for a conversation.
func (r *ToolCallRepo) GetByConversation(ctx context.Context, conversationID string) ([]ToolCall, error) {
	rows, err := r.pool.Query(ctx,
		`SELECT id, conversation_id, tool_name, params, result, error, success, latency_ms, created_at
		 FROM tool_calls
		 WHERE conversation_id = $1
		 ORDER BY created_at ASC`,
		conversationID,
	)
	if err != nil {
		return nil, fmt.Errorf("toolcalls.GetByConversation: %w", err)
	}
	defer rows.Close()

	var calls []ToolCall
	for rows.Next() {
		var tc ToolCall
		var paramsJSON, resultJSON []byte
		if err := rows.Scan(&tc.ID, &tc.ConversationID, &tc.ToolName, &paramsJSON, &resultJSON, &tc.Error, &tc.Success, &tc.LatencyMs, &tc.CreatedAt); err != nil {
			return nil, fmt.Errorf("toolcalls.GetByConversation scan: %w", err)
		}
		_ = json.Unmarshal(paramsJSON, &tc.Params)
		_ = json.Unmarshal(resultJSON, &tc.Result)
		calls = append(calls, tc)
	}
	return calls, rows.Err()
}

// EvalResult represents a stored evaluation result.
type EvalResult struct {
	ID        string
	EvalType  string
	AgentID   string
	Input     string
	Expected  string
	Actual    string
	Score     float32
	Metadata  map[string]any
	CreatedAt time.Time
}

// EvalResultRepo handles CRUD operations for evaluation results.
type EvalResultRepo struct {
	pool *pgxpool.Pool
}

// Store inserts a new evaluation result.
func (r *EvalResultRepo) Store(ctx context.Context, e *EvalResult) error {
	metaJSON, err := json.Marshal(e.Metadata)
	if err != nil {
		return fmt.Errorf("evalresults.Store marshal metadata: %w", err)
	}

	_, err = r.pool.Exec(ctx,
		`INSERT INTO eval_results (id, eval_type, agent_id, input, expected, actual, score, metadata)
		 VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)`,
		e.ID, e.EvalType, e.AgentID, e.Input, e.Expected, e.Actual, e.Score, metaJSON,
	)
	if err != nil {
		return fmt.Errorf("evalresults.Store: %w", err)
	}
	return nil
}

// GetByAgent retrieves recent eval results for an agent.
func (r *EvalResultRepo) GetByAgent(ctx context.Context, agentID string, limit int) ([]EvalResult, error) {
	rows, err := r.pool.Query(ctx,
		`SELECT id, eval_type, agent_id, input, expected, actual, score, metadata, created_at
		 FROM eval_results
		 WHERE agent_id = $1
		 ORDER BY created_at DESC
		 LIMIT $2`,
		agentID, limit,
	)
	if err != nil {
		return nil, fmt.Errorf("evalresults.GetByAgent: %w", err)
	}
	defer rows.Close()

	var results []EvalResult
	for rows.Next() {
		var e EvalResult
		var metaJSON []byte
		if err := rows.Scan(&e.ID, &e.EvalType, &e.AgentID, &e.Input, &e.Expected, &e.Actual, &e.Score, &metaJSON, &e.CreatedAt); err != nil {
			return nil, fmt.Errorf("evalresults.GetByAgent scan: %w", err)
		}
		_ = json.Unmarshal(metaJSON, &e.Metadata)
		results = append(results, e)
	}
	return results, rows.Err()
}

// GetByType retrieves recent eval results by type.
func (r *EvalResultRepo) GetByType(ctx context.Context, evalType string, limit int) ([]EvalResult, error) {
	rows, err := r.pool.Query(ctx,
		`SELECT id, eval_type, agent_id, input, expected, actual, score, metadata, created_at
		 FROM eval_results
		 WHERE eval_type = $1
		 ORDER BY created_at DESC
		 LIMIT $2`,
		evalType, limit,
	)
	if err != nil {
		return nil, fmt.Errorf("evalresults.GetByType: %w", err)
	}
	defer rows.Close()

	var results []EvalResult
	for rows.Next() {
		var e EvalResult
		var metaJSON []byte
		if err := rows.Scan(&e.ID, &e.EvalType, &e.AgentID, &e.Input, &e.Expected, &e.Actual, &e.Score, &metaJSON, &e.CreatedAt); err != nil {
			return nil, fmt.Errorf("evalresults.GetByType scan: %w", err)
		}
		_ = json.Unmarshal(metaJSON, &e.Metadata)
		results = append(results, e)
	}
	return results, rows.Err()
}

// AverageScore returns the average eval score for an agent and eval type.
func (r *EvalResultRepo) AverageScore(ctx context.Context, agentID, evalType string) (float32, error) {
	var avg *float32
	err := r.pool.QueryRow(ctx,
		`SELECT AVG(score) FROM eval_results WHERE agent_id = $1 AND eval_type = $2`,
		agentID, evalType,
	).Scan(&avg)
	if err != nil {
		return 0, fmt.Errorf("evalresults.AverageScore: %w", err)
	}
	if avg == nil {
		return 0, nil
	}
	return *avg, nil
}
