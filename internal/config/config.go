package config

import (
	"fmt"
	"os"
	"strconv"
)

// Config holds the orchestrator configuration.
type Config struct {
	Port      int
	Telemetry TelemetryConfig
	Agents    AgentsConfig
}

// TelemetryConfig holds OpenTelemetry settings.
type TelemetryConfig struct {
	ServiceName  string
	OTLPEndpoint string
}

// AgentsConfig holds Python agent connection settings.
type AgentsConfig struct {
	Endpoint       string
	TimeoutSeconds int
	MaxRetries     int
}

// Load reads configuration from environment variables with sensible defaults.
func Load() (*Config, error) {
	port, err := getEnvInt("ORCHESTRATOR_PORT", 50051)
	if err != nil {
		return nil, fmt.Errorf("loading port: %w", err)
	}

	timeout, err := getEnvInt("AGENT_TIMEOUT_SECONDS", 30)
	if err != nil {
		return nil, fmt.Errorf("loading agent timeout: %w", err)
	}

	maxRetries, err := getEnvInt("AGENT_MAX_RETRIES", 3)
	if err != nil {
		return nil, fmt.Errorf("loading max retries: %w", err)
	}

	return &Config{
		Port: port,
		Telemetry: TelemetryConfig{
			ServiceName:  getEnv("OTEL_SERVICE_NAME", "orchestrator"),
			OTLPEndpoint: getEnv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317"),
		},
		Agents: AgentsConfig{
			Endpoint:       getEnv("AGENT_ENDPOINT", "localhost:50052"),
			TimeoutSeconds: timeout,
			MaxRetries:     maxRetries,
		},
	}, nil
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func getEnvInt(key string, fallback int) (int, error) {
	v := os.Getenv(key)
	if v == "" {
		return fallback, nil
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return 0, fmt.Errorf("parsing %s=%q as int: %w", key, v, err)
	}
	return n, nil
}
