package db

// Package db provides PostgreSQL database access for the orchestrator.
//
// It implements a repository pattern with connection pooling via pgx.
import (
	"context"
	"fmt"
	"log/slog"

	"github.com/jackc/pgx/v5/pgxpool"
)

// DB holds the connection pool and provides access to repositories.
type DB struct {
	pool          *pgxpool.Pool
	Conversations *ConversationRepo
	EvalResults   *EvalResultRepo
	ToolCalls     *ToolCallRepo
}

// Config holds database connection settings.
type Config struct {
	DSN string // PostgreSQL connection string
}

// Connect creates a new DB instance with a connection pool.
func Connect(ctx context.Context, cfg Config) (*DB, error) {
	pool, err := pgxpool.New(ctx, cfg.DSN)
	if err != nil {
		return nil, fmt.Errorf("db.Connect: %w", err)
	}

	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("db.Connect ping: %w", err)
	}

	slog.InfoContext(ctx, "database connected", "dsn", maskDSN(cfg.DSN))

	return &DB{
		pool:          pool,
		Conversations: &ConversationRepo{pool: pool},
		EvalResults:   &EvalResultRepo{pool: pool},
		ToolCalls:     &ToolCallRepo{pool: pool},
	}, nil
}

// Close closes the connection pool.
func (db *DB) Close() {
	db.pool.Close()
}

// Pool returns the underlying connection pool for advanced usage.
func (db *DB) Pool() *pgxpool.Pool {
	return db.pool
}

// maskDSN redacts credentials from DSN for logging.
func maskDSN(dsn string) string {
	if len(dsn) > 30 {
		return dsn[:15] + "***" + dsn[len(dsn)-10:]
	}
	return "***"
}
