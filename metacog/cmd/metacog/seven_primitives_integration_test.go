package main

import (
	"strings"
	"testing"
)

// The seven new primitives must each have a dedicated StepKind constant
// whose string value matches the primitive name.
func TestStepKindsForSevenPrimitives(t *testing.T) {
	cases := map[StepKind]string{
		StepRegister:    "register",
		StepChord:       "chord",
		StepSilence:     "silence",
		StepExcerpt:     "excerpt",
		StepCommitment:  "commitment",
		StepDisjunction: "disjunction",
		StepGlossolalia: "glossolalia",
	}
	for got, want := range cases {
		if string(got) != want {
			t.Errorf("StepKind for %s: got %q, want %q", want, string(got), want)
		}
	}
}

// Each new primitive must advance an active stratagem step when its kind matches.
func TestValidatePrimitiveAdvancesSevenPrimitives(t *testing.T) {
	for _, primitive := range []string{"register", "chord", "silence", "excerpt", "commitment", "disjunction", "glossolalia"} {
		t.Run(primitive, func(t *testing.T) {
			s := NewState()
			s.Stratagem = &ActiveStratagem{
				Name:  "__test_" + primitive,
				Step:  0,
				Title: "TEST",
				Steps: []Step{{StepKind(primitive), "test step"}},
			}
			ValidatePrimitiveForStratagem(s, primitive)
			if len(s.Stratagem.StepsCompleted) != 1 {
				t.Errorf("%s did not advance stratagem step (StepsCompleted=%v)", primitive, s.Stratagem.StepsCompleted)
			}
		})
	}
}

// Each new primitive must be eligible for freestyle-outcome attachment.
func TestOutcomeFreestyleSevenPrimitives(t *testing.T) {
	for _, primitive := range []string{"register", "chord", "silence", "excerpt", "commitment", "disjunction", "glossolalia"} {
		t.Run(primitive, func(t *testing.T) {
			s := NewState()
			s.AddHistory(HistoryEntry{Action: primitive, Params: map[string]string{"k": "v"}})

			if err := RecordOutcome(s, "productive", ""); err != nil {
				t.Fatalf("RecordOutcome failed for %s: %v", primitive, err)
			}

			found := false
			for _, h := range s.History {
				if h.Action == "outcome" {
					found = true
					if h.Params["stratagem"] != "freestyle" {
						t.Errorf("%s: expected stratagem=freestyle, got %s", primitive, h.Params["stratagem"])
					}
				}
			}
			if !found {
				t.Errorf("%s: outcome entry not recorded", primitive)
			}
		})
	}
}

// Version output must list every new primitive.
func TestVersionListsSevenPrimitives(t *testing.T) {
	expected := "primitives: feel drugs become name ritual meditate counterfactual synthesis fork register chord silence excerpt commitment disjunction glossolalia"
	for _, name := range []string{"register", "chord", "silence", "excerpt", "commitment", "disjunction", "glossolalia"} {
		if !strings.Contains(expected, name) {
			t.Errorf("expected version line to contain %q", name)
		}
	}
}
