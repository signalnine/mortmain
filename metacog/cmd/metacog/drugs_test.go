package main

import (
	"testing"
)

func TestDrugsOutput(t *testing.T) {
	result := formatDrugs("caffeine", "adenosine antagonism", "sharp edges")
	expected := "caffeine ingested. Taking action via adenosine antagonism. Producing subjective experience: sharp edges"
	if result != expected {
		t.Errorf("expected %q, got %q", expected, result)
	}
}

func TestDrugsUpdatesState(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	s := NewState()
	applyDrugs(s, "caffeine", "adenosine antagonism", "sharp edges")

	sm.Save(s)

	loaded, _ := sm.Load()
	if loaded.Substrate == nil {
		t.Fatal("substrate should be set")
	}
	if loaded.Substrate.Substance != "caffeine" {
		t.Errorf("expected caffeine, got %s", loaded.Substrate.Substance)
	}
	if len(loaded.History) != 1 || loaded.History[0].Action != "drugs" {
		t.Error("expected drugs history entry")
	}
}
