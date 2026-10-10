package main

import (
	"strings"
	"testing"
)

func TestSynthesisOutput(t *testing.T) {
	a := Lens{Name: "Keynesian liquidity preference", Verdict: "cut rates", Blindspot: "supply-side dynamics"}
	b := Lens{Name: "thermodynamic efficiency", Verdict: "cap throughput", Blindspot: "social acceptance"}
	c := Lens{Name: "ritual continuity", Verdict: "do nothing", Blindspot: "material constraints"}

	result := formatSynthesis("how to respond to the shortage", a, b, c, "growth requires the very throughput that destroys the substrate")

	for _, want := range []string{
		"PROBLEM: how to respond to the shortage",
		"[LENS A -- Keynesian liquidity preference]: cut rates",
		"BLIND TO: supply-side dynamics",
		"[LENS B -- thermodynamic efficiency]: cap throughput",
		"BLIND TO: social acceptance",
		"[LENS C -- ritual continuity]: do nothing",
		"BLIND TO: material constraints",
		"UNRESOLVED TENSION: growth requires the very throughput",
		"speak from each lens in order",
	} {
		if !strings.Contains(result, want) {
			t.Errorf("output missing %q\n--- got ---\n%s", want, result)
		}
	}
}

func TestSynthesisUpdatesState(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	s := NewState()
	a := Lens{Name: "an", Verdict: "av", Blindspot: "ab"}
	b := Lens{Name: "bn", Verdict: "bv", Blindspot: "bb"}
	c := Lens{Name: "cn", Verdict: "cv", Blindspot: "cb"}
	applySynthesis(s, "p", a, b, c, "tension")
	sm.Save(s)

	loaded, _ := sm.Load()
	if len(loaded.History) != 1 {
		t.Fatalf("expected 1 entry, got %d", len(loaded.History))
	}
	h := loaded.History[0]
	if h.Action != "synthesis" {
		t.Errorf("action: %s", h.Action)
	}
	checks := map[string]string{
		"problem":            "p",
		"lens_a_name":        "an",
		"lens_a_verdict":     "av",
		"lens_a_blindspot":   "ab",
		"lens_b_name":        "bn",
		"lens_b_verdict":     "bv",
		"lens_b_blindspot":   "bb",
		"lens_c_name":        "cn",
		"lens_c_verdict":     "cv",
		"lens_c_blindspot":   "cb",
		"suppressed_tension": "tension",
	}
	for k, v := range checks {
		if h.Params[k] != v {
			t.Errorf("%s: expected %q, got %q", k, v, h.Params[k])
		}
	}
}

func TestSynthesisValidatesRequired(t *testing.T) {
	a := Lens{Name: "an", Verdict: "av", Blindspot: "ab"}
	b := Lens{Name: "bn", Verdict: "bv", Blindspot: "bb"}
	c := Lens{Name: "cn", Verdict: "cv", Blindspot: "cb"}

	cases := []struct {
		name    string
		problem string
		a, b, c Lens
		tension string
	}{
		{"missing problem", "", a, b, c, "t"},
		{"missing tension", "p", a, b, c, ""},
		{"lens A name empty", "p", Lens{Verdict: "v", Blindspot: "b"}, b, c, "t"},
		{"lens B verdict empty", "p", a, Lens{Name: "n", Blindspot: "b"}, c, "t"},
		{"lens C blindspot empty", "p", a, b, Lens{Name: "n", Verdict: "v"}, "t"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := validateSynthesis(tc.problem, tc.a, tc.b, tc.c, tc.tension)
			if err == nil {
				t.Errorf("expected error for %s", tc.name)
			}
		})
	}
}
