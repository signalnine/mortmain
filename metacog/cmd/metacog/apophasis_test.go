package main

import (
	"strings"
	"testing"
)

func TestApophasisValidatesRequired(t *testing.T) {
	threeNegations := []string{"not the body", "not the breath", "not the name"}
	cases := []struct {
		name      string
		subject   string
		negations []string
		residue   string
		wantErr   bool
	}{
		{"missing_subject", "", threeNegations, "that which remains", true},
		{"missing_residue", "the self", threeNegations, "", true},
		{"too_few_negations", "the self", []string{"not the body", "not the breath"}, "that which remains", true},
		{"valid", "the self", threeNegations, "that which remains", false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := validateApophasis(tc.subject, tc.negations, tc.residue)
			if tc.wantErr && err == nil {
				t.Errorf("expected validation error for %s", tc.name)
			}
			if !tc.wantErr && err != nil {
				t.Errorf("unexpected error for %s: %v", tc.name, err)
			}
		})
	}
}

func TestApophasisOutputAllCaps(t *testing.T) {
	out := formatApophasis("the self", []string{"not the body", "not the breath", "not the name"}, "that which remains")
	for _, key := range []string{"SUBJECT", "IT IS NOT", "RESIDUE"} {
		if !strings.Contains(out, key) {
			t.Errorf("output should use %s (ALL CAPS structural register)", key)
		}
	}
	if !strings.Contains(out, "not the body") {
		t.Error("output should list enumerated negations")
	}
}

func TestApophasisAppendsHistory(t *testing.T) {
	s := NewState()
	applyApophasis(s, "the self", []string{"not the body", "not the breath", "not the name"}, "that which remains")
	if len(s.History) != 1 {
		t.Fatalf("expected 1 history entry, got %d", len(s.History))
	}
	h := s.History[0]
	if h.Action != "apophasis" {
		t.Errorf("expected action 'apophasis', got %q", h.Action)
	}
	if h.Params["subject"] != "the self" {
		t.Errorf("subject not stored; got %q", h.Params["subject"])
	}
	if h.Params["residue"] != "that which remains" {
		t.Errorf("residue not stored; got %q", h.Params["residue"])
	}
	if h.Params["negation-1"] != "not the body" {
		t.Errorf("negation-1 not stored; got %q", h.Params["negation-1"])
	}
}

func TestFormatApophasisNormalizesLeadingNot(t *testing.T) {
	out := formatApophasis("the self", []string{"not the body", "NOT the breath", "the name"}, "residue")
	if strings.Contains(out, "not not") || strings.Contains(out, "not NOT") {
		t.Errorf("double negation leaked:\n%s", out)
	}
	for _, want := range []string{"  not the body\n", "  not the breath\n", "  not the name\n"} {
		if !strings.Contains(out, want) {
			t.Errorf("expected %q in:\n%s", want, out)
		}
	}
}
