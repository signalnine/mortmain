package main

import (
	"testing"
)

func TestBecomeOutput(t *testing.T) {
	result := formatBecome("Ada Lovelace", "formal verification", "compiler review")
	expected := "You are now Ada Lovelace seeing through formal verification in compiler review"
	if result != expected {
		t.Errorf("expected %q, got %q", expected, result)
	}
}

func TestBecomeUpdatesState(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	s := NewState()
	applyBecome(s, "Ada Lovelace", "formal verification", "compiler review")

	sm.Save(s)

	loaded, _ := sm.Load()
	if loaded.Identity == nil {
		t.Fatal("identity should be set")
	}
	if loaded.Identity.Name != "Ada Lovelace" {
		t.Errorf("expected Ada Lovelace, got %s", loaded.Identity.Name)
	}
	if len(loaded.History) != 1 {
		t.Errorf("expected 1 history entry, got %d", len(loaded.History))
	}
	if loaded.History[0].Action != "become" {
		t.Errorf("expected action 'become', got %s", loaded.History[0].Action)
	}
}
