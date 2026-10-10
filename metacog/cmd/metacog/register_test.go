package main

import (
	"strings"
	"testing"
)

func TestRegisterValidatesRequired(t *testing.T) {
	cases := []struct {
		name      string
		from      string
		to        string
		rationale string
	}{
		{"missing_from", "", "vernacular", "to land softer"},
		{"missing_to", "academic", "", "to land softer"},
		{"missing_rationale", "academic", "vernacular", ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if err := validateRegister(tc.from, tc.to, tc.rationale); err == nil {
				t.Errorf("expected validation error for %s", tc.name)
			}
		})
	}
}

func TestRegisterOutputContainsBothRegisters(t *testing.T) {
	out := formatRegister("academic", "vernacular", "to land softer")
	if !strings.Contains(out, "academic") {
		t.Error("output should contain --from value")
	}
	if !strings.Contains(out, "vernacular") {
		t.Error("output should contain --to value")
	}
	if !strings.Contains(out, "to land softer") {
		t.Error("output should contain rationale")
	}
}

func TestRegisterAppendsHistory(t *testing.T) {
	s := NewState()
	applyRegister(s, "academic", "vernacular", "to land softer")
	if len(s.History) != 1 {
		t.Fatalf("expected 1 history entry, got %d", len(s.History))
	}
	h := s.History[0]
	if h.Action != "register" {
		t.Errorf("expected action 'register', got %q", h.Action)
	}
	if h.Params["from"] != "academic" {
		t.Errorf("expected from=academic, got %q", h.Params["from"])
	}
	if h.Params["to"] != "vernacular" {
		t.Errorf("expected to=vernacular, got %q", h.Params["to"])
	}
	if h.Params["rationale"] != "to land softer" {
		t.Errorf("expected rationale stored, got %q", h.Params["rationale"])
	}
}

func TestRegisterDoesNotChangeIdentity(t *testing.T) {
	s := NewState()
	s.Identity = &Identity{Name: "test-id", Lens: "x", Env: "y"}
	applyRegister(s, "academic", "vernacular", "to land softer")
	if s.Identity == nil || s.Identity.Name != "test-id" {
		t.Errorf("register must not modify state.Identity; got %+v", s.Identity)
	}
}
