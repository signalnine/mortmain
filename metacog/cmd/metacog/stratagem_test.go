package main

import (
	"fmt"
	"strings"
	"testing"
)

func TestStratagemDefinitions(t *testing.T) {
	names := []string{"pivot", "mirror", "anchor", "reset", "manifold", "chorus", "anchor-duo"}
	for _, name := range names {
		def, ok := LoadRite(name)
		if !ok {
			t.Errorf("stratagem %q not defined", name)
			continue
		}
		if len(def.Steps) == 0 {
			t.Errorf("stratagem %q has no steps", name)
		}
	}
}

func TestPivotStepSequence(t *testing.T) {
	def, _ := LoadRite("pivot")
	expected := []StepKind{StepDrugs, StepThink, StepBecome, StepThink, StepRitual}
	if len(def.Steps) != len(expected) {
		t.Fatalf("pivot: expected %d steps, got %d", len(expected), len(def.Steps))
	}
	for i, step := range def.Steps {
		if step.Kind != expected[i] {
			t.Errorf("pivot step %d: expected %v, got %v", i+1, expected[i], step.Kind)
		}
	}
}

func TestStartStratagem(t *testing.T) {
	s := NewState()
	output, err := StartStratagem(s, "pivot", false)
	if err != nil {
		t.Fatalf("start pivot failed: %v", err)
	}
	if s.Stratagem == nil {
		t.Fatal("stratagem should be active")
	}
	if s.Stratagem.Name != "pivot" {
		t.Errorf("expected pivot, got %s", s.Stratagem.Name)
	}
	if s.Stratagem.Step != 0 {
		t.Errorf("expected step 0, got %d", s.Stratagem.Step)
	}
	if output == "" {
		t.Error("expected non-empty output")
	}
}

func TestStartStratagemWhileActive(t *testing.T) {
	s := NewState()
	StartStratagem(s, "pivot", false)

	_, err := StartStratagem(s, "mirror", false)
	if err == nil {
		t.Error("expected error starting second stratagem without force")
	}
}

func TestStartStratagemForce(t *testing.T) {
	s := NewState()
	StartStratagem(s, "pivot", false)

	_, err := StartStratagem(s, "mirror", true)
	if err != nil {
		t.Fatalf("force start failed: %v", err)
	}
	if s.Stratagem.Name != "mirror" {
		t.Error("expected mirror after force")
	}
	// Check pivot was recorded as abandoned
	found := false
	for _, h := range s.History {
		if h.Action == "stratagem" && h.Status == "abandoned" {
			found = true
			break
		}
	}
	if !found {
		t.Error("abandoned stratagem should be in history")
	}
}

func TestAdvanceThinkStep(t *testing.T) {
	s := NewState()
	StartStratagem(s, "pivot", false)

	// Step 0 is drugs — simulate calling drugs
	s.Stratagem.StepsCompleted = append(s.Stratagem.StepsCompleted, "drugs")

	// Advance past drugs step
	_, err := AdvanceStratagem(s)
	if err != nil {
		t.Fatalf("advance past drugs failed: %v", err)
	}

	// Now at step 1 (THINK) — should advance freely
	_, err = AdvanceStratagem(s)
	if err != nil {
		t.Fatalf("advance past THINK failed: %v", err)
	}

	// Now at step 2 (become)
	if s.Stratagem.Step != 2 {
		t.Errorf("expected step 2, got %d", s.Stratagem.Step)
	}
}

func TestAdvanceRequiresPrimitive(t *testing.T) {
	s := NewState()
	StartStratagem(s, "pivot", false)

	// Step 0 is drugs — try to advance without calling drugs
	_, err := AdvanceStratagem(s)
	if err == nil {
		t.Error("expected error advancing without calling drugs first")
	}
}

func TestCompleteStratagem(t *testing.T) {
	s := NewState()
	StartStratagem(s, "reset", false)

	// Reset: ritual, THINK, ritual
	// Step 0: ritual
	s.Stratagem.StepsCompleted = append(s.Stratagem.StepsCompleted, "ritual")
	AdvanceStratagem(s)

	// Step 1: THINK — advances freely
	AdvanceStratagem(s)

	// Step 2: ritual
	s.Stratagem.StepsCompleted = append(s.Stratagem.StepsCompleted, "ritual")
	output, err := AdvanceStratagem(s)
	if err != nil {
		t.Fatalf("final advance failed: %v", err)
	}

	if s.Stratagem != nil {
		t.Error("stratagem should be cleared after completion")
	}
	if output == "" {
		t.Error("completion should produce output")
	}
}

func TestAbortStratagem(t *testing.T) {
	s := NewState()
	StartStratagem(s, "pivot", false)

	err := AbortStratagem(s)
	if err != nil {
		t.Fatalf("abort failed: %v", err)
	}
	if s.Stratagem != nil {
		t.Error("stratagem should be nil after abort")
	}
}

func TestAbortNoStratagem(t *testing.T) {
	s := NewState()
	err := AbortStratagem(s)
	if err == nil {
		t.Error("expected error aborting with no active stratagem")
	}
}

func TestStratagemStatus(t *testing.T) {
	s := NewState()
	StartStratagem(s, "pivot", false)

	output := StratagemStatus(s)
	if output == "" {
		t.Error("expected non-empty status output")
	}
}

func TestUnknownStratagem(t *testing.T) {
	s := NewState()
	_, err := StartStratagem(s, "nonexistent", false)
	if err == nil {
		t.Error("expected error for unknown stratagem")
	}
}

func TestStartStratagemWhileActiveSuggestsValidCommand(t *testing.T) {
	s := NewState()
	StartStratagem(s, "pivot", false)

	_, err := StartStratagem(s, "mirror", false)
	if err == nil {
		t.Fatal("expected error starting second stratagem without force")
	}
	msg := err.Error()
	if !strings.Contains(msg, "metacog stratagem start mirror --force") {
		t.Errorf("error message should reference 'metacog stratagem start mirror --force', got: %s", msg)
	}
}

func TestAdvanceWithoutActiveStratagemSuggestsValidCommand(t *testing.T) {
	s := NewState()
	_, err := AdvanceStratagem(s)
	if err == nil {
		t.Fatal("expected error advancing with no active stratagem")
	}
	msg := err.Error()
	if !strings.Contains(msg, "metacog stratagem start <name>") {
		t.Errorf("error message should reference 'metacog stratagem start <name>', got: %s", msg)
	}
}

func TestUnknownStratagemListsSorted(t *testing.T) {
	s := NewState()
	_, err := StartStratagem(s, "nope", false)
	if err == nil {
		t.Fatal("expected error")
	}
	if !strings.Contains(err.Error(), "anchor, anchor-duo, chorus") {
		t.Errorf("available list should be sorted: %v", err)
	}
}

func TestValidateSameKindAutoAdvances(t *testing.T) {
	s := NewState()
	// anchor-duo: commitment, excerpt, excerpt, fork, ritual
	if _, err := StartStratagem(s, "anchor-duo", false); err != nil {
		t.Fatal(err)
	}
	ValidatePrimitiveForStratagem(s, "commitment")
	if _, err := AdvanceStratagem(s); err != nil {
		t.Fatal(err)
	}
	note1 := ValidatePrimitiveForStratagem(s, "excerpt")
	if s.Stratagem.Step != 1 {
		t.Fatalf("first excerpt should mark step 2 without advancing, at %d", s.Stratagem.Step)
	}
	if !strings.Contains(note1, "step 2/5 satisfied") {
		t.Errorf("note should say the step is satisfied: %q", note1)
	}
	note2 := ValidatePrimitiveForStratagem(s, "excerpt")
	if s.Stratagem.Step != 2 {
		t.Fatalf("second consecutive excerpt should auto-advance to step 3, at %d", s.Stratagem.Step)
	}
	if !strings.Contains(note2, "auto-advanced") {
		t.Errorf("note should mention auto-advance: %q", note2)
	}
	if len(s.Stratagem.StepsCompleted) != 1 || s.Stratagem.StepsCompleted[0] != "excerpt" {
		t.Errorf("step 3 should be marked satisfied by the second excerpt: %v", s.Stratagem.StepsCompleted)
	}
	if _, err := AdvanceStratagem(s); err != nil {
		t.Fatalf("next after two excerpts should reach fork: %v", err)
	}
	if s.Stratagem.Step != 3 || s.Stratagem.Steps[3].Kind != StepFork {
		t.Errorf("expected to be at fork (step 4), at %d", s.Stratagem.Step)
	}
}

func TestValidateThreeConsecutiveSameKind(t *testing.T) {
	s := NewState()
	// chorus: become, become, become, fork, ritual
	if _, err := StartStratagem(s, "chorus", false); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 3; i++ {
		ValidatePrimitiveForStratagem(s, "become")
		if s.Stratagem.Step != i {
			t.Fatalf("after become #%d expected step index %d, got %d", i+1, i, s.Stratagem.Step)
		}
	}
	// A fourth become has nowhere to go: step 3 is fork.
	note := ValidatePrimitiveForStratagem(s, "become")
	if s.Stratagem.Step != 2 || !strings.Contains(note, "already satisfied") {
		t.Errorf("fourth become must not advance into fork: step=%d note=%q", s.Stratagem.Step, note)
	}
	if _, err := AdvanceStratagem(s); err != nil {
		t.Fatal(err)
	}
	if s.Stratagem.Step != 3 || s.Stratagem.Steps[3].Kind != StepFork {
		t.Errorf("expected fork at step index 3, at %d", s.Stratagem.Step)
	}
	if _, err := AdvanceStratagem(s); err == nil {
		t.Error("next without fork must fail")
	}
}

func TestValidateDoesNotAutoAdvanceAcrossDifferentKinds(t *testing.T) {
	s := NewState()
	StartStratagem(s, "pivot", false) // drugs, THINK, become, THINK, ritual
	ValidatePrimitiveForStratagem(s, "drugs")
	note := ValidatePrimitiveForStratagem(s, "drugs")
	if s.Stratagem.Step != 0 {
		t.Errorf("a repeated drugs must not skip the THINK step, at %d", s.Stratagem.Step)
	}
	if !strings.Contains(note, "already satisfied") {
		t.Errorf("note should say already satisfied: %q", note)
	}
}

func TestValidateOffScriptNote(t *testing.T) {
	s := NewState()
	StartStratagem(s, "pivot", false)
	note := ValidatePrimitiveForStratagem(s, "feel")
	if !strings.Contains(note, "expects 'drugs'") || !strings.Contains(note, "freestyle") {
		t.Errorf("off-script note should name the expected primitive and say freestyle: %q", note)
	}
	if len(s.Stratagem.StepsCompleted) != 0 {
		t.Error("off-script primitive must not mark the step")
	}
}

func TestValidateNoStratagemNoNote(t *testing.T) {
	s := NewState()
	if note := ValidatePrimitiveForStratagem(s, "feel"); note != "" {
		t.Errorf("expected empty note, got %q", note)
	}
}

func TestFormatStratagemListCoversAll(t *testing.T) {
	out := FormatStratagemList()
	all := LoadRites()
	for name, def := range all {
		if !strings.Contains(out, name) || !strings.Contains(out, def.Name) {
			t.Errorf("list missing %s / %s", name, def.Name)
		}
	}
	if !strings.HasPrefix(out, fmt.Sprintf("%d stratagems", len(all))) {
		t.Errorf("list should open with the count:\n%s", out)
	}
	views := StratagemListView()
	if len(views) != len(all) {
		t.Errorf("view count %d != %d", len(views), len(all))
	}
	if views[0].Name != "anchor" || len(views[0].Steps) == 0 {
		t.Errorf("views should be sorted and carry steps: %+v", views[0])
	}
}
