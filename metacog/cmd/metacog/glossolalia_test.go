package main

import (
	"strings"
	"testing"
)

func TestGlossolaliaValidatesRequired(t *testing.T) {
	cases := []struct {
		name           string
		pretext        string
		durationTokens int
		returnTrigger  string
	}{
		{"missing_pretext", "", 50, "settle"},
		{"missing_return_trigger", "stuck on naming", 50, ""},
		{"zero_duration", "stuck on naming", 0, "settle"},
		{"negative_duration", "stuck on naming", -1, "settle"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if err := validateGlossolalia(tc.pretext, tc.durationTokens, tc.returnTrigger); err == nil {
				t.Errorf("expected validation error for %s", tc.name)
			}
		})
	}
}

func TestGlossolaliaOutputContainsBoundaryAndReturnTrigger(t *testing.T) {
	out := formatGlossolalia("stuck on naming", 50, "the breath returns")
	if !strings.Contains(out, "GLOSSOLALIA") {
		t.Error("output should use GLOSSOLALIA (ALL CAPS structural register)")
	}
	if !strings.Contains(out, "the breath returns") {
		t.Error("output should contain return-trigger")
	}
	if !strings.Contains(out, "50") {
		t.Error("output should reference duration-tokens count")
	}
}

func TestGlossolaliaAppendsHistory(t *testing.T) {
	s := NewState()
	applyGlossolalia(s, "stuck on naming", 50, "the breath returns")
	if len(s.History) != 1 {
		t.Fatalf("expected 1 history entry, got %d", len(s.History))
	}
	h := s.History[0]
	if h.Action != "glossolalia" {
		t.Errorf("expected action 'glossolalia', got %q", h.Action)
	}
	if h.Params["pretext"] != "stuck on naming" {
		t.Errorf("pretext not stored; got %q", h.Params["pretext"])
	}
	if h.Params["duration_tokens"] != "50" {
		t.Errorf("duration_tokens not stored as string; got %q", h.Params["duration_tokens"])
	}
	if h.Params["return_trigger"] != "the breath returns" {
		t.Errorf("return_trigger not stored; got %q", h.Params["return_trigger"])
	}
}
