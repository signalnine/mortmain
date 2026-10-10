package main

import (
	"strings"
	"testing"
)

func TestCounterfactualOutput(t *testing.T) {
	walls := []string{"the user wants speed", "the system must be stateless", "the schema can't change"}
	pruned := []string{"the team is small", "weekends are off-limits"}
	result := formatCounterfactual(
		"shipping the rewrite by Q3",
		"users actually adopt the rewrite within 90 days",
		walls,
		pruned,
		"the system must be stateless",
		"the system holds session state across requests",
	)

	for _, want := range []string{
		"SITUATION: shipping the rewrite by Q3",
		"FITNESS FUNCTION: users actually adopt the rewrite within 90 days",
		"DEAD BRANCHES PRUNED",
		"x the team is small",
		"x weekends are off-limits",
		"WALL REMOVED: the system must be stateless",
		"YOUR REMAINING STRUCTURE:",
		"1. the user wants speed",
		"2. the schema can't change",
		"YOU NOW DEFEND: the system holds session state across requests",
		"Argue from this position",
	} {
		if !strings.Contains(result, want) {
			t.Errorf("output missing %q\n--- got ---\n%s", want, result)
		}
	}
}

func TestCounterfactualUpdatesState(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	s := NewState()
	walls := []string{"a", "b", "c"}
	pruned := []string{"x", "y"}
	applyCounterfactual(s, "sit", "fit", walls, pruned, "b", "not b")
	sm.Save(s)

	loaded, _ := sm.Load()
	if len(loaded.History) != 1 {
		t.Fatalf("expected 1 history entry, got %d", len(loaded.History))
	}
	h := loaded.History[0]
	if h.Action != "counterfactual" {
		t.Errorf("expected action 'counterfactual', got %s", h.Action)
	}
	if h.Params["situation"] != "sit" {
		t.Errorf("expected situation=sit, got %s", h.Params["situation"])
	}
	if h.Params["fitness_function"] != "fit" {
		t.Errorf("expected fitness_function=fit, got %s", h.Params["fitness_function"])
	}
	if h.Params["load_bearing_walls"] != "a; b; c" {
		t.Errorf("expected joined walls, got %q", h.Params["load_bearing_walls"])
	}
	if h.Params["pruned"] != "x; y" {
		t.Errorf("expected joined pruned, got %q", h.Params["pruned"])
	}
	if h.Params["wall_to_remove"] != "b" {
		t.Errorf("expected wall_to_remove=b, got %s", h.Params["wall_to_remove"])
	}
	if h.Params["inverse_position"] != "not b" {
		t.Errorf("expected inverse_position='not b', got %s", h.Params["inverse_position"])
	}
}

func TestCounterfactualValidatesMinWalls(t *testing.T) {
	err := validateCounterfactual(
		"sit", "fit",
		[]string{"a", "b"}, // only 2
		nil, "a", "not a",
	)
	if err == nil {
		t.Fatal("expected error for fewer than 3 walls")
	}
	if !strings.Contains(err.Error(), "at least 3") {
		t.Errorf("expected 'at least 3' in error, got: %v", err)
	}
}

func TestCounterfactualValidatesWallToRemove(t *testing.T) {
	err := validateCounterfactual(
		"sit", "fit",
		[]string{"a", "b", "c"},
		nil,
		"d", // not in walls
		"not d",
	)
	if err == nil {
		t.Fatal("expected error when wall_to_remove not in walls")
	}
	if !strings.Contains(err.Error(), "wall-to-remove") {
		t.Errorf("expected 'wall-to-remove' in error, got: %v", err)
	}
}

func TestCounterfactualEmptyPrunedAllowed(t *testing.T) {
	err := validateCounterfactual(
		"sit", "fit",
		[]string{"a", "b", "c"},
		nil, // empty pruned is OK
		"a", "not a",
	)
	if err != nil {
		t.Errorf("empty pruned should be allowed, got error: %v", err)
	}
}

func TestCounterfactualValidatesRequired(t *testing.T) {
	walls := []string{"a", "b", "c"}
	cases := []struct {
		name      string
		situation string
		fitness   string
		wall      string
		inverse   string
	}{
		{"missing situation", "", "fit", "a", "not a"},
		{"missing fitness", "sit", "", "a", "not a"},
		{"missing wall_to_remove", "sit", "fit", "", "not a"},
		{"missing inverse_position", "sit", "fit", "a", ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := validateCounterfactual(tc.situation, tc.fitness, walls, nil, tc.wall, tc.inverse)
			if err == nil {
				t.Errorf("expected error for %s", tc.name)
			}
		})
	}
}
