package main

import (
	"strings"
	"testing"
)

func TestFeelOutput(t *testing.T) {
	result := formatFeel("the chest", "tight and warm", "⊕", "")
	if !strings.Contains(result, "⊕") {
		t.Error("expected sigil in output")
	}
	if !strings.Contains(result, "You are now attending to: the chest") {
		t.Error("expected somewhere in output")
	}
	if !strings.Contains(result, "It feels: tight and warm") {
		t.Error("expected quality in output")
	}
	if !strings.Contains(result, "Stay with this. Don't name it yet.") {
		t.Error("expected closing instruction")
	}
}

func TestFeelOutputWithSinceLast(t *testing.T) {
	result := formatFeel("the chest", "tight and warm", "⊕", "the message landed harder than expected")
	if !strings.Contains(result, "Since last pause: the message landed harder than expected") {
		t.Errorf("expected since_last line in output\n%s", result)
	}
	if !strings.Contains(result, "⊕") {
		t.Error("expected sigil in output")
	}
}

func TestFeelOutputWithoutSinceLast(t *testing.T) {
	result := formatFeel("the chest", "tight and warm", "⊕", "")
	if strings.Contains(result, "Since last pause:") {
		t.Errorf("did not expect since_last line when omitted\n%s", result)
	}
}

func TestFeelStateOmitsSinceLastWhenEmpty(t *testing.T) {
	s := NewState()
	applyFeel(s, "where", "what", "sigil", "")
	if len(s.History) != 1 {
		t.Fatalf("expected 1 history entry, got %d", len(s.History))
	}
	if _, ok := s.History[0].Params["since_last"]; ok {
		t.Errorf("expected since_last absent from params when empty, got %v", s.History[0].Params)
	}
}

func TestFeelStateIncludesSinceLast(t *testing.T) {
	s := NewState()
	applyFeel(s, "where", "what", "sigil", "the diff")
	if s.History[0].Params["since_last"] != "the diff" {
		t.Errorf("expected since_last='the diff', got %q", s.History[0].Params["since_last"])
	}
}

func TestFeelUpdatesState(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	s := NewState()
	applyFeel(s, "the chest", "tight and warm", "⊕", "")
	sm.Save(s)

	loaded, _ := sm.Load()
	if len(loaded.History) != 1 {
		t.Errorf("expected 1 history entry, got %d", len(loaded.History))
	}
	if loaded.History[0].Action != "feel" {
		t.Errorf("expected action 'feel', got %s", loaded.History[0].Action)
	}
	if loaded.History[0].Params["somewhere"] != "the chest" {
		t.Errorf("expected somewhere 'the chest', got %s", loaded.History[0].Params["somewhere"])
	}
	if loaded.History[0].Params["quality"] != "tight and warm" {
		t.Errorf("expected quality 'tight and warm', got %s", loaded.History[0].Params["quality"])
	}
	if loaded.History[0].Params["sigil"] != "⊕" {
		t.Errorf("expected sigil '⊕', got %s", loaded.History[0].Params["sigil"])
	}
}
