package main

import (
	"strings"
	"testing"
)

func TestCommitmentValidatesRequired(t *testing.T) {
	cases := []struct {
		name      string
		binding   string
		stakes    string
		falsifier string
	}{
		{"missing_binding", "", "credibility", "if X then wrong"},
		{"missing_stakes", "X is true", "", "if X then wrong"},
		{"missing_falsifier", "X is true", "credibility", ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if err := validateCommitment(tc.binding, tc.stakes, tc.falsifier); err == nil {
				t.Errorf("expected validation error for %s", tc.name)
			}
		})
	}
}

func TestCommitmentOutputAllCaps(t *testing.T) {
	out := formatCommitment("X is true", "credibility", "if A is observed, X is wrong")
	if !strings.Contains(out, "BINDING") {
		t.Error("output should use BINDING (ALL CAPS structural register)")
	}
	if !strings.Contains(out, "STAKES") {
		t.Error("output should use STAKES (ALL CAPS structural register)")
	}
	if !strings.Contains(out, "FALSIFIER") {
		t.Error("output should use FALSIFIER (ALL CAPS structural register)")
	}
}

func TestCommitmentAppendsHistory(t *testing.T) {
	s := NewState()
	applyCommitment(s, "X is true", "credibility", "if A then wrong")
	if len(s.History) != 1 {
		t.Fatalf("expected 1 history entry, got %d", len(s.History))
	}
	h := s.History[0]
	if h.Action != "commitment" {
		t.Errorf("expected action 'commitment', got %q", h.Action)
	}
	if h.Params["binding"] != "X is true" {
		t.Errorf("binding not stored; got %q", h.Params["binding"])
	}
	if h.Params["stakes"] != "credibility" {
		t.Errorf("stakes not stored; got %q", h.Params["stakes"])
	}
	if h.Params["falsifier"] != "if A then wrong" {
		t.Errorf("falsifier not stored; got %q", h.Params["falsifier"])
	}
}
