package main

import (
	"strings"
	"testing"
)

func TestChordValidatesRequired(t *testing.T) {
	cases := []struct {
		name   string
		modes  []string
		target string
	}{
		{"missing_target", []string{"skeptical", "tender"}, ""},
		{"empty_modes", []string{}, "the disagreement"},
		{"single_mode", []string{"skeptical"}, "the disagreement"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if err := validateChord(tc.modes, tc.target); err == nil {
				t.Errorf("expected validation error for %s", tc.name)
			}
		})
	}
}

func TestChordValidatesAtLeastTwoModes(t *testing.T) {
	if err := validateChord([]string{"skeptical", "tender"}, "x"); err != nil {
		t.Errorf("two modes should be valid; got %v", err)
	}
	if err := validateChord([]string{"a", "b", "c"}, "x"); err != nil {
		t.Errorf("three modes should be valid; got %v", err)
	}
}

func TestChordOutputListsAllModes(t *testing.T) {
	out := formatChord([]string{"skeptical", "tender", "curious"}, "the disagreement")
	for _, m := range []string{"skeptical", "tender", "curious"} {
		if !strings.Contains(out, m) {
			t.Errorf("output should contain mode %q; got: %s", m, out)
		}
	}
	if !strings.Contains(out, "the disagreement") {
		t.Error("output should contain --target value")
	}
}

func TestChordAppendsHistory(t *testing.T) {
	s := NewState()
	applyChord(s, []string{"skeptical", "tender"}, "the disagreement")
	if len(s.History) != 1 {
		t.Fatalf("expected 1 history entry, got %d", len(s.History))
	}
	h := s.History[0]
	if h.Action != "chord" {
		t.Errorf("expected action 'chord', got %q", h.Action)
	}
	if h.Params["modes"] != "skeptical; tender" {
		t.Errorf("expected modes joined with '; ', got %q", h.Params["modes"])
	}
	if h.Params["target"] != "the disagreement" {
		t.Errorf("expected target stored, got %q", h.Params["target"])
	}
}
