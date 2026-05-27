package config

import (
	"os"
	"testing"
)

func TestLoad(t *testing.T) {
	tests := []struct {
		name    string
		env     map[string]string
		want    *Config
		wantErr bool
	}{
		{
			name: "defaults",
			env:  map[string]string{},
			want: &Config{
				Port: 50051,
				Telemetry: TelemetryConfig{
					ServiceName:  "orchestrator",
					OTLPEndpoint: "localhost:4317",
				},
				Agents: AgentsConfig{
					Endpoint:       "localhost:50052",
					TimeoutSeconds: 30,
					MaxRetries:     3,
				},
			},
		},
		{
			name: "custom values",
			env: map[string]string{
				"ORCHESTRATOR_PORT":            "9090",
				"OTEL_SERVICE_NAME":            "my-service",
				"OTEL_EXPORTER_OTLP_ENDPOINT":  "otel:4317",
				"AGENT_ENDPOINT":               "agents:8080",
				"AGENT_TIMEOUT_SECONDS":        "60",
				"AGENT_MAX_RETRIES":            "5",
			},
			want: &Config{
				Port: 9090,
				Telemetry: TelemetryConfig{
					ServiceName:  "my-service",
					OTLPEndpoint: "otel:4317",
				},
				Agents: AgentsConfig{
					Endpoint:       "agents:8080",
					TimeoutSeconds: 60,
					MaxRetries:     5,
				},
			},
		},
		{
			name:    "invalid port",
			env:     map[string]string{"ORCHESTRATOR_PORT": "not-a-number"},
			wantErr: true,
		},
		{
			name:    "invalid timeout",
			env:     map[string]string{"AGENT_TIMEOUT_SECONDS": "abc"},
			wantErr: true,
		},
		{
			name:    "invalid max retries",
			env:     map[string]string{"AGENT_MAX_RETRIES": "xyz"},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Clear and set env vars
			envKeys := []string{
				"ORCHESTRATOR_PORT", "OTEL_SERVICE_NAME", "OTEL_EXPORTER_OTLP_ENDPOINT",
				"AGENT_ENDPOINT", "AGENT_TIMEOUT_SECONDS", "AGENT_MAX_RETRIES",
			}
			for _, k := range envKeys {
				os.Unsetenv(k)
			}
			for k, v := range tt.env {
				os.Setenv(k, v)
			}

			got, err := Load()
			if tt.wantErr {
				if err == nil {
					t.Fatal("expected error, got nil")
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}

			if got.Port != tt.want.Port {
				t.Errorf("Port = %d, want %d", got.Port, tt.want.Port)
			}
			if got.Telemetry.ServiceName != tt.want.Telemetry.ServiceName {
				t.Errorf("ServiceName = %q, want %q", got.Telemetry.ServiceName, tt.want.Telemetry.ServiceName)
			}
			if got.Telemetry.OTLPEndpoint != tt.want.Telemetry.OTLPEndpoint {
				t.Errorf("OTLPEndpoint = %q, want %q", got.Telemetry.OTLPEndpoint, tt.want.Telemetry.OTLPEndpoint)
			}
			if got.Agents.Endpoint != tt.want.Agents.Endpoint {
				t.Errorf("Agents.Endpoint = %q, want %q", got.Agents.Endpoint, tt.want.Agents.Endpoint)
			}
			if got.Agents.TimeoutSeconds != tt.want.Agents.TimeoutSeconds {
				t.Errorf("Agents.TimeoutSeconds = %d, want %d", got.Agents.TimeoutSeconds, tt.want.Agents.TimeoutSeconds)
			}
			if got.Agents.MaxRetries != tt.want.Agents.MaxRetries {
				t.Errorf("Agents.MaxRetries = %d, want %d", got.Agents.MaxRetries, tt.want.Agents.MaxRetries)
			}
		})
	}
}
