package main

import (
	"strings"
	"testing"
)

func TestRitualOutput(t *testing.T) {
	result := formatRitual("old→new", []string{"step one", "step two"}, "transformation complete")
	if !strings.Contains(result, "[RITUAL EXECUTED]") {
		t.Error("expected [RITUAL EXECUTED] header")
	}
	if !strings.Contains(result, "Threshold: old→new") {
		t.Error("expected threshold")
	}
	if !strings.Contains(result, "1. step one") {
		t.Error("expected numbered steps")
	}
	if !strings.Contains(result, "transformation complete is taking hold") {
		t.Error("expected result")
	}
}

func TestRitualUpdatesState(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	s := NewState()
	applyRitual(s, "old→new", []string{"step one"}, "done")
	sm.Save(s)

	loaded, _ := sm.Load()
	if len(loaded.History) != 1 || loaded.History[0].Action != "ritual" {
		t.Error("expected ritual history entry")
	}
}
