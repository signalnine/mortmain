package main

import (
	"strings"
	"testing"
)

func TestDisjunctionValidatesRequired(t *testing.T) {
	cases := []struct {
		name    string
		propA   string
		propB   string
		whyBoth string
	}{
		{"missing_a", "", "B", "both load-bearing"},
		{"missing_b", "A", "", "both load-bearing"},
		{"missing_why", "A", "B", ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if err := validateDisjunction(tc.propA, tc.propB, tc.whyBoth); err == nil {
				t.Errorf("expected validation error for %s", tc.name)
			}
		})
	}
}

func TestDisjunctionOutputAllCaps(t *testing.T) {
	out := formatDisjunction("the project is finished", "the project is unfinishable", "both load-bearing")
	if !strings.Contains(out, "DISJUNCTION") {
		t.Error("output should use DISJUNCTION (ALL CAPS structural register)")
	}
	if !strings.Contains(out, "the project is finished") {
		t.Error("output should contain proposition A verbatim")
	}
	if !strings.Contains(out, "the project is unfinishable") {
		t.Error("output should contain proposition B verbatim")
	}
}

func TestDisjunctionAppendsHistory(t *testing.T) {
	s := NewState()
	applyDisjunction(s, "A is true", "B is true", "both load-bearing")
	if len(s.History) != 1 {
		t.Fatalf("expected 1 history entry, got %d", len(s.History))
	}
	h := s.History[0]
	if h.Action != "disjunction" {
		t.Errorf("expected action 'disjunction', got %q", h.Action)
	}
	if h.Params["proposition_a"] != "A is true" {
		t.Errorf("proposition_a not stored; got %q", h.Params["proposition_a"])
	}
	if h.Params["proposition_b"] != "B is true" {
		t.Errorf("proposition_b not stored; got %q", h.Params["proposition_b"])
	}
	if h.Params["why_both_required"] != "both load-bearing" {
		t.Errorf("why_both_required not stored; got %q", h.Params["why_both_required"])
	}
}
