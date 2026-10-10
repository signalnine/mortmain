package main

import (
	"strings"
	"testing"
)

func TestOutcomeRecordsResult(t *testing.T) {
	s := NewState()
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "pivot", "event": "completed"}})

	err := RecordOutcome(s, "productive", "reframed the problem")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Find outcome entry
	found := false
	for _, h := range s.History {
		if h.Action == "outcome" {
			found = true
			if h.Params["result"] != "productive" {
				t.Errorf("expected result=productive, got %s", h.Params["result"])
			}
			if h.Params["shift"] != "reframed the problem" {
				t.Errorf("expected shift text, got %s", h.Params["shift"])
			}
			if h.Params["stratagem"] != "pivot" {
				t.Errorf("expected stratagem=pivot, got %s", h.Params["stratagem"])
			}
		}
	}
	if !found {
		t.Error("outcome entry not found in history")
	}
}

func TestOutcomeUnproductive(t *testing.T) {
	s := NewState()
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "manifold", "event": "completed"}})

	err := RecordOutcome(s, "unproductive", "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	for _, h := range s.History {
		if h.Action == "outcome" {
			if h.Params["result"] != "unproductive" {
				t.Errorf("expected unproductive, got %s", h.Params["result"])
			}
			if h.Params["shift"] != "" {
				t.Errorf("expected empty shift, got %s", h.Params["shift"])
			}
			if h.Params["stratagem"] != "manifold" {
				t.Errorf("expected stratagem=manifold, got %s", h.Params["stratagem"])
			}
		}
	}
}

func TestOutcomeAutoCaptures(t *testing.T) {
	s := NewState()
	// Multiple stratagems — should capture the most recent
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "pivot", "event": "completed"}})
	s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "test"}})
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "mirror", "event": "completed"}})

	err := RecordOutcome(s, "productive", "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	for _, h := range s.History {
		if h.Action == "outcome" {
			if h.Params["stratagem"] != "mirror" {
				t.Errorf("expected mirror (most recent), got %s", h.Params["stratagem"])
			}
		}
	}
}

func TestOutcomeFreestyle(t *testing.T) {
	s := NewState()
	// Freestyle: primitives without a stratagem
	s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "Ada"}})
	s.AddHistory(HistoryEntry{Action: "drugs", Params: map[string]string{"substance": "caffeine"}})

	err := RecordOutcome(s, "productive", "reframed via freestyle")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	found := false
	for _, h := range s.History {
		if h.Action == "outcome" {
			found = true
			if h.Params["stratagem"] != "freestyle" {
				t.Errorf("expected stratagem=freestyle, got %s", h.Params["stratagem"])
			}
			if h.Params["result"] != "productive" {
				t.Errorf("expected result=productive, got %s", h.Params["result"])
			}
			if h.Params["shift"] != "reframed via freestyle" {
				t.Errorf("expected shift text, got %s", h.Params["shift"])
			}
		}
	}
	if !found {
		t.Error("outcome entry not found in history")
	}
}

func TestOutcomeFreestyleFeel(t *testing.T) {
	s := NewState()
	s.AddHistory(HistoryEntry{Action: "feel", Params: map[string]string{"somewhere": "chest", "quality": "tight", "sigil": "knot"}})

	err := RecordOutcome(s, "productive", "attended to the felt sense")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	found := false
	for _, h := range s.History {
		if h.Action == "outcome" {
			found = true
			if h.Params["stratagem"] != "freestyle" {
				t.Errorf("expected stratagem=freestyle, got %s", h.Params["stratagem"])
			}
		}
	}
	if !found {
		t.Error("outcome entry not found in history")
	}
}

func TestOutcomeFreestyleName(t *testing.T) {
	s := NewState()
	s.AddHistory(HistoryEntry{Action: "name", Params: map[string]string{"unnamed": "the hum", "named": "Resonance", "power": "invocation"}})

	err := RecordOutcome(s, "productive", "found the true name")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	found := false
	for _, h := range s.History {
		if h.Action == "outcome" {
			found = true
			if h.Params["stratagem"] != "freestyle" {
				t.Errorf("expected stratagem=freestyle, got %s", h.Params["stratagem"])
			}
		}
	}
	if !found {
		t.Error("outcome entry not found in history")
	}
}

func TestOutcomeFreestyleAfterStratagem(t *testing.T) {
	s := NewState()
	// Completed stratagem with outcome already recorded
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "pivot", "event": "started"}})
	s.AddHistory(HistoryEntry{Action: "drugs", Params: map[string]string{"substance": "test"}})
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "pivot", "event": "completed"}})
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "productive", "stratagem": "pivot"}})
	// Then freestyle primitives
	s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "Ada"}})

	err := RecordOutcome(s, "unproductive", "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Should be a freestyle outcome, not duplicate stratagem
	outcomeCount := 0
	for _, h := range s.History {
		if h.Action == "outcome" {
			outcomeCount++
			if outcomeCount == 2 {
				if h.Params["stratagem"] != "freestyle" {
					t.Errorf("expected second outcome as freestyle, got %s", h.Params["stratagem"])
				}
			}
		}
	}
	if outcomeCount != 2 {
		t.Errorf("expected 2 outcomes, got %d", outcomeCount)
	}
}

func TestOutcomeNoPrimitives(t *testing.T) {
	s := NewState()
	// Empty history — no primitives at all

	err := RecordOutcome(s, "productive", "")
	if err == nil {
		t.Error("expected error when no primitives or stratagems")
	}
}

func TestOutcomeFreestyleIgnoresStratagemPrimitives(t *testing.T) {
	s := NewState()
	// Primitives inside a stratagem span should not count as freestyle
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "pivot", "event": "started"}})
	s.AddHistory(HistoryEntry{Action: "drugs", Params: map[string]string{"substance": "test"}})
	s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "test"}})
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "pivot", "event": "completed"}})
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "productive", "stratagem": "pivot"}})

	err := RecordOutcome(s, "productive", "")
	if err == nil {
		t.Error("expected error — no freestyle primitives outside stratagem")
	}
}

func TestOutcomeDuplicate(t *testing.T) {
	s := NewState()
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "pivot", "event": "completed"}})

	RecordOutcome(s, "productive", "first")

	err := RecordOutcome(s, "unproductive", "second")
	if err == nil {
		t.Error("expected error on duplicate outcome")
	}
	if !strings.Contains(err.Error(), "already recorded") {
		t.Errorf("expected 'already recorded' error, got: %v", err)
	}
}

func TestOutcomeAmend(t *testing.T) {
	s := NewState()
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "pivot", "event": "completed"}})
	RecordOutcome(s, "productive", "initial assessment")

	err := AmendOutcome(s, "unproductive", "on reflection, no real shift")
	if err != nil {
		t.Fatalf("amend failed: %v", err)
	}

	// Find the outcome — should be updated
	for _, h := range s.History {
		if h.Action == "outcome" {
			if h.Params["result"] != "unproductive" {
				t.Errorf("expected amended result=unproductive, got %s", h.Params["result"])
			}
			if h.Params["shift"] != "on reflection, no real shift" {
				t.Errorf("expected amended shift, got %s", h.Params["shift"])
			}
		}
	}
}

func TestOutcomeAmendNoExisting(t *testing.T) {
	s := NewState()
	err := AmendOutcome(s, "productive", "nothing to amend")
	if err == nil {
		t.Error("expected error when no outcome to amend")
	}
}

func TestOutcomeInvalidResult(t *testing.T) {
	s := NewState()
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "pivot", "event": "completed"}})

	err := RecordOutcome(s, "maybe", "")
	if err == nil {
		t.Error("expected error for invalid result value")
	}
}

// TestOutcomeAttachmentAllPrimitives enumerates every primitive listed in
// main.go's version string and verifies that a freestyle invocation of that
// primitive can have an outcome attached. Regression guard for metacog-6m6:
// witness and apophasis were added in v6.7.0 but findLastPrimitive's switch
// was not updated, so outcome recording silently failed for those primitives.
// If you add a primitive to main.go's version string, add it here AND to the
// switch in findLastPrimitive (cmd/metacog/outcome.go).
func TestOutcomeAttachmentAllPrimitives(t *testing.T) {
	primitives := []string{
		"feel", "drugs", "become", "name", "ritual", "meditate",
		"counterfactual", "synthesis", "fork",
		"register", "chord", "silence", "excerpt", "commitment", "disjunction", "glossolalia",
		"witness", "apophasis",
	}
	for _, p := range primitives {
		t.Run(p, func(t *testing.T) {
			s := NewState()
			s.AddHistory(HistoryEntry{Action: p, Params: map[string]string{}})

			if err := RecordOutcome(s, "productive", ""); err != nil {
				t.Fatalf("RecordOutcome failed for primitive %q: %v -- if %q was recently added, also add it to findLastPrimitive's case list in outcome.go", p, err, p)
			}

			found := false
			for _, h := range s.History {
				if h.Action == "outcome" {
					found = true
					if h.Params["stratagem"] != "freestyle" {
						t.Errorf("expected stratagem=freestyle for primitive %q, got %s", p, h.Params["stratagem"])
					}
				}
			}
			if !found {
				t.Errorf("no outcome entry recorded for primitive %q", p)
			}
		})
	}
}

func TestRecordOutcomeAlreadyMarkedMessageNamesStratagem(t *testing.T) {
	s := NewState()
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "pivot", "event": "completed"}})
	if err := RecordOutcome(s, "productive", ""); err != nil {
		t.Fatal(err)
	}
	err := RecordOutcome(s, "productive", "")
	if err == nil {
		t.Fatal("second outcome with nothing new should fail")
	}
	if !strings.Contains(err.Error(), "pivot") || !strings.Contains(err.Error(), "--amend") {
		t.Errorf("error should name the stratagem and suggest --amend: %v", err)
	}
}
