package router

import (
	"context"
	"testing"
)

func TestRoute(t *testing.T) {
	tests := []struct {
		name    string
		query   string
		want    AgentID
		wantErr bool
	}{
		{
			name:  "flights - explicit",
			query: "Find cheapest flights to Tokyo",
			want:  AgentFlights,
		},
		{
			name:  "flights - airline keyword",
			query: "Which airline has the best route?",
			want:  AgentFlights,
		},
		{
			name:  "stay - hotel",
			query: "Find me a hotel in Paris",
			want:  AgentStay,
		},
		{
			name:  "stay - accommodation",
			query: "Best accommodation near the beach",
			want:  AgentStay,
		},
		{
			name:  "marketplace - product search",
			query: "Find the best price for a laptop",
			want:  AgentMarketplace,
		},
		{
			name:  "marketplace - shopping",
			query: "I want to buy a new phone, show me deals",
			want:  AgentMarketplace,
		},
		{
			name:  "twitter - trends",
			query: "What are the trending hashtags on Twitter?",
			want:  AgentTwitter,
		},
		{
			name:  "twitter - sentiment",
			query: "Analyze the sentiment of recent tweets about AI",
			want:  AgentTwitter,
		},
		{
			name:  "case insensitive",
			query: "BOOK A FLIGHT TO NYC",
			want:  AgentFlights,
		},
		{
			name:  "no match falls back to marketplace",
			query: "What is the meaning of life?",
			want:  AgentMarketplace,
		},
		{
			name:  "empty query falls back to marketplace",
			query: "",
			want:  AgentMarketplace,
		},
		{
			name:  "highest score wins",
			query: "fly from the airport to catch my flight",
			want:  AgentFlights,
		},
	}

	r := New()

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := r.Route(context.Background(), tt.query)
			if tt.wantErr {
				if err == nil {
					t.Fatal("expected error, got nil")
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if got != tt.want {
				t.Errorf("Route(%q) = %q, want %q", tt.query, got, tt.want)
			}
		})
	}
}
