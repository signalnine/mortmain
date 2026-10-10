package main

import "testing"

func TestFormatMeditateObjectless(t *testing.T) {
	out := formatMeditate("attachment to cleverness", "", "three breaths")
	if out == "" {
		t.Error("expected non-empty output")
	}
	if !contains(out, "just sitting") {
		t.Error("objectless meditation should mention just sitting")
	}
	if !contains(out, "attachment to cleverness") {
		t.Error("should mention what is being released")
	}
}

func TestFormatMeditateFocused(t *testing.T) {
	out := formatMeditate("urgency", "the breath", "until the mind clears")
	if out == "" {
		t.Error("expected non-empty output")
	}
	if contains(out, "just sitting") {
		t.Error("focused meditation should not mention just sitting")
	}
	if !contains(out, "the breath") {
		t.Error("should mention focus object")
	}
}

func TestApplyMeditate(t *testing.T) {
	s := NewState()
	applyMeditate(s, "outcome", "breath", "3 breaths")
	if len(s.History) != 1 {
		t.Fatalf("expected 1 history entry, got %d", len(s.History))
	}
	if s.History[0].Action != "meditate" {
		t.Errorf("expected meditate action, got %s", s.History[0].Action)
	}
}

func TestMeditateValidatesStratagem(t *testing.T) {
	s := NewState()
	StartStratagem(s, "zen", false)
	// Step 0 of zen is meditate
	ValidatePrimitiveForStratagem(s, "meditate")
	found := false
	for _, c := range s.Stratagem.StepsCompleted {
		if c == "meditate" {
			found = true
		}
	}
	if !found {
		t.Error("meditate should be recorded in StepsCompleted")
	}
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(s) > 0 && containsHelper(s, substr))
}

func containsHelper(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
