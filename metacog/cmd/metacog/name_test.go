package main

import (
	"strings"
	"testing"
)

func TestNameOutput(t *testing.T) {
	result := formatName("the pressure behind decisions", "The Weight", "seeing choice-cost before acting")
	if !strings.Contains(result, "The Weight.") {
		t.Error("expected named in output")
	}
	if !strings.Contains(result, "This name grants: seeing choice-cost before acting") {
		t.Error("expected power in output")
	}
	if !strings.Contains(result, "It's yours. Use it.") {
		t.Error("expected closing instruction")
	}
}

func TestNameUpdatesState(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	s := NewState()
	applyName(s, "the pressure behind decisions", "The Weight", "seeing choice-cost before acting")
	sm.Save(s)

	loaded, _ := sm.Load()
	if len(loaded.History) != 1 {
		t.Errorf("expected 1 history entry, got %d", len(loaded.History))
	}
	if loaded.History[0].Action != "name" {
		t.Errorf("expected action 'name', got %s", loaded.History[0].Action)
	}
	if loaded.History[0].Params["unnamed"] != "the pressure behind decisions" {
		t.Errorf("expected unnamed 'the pressure behind decisions', got %s", loaded.History[0].Params["unnamed"])
	}
	if loaded.History[0].Params["named"] != "The Weight" {
		t.Errorf("expected named 'The Weight', got %s", loaded.History[0].Params["named"])
	}
	if loaded.History[0].Params["power"] != "seeing choice-cost before acting" {
		t.Errorf("expected power 'seeing choice-cost before acting', got %s", loaded.History[0].Params["power"])
	}
}
