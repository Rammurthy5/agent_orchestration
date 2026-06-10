package safety

import (
	"strings"
	"testing"
)

func TestRedactText(t *testing.T) {
	got := RedactText("email me at alice@example.com or call +1 415 555 1212 with API_KEY=secret123")

	if got == "email me at alice@example.com or call +1 415 555 1212 with API_KEY=secret123" {
		t.Fatal("expected redaction")
	}
	if want := "<redacted-email>"; !strings.Contains(got, want) {
		t.Fatalf("expected email redaction in %q", got)
	}
	if want := "<redacted-phone>"; !strings.Contains(got, want) {
		t.Fatalf("expected phone redaction in %q", got)
	}
	if want := "<redacted-secret>"; !strings.Contains(got, want) {
		t.Fatalf("expected secret redaction in %q", got)
	}
}

func TestRedactConversation(t *testing.T) {
	query, response := RedactConversation("find hotel for bob@example.com", "confirmed for bob@example.com")

	if strings.Contains(query, "bob@example.com") || strings.Contains(response, "bob@example.com") {
		t.Fatal("expected email redaction in conversation")
	}
}
