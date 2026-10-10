package main

import (
	"strings"
	"testing"
)

func TestForkOutput(t *testing.T) {
	threads := []string{"Cassandra: argue from worst-case", "Pollyanna: argue from best-case", "Dispatcher: pick the moment to commit"}
	result := formatFork(threads, "the boundary between optimism and resignation", "the moment a thread requires an assumption not in the original premises")

	for _, want := range []string{
		"MANIFOLD SPLIT -- 3 parallel threads launched:",
		"[1] Cassandra: argue from worst-case",
		"[2] Pollyanna: argue from best-case",
		"[3] Dispatcher: pick the moment to commit",
		"DIVERGENCE VECTOR: the boundary between optimism and resignation",
		"SACRIFICE CONDITION: the moment a thread requires",
		"AWAIT state",
	} {
		if !strings.Contains(result, want) {
			t.Errorf("output missing %q\n--- got ---\n%s", want, result)
		}
	}
}

func TestForkUpdatesState(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	s := NewState()
	applyFork(s, []string{"t1", "t2"}, "vector", "trigger")
	sm.Save(s)

	loaded, _ := sm.Load()
	if len(loaded.History) != 1 {
		t.Fatalf("expected 1 entry, got %d", len(loaded.History))
	}
	h := loaded.History[0]
	if h.Action != "fork" {
		t.Errorf("action: %s", h.Action)
	}
	if h.Params["threads"] != "t1; t2" {
		t.Errorf("threads: %q", h.Params["threads"])
	}
	if h.Params["divergence_vector"] != "vector" {
		t.Errorf("divergence_vector: %q", h.Params["divergence_vector"])
	}
	if h.Params["sacrifice_condition"] != "trigger" {
		t.Errorf("sacrifice_condition: %q", h.Params["sacrifice_condition"])
	}
}

func TestForkValidatesMinThreads(t *testing.T) {
	err := validateFork([]string{"only one"}, "v", "t")
	if err == nil {
		t.Fatal("expected error for fewer than 2 threads")
	}
	if !strings.Contains(err.Error(), "at least 2") {
		t.Errorf("expected 'at least 2' in error, got: %v", err)
	}
}

func TestForkValidatesRequired(t *testing.T) {
	threads := []string{"a", "b"}
	cases := []struct {
		name string
		v, t string
	}{
		{"missing vector", "", "trigger"},
		{"missing trigger", "vector", ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if err := validateFork(threads, tc.v, tc.t); err == nil {
				t.Errorf("expected error for %s", tc.name)
			}
		})
	}
}
