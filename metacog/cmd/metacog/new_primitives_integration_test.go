package main

import "testing"

func TestStepKindsForStructuralPrimitives(t *testing.T) {
	cases := map[StepKind]string{
		StepCounterfactual: "counterfactual",
		StepSynthesis:      "synthesis",
		StepFork:           "fork",
	}
	for got, want := range cases {
		if string(got) != want {
			t.Errorf("StepKind for %s: got %q, want %q", want, string(got), want)
		}
	}
}

func TestValidatePrimitiveAdvancesStructuralPrimitives(t *testing.T) {
	for _, primitive := range []string{"counterfactual", "synthesis", "fork"} {
		t.Run(primitive, func(t *testing.T) {
			s := NewState()
			s.Stratagem = &ActiveStratagem{
				Name: "pivot",
				Step: 0,
			}
			s.Stratagem.Name = "__test_" + primitive
			s.Stratagem.Title = "TEST"
			s.Stratagem.Steps = []Step{{StepKind(primitive), "test step"}}
			ValidatePrimitiveForStratagem(s, primitive)
			if len(s.Stratagem.StepsCompleted) != 1 {
				t.Errorf("%s did not advance stratagem step (StepsCompleted=%v)", primitive, s.Stratagem.StepsCompleted)
			}
		})
	}
}

func TestOutcomeFreestyleStructuralPrimitives(t *testing.T) {
	for _, primitive := range []string{"counterfactual", "synthesis", "fork"} {
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
