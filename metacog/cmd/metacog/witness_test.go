package main

import (
	"strings"
	"testing"
)

func TestWitnessValidatesRequired(t *testing.T) {
	cases := []struct {
		name     string
		position string
		observed string
		distance string
	}{
		{"missing_position", "", "the speaker hesitating", "temporal"},
		{"missing_observed", "above the speaker", "", "temporal"},
		{"missing_distance", "above the speaker", "the speaker hesitating", ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if err := validateWitness(tc.position, tc.observed, tc.distance); err == nil {
				t.Errorf("expected validation error for %s", tc.name)
			}
		})
	}
}

func TestWitnessOutputAllCaps(t *testing.T) {
	out := formatWitness("above the speaker", "the speaker hesitating", "temporal")
	for _, key := range []string{"POSITION", "OBSERVED", "DISTANCE"} {
		if !strings.Contains(out, key) {
			t.Errorf("output should use %s (ALL CAPS structural register)", key)
		}
	}
}

func TestWitnessAppendsHistory(t *testing.T) {
	s := NewState()
	applyWitness(s, "above the speaker", "the speaker hesitating", "temporal")
	if len(s.History) != 1 {
		t.Fatalf("expected 1 history entry, got %d", len(s.History))
	}
	h := s.History[0]
	if h.Action != "witness" {
		t.Errorf("expected action 'witness', got %q", h.Action)
	}
	if h.Params["position"] != "above the speaker" {
		t.Errorf("position not stored; got %q", h.Params["position"])
	}
	if h.Params["observed"] != "the speaker hesitating" {
		t.Errorf("observed not stored; got %q", h.Params["observed"])
	}
	if h.Params["distance"] != "temporal" {
		t.Errorf("distance not stored; got %q", h.Params["distance"])
	}
}
