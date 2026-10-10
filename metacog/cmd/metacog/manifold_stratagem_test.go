package main

import (
	"strings"
	"testing"
)

// THE MANIFOLD chains fork into synthesis and locks via ritual.
// It is the structural-axis champion among stratagems and the
// progenitor of chorus + trinity (which extend it with cross-domain becomes).
func TestManifoldChainsForkAndSynthesis(t *testing.T) {
	def, ok := LoadRite("manifold")
	if !ok {
		t.Fatal("rite \"manifold\" not loadable")
	}
	if def.Name != "THE MANIFOLD" {
		t.Errorf("Name: want %q, got %q", "THE MANIFOLD", def.Name)
	}
	hasFork, hasSynthesis := false, false
	for _, step := range def.Steps {
		if step.Kind == StepFork {
			hasFork = true
		}
		if step.Kind == StepSynthesis {
			hasSynthesis = true
		}
	}
	if !hasFork || !hasSynthesis {
		t.Errorf("THE MANIFOLD must chain fork + synthesis; hasFork=%v hasSynthesis=%v", hasFork, hasSynthesis)
	}
}

func TestStartManifoldStratagem(t *testing.T) {
	s := NewState()
	out, err := StartStratagem(s, "manifold", false)
	if err != nil {
		t.Fatalf("StartStratagem(\"manifold\") returned error: %v", err)
	}
	if s.Stratagem == nil {
		t.Fatal("StartStratagem(\"manifold\"): state.Stratagem is nil after start")
	}
	if !strings.Contains(out, "THE MANIFOLD") {
		t.Errorf("StartStratagem(\"manifold\") output should contain display name; got: %s", out)
	}
}
