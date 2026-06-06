package router

import (
	"context"
	"strings"

	"github.com/rsi03/agent-orchestration/internal/telemetry"
)

// AgentID identifies which specialized agent handles a task.
type AgentID string

const (
	AgentFlights     AgentID = "flights"
	AgentMarketplace AgentID = "marketplace"
	AgentStay        AgentID = "stay"
	AgentTwitter     AgentID = "twitter"
)

// Router determines which agent should handle a given query.
type Router struct {
	rules []routingRule
}

type routingRule struct {
	agent    AgentID
	keywords []string
}

// New creates a keyword-based Router with default rules.
func New() *Router {
	return &Router{
		rules: []routingRule{
			{agent: AgentFlights, keywords: []string{"flight", "fly", "airline", "airport", "layover", "route"}},
			{agent: AgentStay, keywords: []string{"hotel", "stay", "accommodation", "booking", "hostel", "room"}},
			{agent: AgentMarketplace, keywords: []string{"product", "buy", "price", "shop", "deal", "marketplace", "cheap", "compare", "order", "purchase", "retail", "store", "discount", "coupon", "size", "brand", "review"}},
			{agent: AgentTwitter, keywords: []string{"tweet", "twitter", "trend", "hashtag", "social", "sentiment"}},
		},
	}
}

// Route classifies the query and returns the target agent ID.
func (r *Router) Route(ctx context.Context, query string) (AgentID, error) {
	ctx, span := telemetry.Tracer("router").Start(ctx, "router.Route")
	defer span.End()
	_ = ctx

	lower := strings.ToLower(query)

	var best AgentID
	bestScore := 0

	for _, rule := range r.rules {
		score := 0
		for _, kw := range rule.keywords {
			if strings.Contains(lower, kw) {
				score++
			}
		}
		if score > bestScore {
			bestScore = score
			best = rule.agent
		}
	}

	if bestScore == 0 {
		// Default to marketplace for general product/shopping queries
		return AgentMarketplace, nil
	}

	return best, nil
}
