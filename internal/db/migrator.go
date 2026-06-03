package db

import (
	"context"
	"embed"
	"fmt"
	"log/slog"
	"sort"
	"strconv"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"
)

//go:embed migrations/*.sql
var migrationsFS embed.FS

// Migrator applies SQL migrations in order.
type Migrator struct {
	pool *pgxpool.Pool
}

// NewMigrator creates a migrator using the provided pool.
func NewMigrator(pool *pgxpool.Pool) *Migrator {
	return &Migrator{pool: pool}
}

// Migrate applies all pending migrations.
func (m *Migrator) Migrate(ctx context.Context) error {
	// Ensure schema_migrations table exists
	_, err := m.pool.Exec(ctx, `
		CREATE TABLE IF NOT EXISTS schema_migrations (
			version INTEGER PRIMARY KEY,
			name TEXT NOT NULL,
			applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
		)
	`)
	if err != nil {
		return fmt.Errorf("migrator: create schema_migrations: %w", err)
	}

	// Get applied versions
	applied, err := m.appliedVersions(ctx)
	if err != nil {
		return err
	}

	// List migration files
	entries, err := migrationsFS.ReadDir("migrations")
	if err != nil {
		return fmt.Errorf("migrator: read dir: %w", err)
	}

	type migration struct {
		version int
		name    string
		path    string
	}

	var pending []migration
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".sql") {
			continue
		}
		parts := strings.SplitN(entry.Name(), "_", 2)
		if len(parts) < 2 {
			continue
		}
		version, err := strconv.Atoi(parts[0])
		if err != nil {
			continue
		}
		if applied[version] {
			continue
		}
		pending = append(pending, migration{
			version: version,
			name:    entry.Name(),
			path:    "migrations/" + entry.Name(),
		})
	}

	sort.Slice(pending, func(i, j int) bool {
		return pending[i].version < pending[j].version
	})

	for _, mig := range pending {
		sql, err := migrationsFS.ReadFile(mig.path)
		if err != nil {
			return fmt.Errorf("migrator: read %s: %w", mig.name, err)
		}

		tx, err := m.pool.Begin(ctx)
		if err != nil {
			return fmt.Errorf("migrator: begin tx for %s: %w", mig.name, err)
		}

		if _, err := tx.Exec(ctx, string(sql)); err != nil {
			_ = tx.Rollback(ctx)
			return fmt.Errorf("migrator: exec %s: %w", mig.name, err)
		}

		if _, err := tx.Exec(ctx,
			`INSERT INTO schema_migrations (version, name) VALUES ($1, $2)`,
			mig.version, mig.name,
		); err != nil {
			_ = tx.Rollback(ctx)
			return fmt.Errorf("migrator: record %s: %w", mig.name, err)
		}

		if err := tx.Commit(ctx); err != nil {
			return fmt.Errorf("migrator: commit %s: %w", mig.name, err)
		}

		slog.InfoContext(ctx, "migration applied", "version", mig.version, "name", mig.name)
	}

	if len(pending) == 0 {
		slog.InfoContext(ctx, "no pending migrations")
	}

	return nil
}

func (m *Migrator) appliedVersions(ctx context.Context) (map[int]bool, error) {
	rows, err := m.pool.Query(ctx, `SELECT version FROM schema_migrations`)
	if err != nil {
		return nil, fmt.Errorf("migrator: query applied: %w", err)
	}
	defer rows.Close()

	applied := make(map[int]bool)
	for rows.Next() {
		var v int
		if err := rows.Scan(&v); err != nil {
			return nil, fmt.Errorf("migrator: scan version: %w", err)
		}
		applied[v] = true
	}
	return applied, rows.Err()
}
