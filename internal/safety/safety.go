package safety

import (
	"regexp"
	"strings"
)

var (
	emailRE = regexp.MustCompile(`\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b`)
	ssnRE   = regexp.MustCompile(`\b\d{3}-?\d{2}-?\d{4}\b`)
	phoneRE  = regexp.MustCompile(`(?:\+?\d{1,3}[\s().-]\d{2,4}[\s().-]\d{2,4}[\s().-]\d{2,4})`)
	addressRE = regexp.MustCompile(`(?i)\b\d{1,5}\s+[A-Za-z0-9.'-]+(?:\s+[A-Za-z0-9.'-]+){0,4}\s+(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr|boulevard|blvd|court|ct|place|pl|square|sq|way|close|crescent|cres|terrace|ter)\b`)
	cardRE = regexp.MustCompile(`\b(?:\d[ -]*?){13,19}\b`)
	bearerRE = regexp.MustCompile(`(?i)\bbearer\s+[A-Za-z0-9._\-+/=]{8,}\b`)
	secretAssignmentRE = regexp.MustCompile(`(?i)\b(?:api[_-]?key|secret|token|password|passphrase|access[_-]?token|refresh[_-]?token|private[_-]?key)\b\s*[:=]\s*([^\s,;]+)`)
	secretPrefixRE = regexp.MustCompile(`\b(?:sk-|rk-|pk-|ghp_|gho_|xoxb-|xoxp-|AIza[0-9A-Za-z_-]{10,})[A-Za-z0-9._=-]{8,}\b`)
)

// RedactText removes routine PII and obvious secret-like payloads from text.
func RedactText(text string) string {
	if text == "" {
		return text
	}

	redacted := emailRE.ReplaceAllString(text, "<redacted-email>")
	redacted = ssnRE.ReplaceAllString(redacted, "<redacted-ssn>")
	redacted = cardRE.ReplaceAllStringFunc(redacted, redactCard)
	redacted = phoneRE.ReplaceAllString(redacted, "<redacted-phone>")
	redacted = addressRE.ReplaceAllString(redacted, "<redacted-address>")
	redacted = bearerRE.ReplaceAllString(redacted, "<redacted-secret>")
	redacted = secretAssignmentRE.ReplaceAllString(redacted, "<redacted-secret>")
	redacted = secretPrefixRE.ReplaceAllString(redacted, "<redacted-secret>")
	return redacted
}

// RedactConversation redacts the query and response payloads for persistence.
func RedactConversation(query, response string) (string, string) {
	return RedactText(query), RedactText(response)
}

func redactCard(match string) string {
	digits := stripNonDigits(match)
	if len(digits) < 13 || len(digits) > 19 {
		return match
	}
	if !luhnValid(digits) {
		return match
	}
	return "<redacted-card>"
}

func stripNonDigits(s string) string {
	var b strings.Builder
	b.Grow(len(s))
	for _, r := range s {
		if r >= '0' && r <= '9' {
			b.WriteRune(r)
		}
	}
	return b.String()
}

func luhnValid(number string) bool {
	sum := 0
	double := false
	for i := len(number) - 1; i >= 0; i-- {
		digit := int(number[i] - '0')
		if double {
			digit *= 2
			if digit > 9 {
				digit -= 9
			}
		}
		sum += digit
		double = !double
	}
	return sum%10 == 0
}
