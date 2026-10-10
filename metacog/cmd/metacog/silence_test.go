package main

import (
	"strings"
	"testing"
)

func TestSilenceValidatesRequired(t *testing.T) {
	cases := []struct {
		name     string
		about    string
		reason   string
		duration string
	}{
		{"missing_about", "", "would falsify", "until the next session"},
		{"missing_reason", "the held question", "", "until the next session"},
		{"missing_duration", "the held question", "would falsify", ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if err := validateSilence(tc.about, tc.reason, tc.duration); err == nil {
				t.Errorf("expected validation error for %s", tc.name)
			}
		})
	}
}

func TestSilenceOutputIsMinimal(t *testing.T) {
	out := formatSilence("the held question", "would falsify", "until the next session")
	if !strings.Contains(out, "the held question") {
		t.Error("output should contain --about value")
	}
	if !strings.Contains(out, "would falsify") {
		t.Error("output should contain --reason value")
	}
	if strings.Count(out, "\n") > 4 {
		t.Errorf("silence output should be minimal (<=4 newlines); got %d", strings.Count(out, "\n"))
	}
}

func TestSilenceAppendsHistory(t *testing.T) {
	s := NewState()
	applySilence(s, "the held question", "would falsify", "until the next session")
	if len(s.History) != 1 {
		t.Fatalf("expected 1 history entry, got %d", len(s.History))
	}
	h := s.History[0]
	if h.Action != "silence" {
		t.Errorf("expected action 'silence', got %q", h.Action)
	}
	if h.Params["about"] != "the held question" {
		t.Errorf("about not stored; got %q", h.Params["about"])
	}
	if h.Params["reason"] != "would falsify" {
		t.Errorf("reason not stored; got %q", h.Params["reason"])
	}
	if h.Params["duration"] != "until the next session" {
		t.Errorf("duration not stored; got %q", h.Params["duration"])
	}
}
