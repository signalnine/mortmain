package main

import (
	"fmt"
	"strings"
	"testing"
)

func TestFormatStatus(t *testing.T) {
	s := NewState()
	s.Identity = &Identity{Name: "Ada", Lens: "verification", Env: "lab"}
	s.Substrate = &Substrate{Substance: "caffeine", Method: "antagonism", Qualia: "sharp"}

	output := FormatStatus(s)
	if output == "" {
		t.Error("expected non-empty status")
	}
}

func TestFormatStatusEmpty(t *testing.T) {
	s := NewState()
	output := FormatStatus(s)
	if output == "" {
		t.Error("expected non-empty status even for empty state")
	}
}

func TestFormatHistory(t *testing.T) {
	s := NewState()
	s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "Ada"}})
	s.AddHistory(HistoryEntry{Action: "drugs", Params: map[string]string{"substance": "caffeine"}})

	output := FormatHistory(s)
	if output == "" {
		t.Error("expected non-empty history")
	}
}

func TestFormatHistoryEmpty(t *testing.T) {
	s := NewState()
	output := FormatHistory(s)
	if output == "" {
		t.Error("expected non-empty output for empty history")
	}
}

func TestHistoryFullIncludesArchivedEntries(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	s := NewState()
	for i := 0; i < 502; i++ {
		s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"i": fmt.Sprintf("%d", i)}})
	}
	if err := sm.Save(s); err != nil {
		t.Fatalf("save failed: %v", err)
	}

	loaded, err := sm.Load()
	if err != nil {
		t.Fatalf("load failed: %v", err)
	}

	merged, err := mergeArchivedHistory(sm, loaded)
	if err != nil {
		t.Fatalf("merge failed: %v", err)
	}
	if len(merged.History) != 502 {
		t.Errorf("merged history should have 502 entries, got %d", len(merged.History))
	}

	output := FormatHistory(merged)
	if !strings.Contains(output, "i=0") {
		t.Error("--full output should contain earliest archived entry (i=0)")
	}
	if !strings.Contains(output, "i=501") {
		t.Error("--full output should contain newest entry (i=501)")
	}
}

func TestResetPreservesSession(t *testing.T) {
	s := NewState()
	s.Session = "my-session"
	s.Identity = &Identity{Name: "Ada", Lens: "verification", Env: "lab"}
	s.Substrate = &Substrate{Substance: "caffeine", Method: "antagonism", Qualia: "sharp"}
	s.Stratagem = &ActiveStratagem{Name: "pivot", Step: 1}
	s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "Ada"}})

	// Simulate reset: clear working state, preserve session + history
	s.Identity = nil
	s.Substrate = nil
	s.Stratagem = nil

	if s.Session != "my-session" {
		t.Errorf("reset should preserve session, got %q", s.Session)
	}
	if len(s.History) != 1 {
		t.Errorf("reset should preserve history, got %d entries", len(s.History))
	}
	if s.Identity != nil || s.Substrate != nil || s.Stratagem != nil {
		t.Error("reset should clear identity, substrate, and stratagem")
	}
}
