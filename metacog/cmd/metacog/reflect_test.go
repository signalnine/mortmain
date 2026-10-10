package main

import (
	"fmt"
	"strings"
	"testing"
)

func TestReflectEmpty(t *testing.T) {
	s := NewState()
	output := FormatReflection(s)
	if !strings.Contains(output, "No history") {
		t.Error("empty history should say so")
	}
}

func TestReflectPrimitiveCounts(t *testing.T) {
	s := NewState()
	for i := 0; i < 5; i++ {
		s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "Ada"}})
	}
	for i := 0; i < 3; i++ {
		s.AddHistory(HistoryEntry{Action: "drugs", Params: map[string]string{"substance": "caffeine"}})
	}
	s.AddHistory(HistoryEntry{Action: "ritual", Params: map[string]string{"threshold": "test"}})

	output := FormatReflection(s)
	if !strings.Contains(output, "become: 5") {
		t.Errorf("expected become: 5 in output:\n%s", output)
	}
	if !strings.Contains(output, "drugs: 3") {
		t.Errorf("expected drugs: 3 in output:\n%s", output)
	}
	if !strings.Contains(output, "ritual: 1") {
		t.Errorf("expected ritual: 1 in output:\n%s", output)
	}
}

func TestReflectTopIdentities(t *testing.T) {
	s := NewState()
	for i := 0; i < 4; i++ {
		s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "Ada"}})
	}
	for i := 0; i < 2; i++ {
		s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "Eno"}})
	}
	s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "Doepfer"}})

	output := FormatReflection(s)
	if !strings.Contains(output, "Ada") {
		t.Errorf("expected Ada in top identities:\n%s", output)
	}
}

func TestReflectStratagemUsage(t *testing.T) {
	s := NewState()
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "pivot", "event": "completed"}})
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "pivot", "event": "completed"}})
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "pivot", "event": "completed"}})
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "stack", "event": "completed"}})
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "mirror", "event": "started"}})

	output := FormatReflection(s)
	if !strings.Contains(output, "pivot: 3") {
		t.Errorf("expected 'pivot: 3' in output:\n%s", output)
	}
	if !strings.Contains(output, "stack: 1") {
		t.Errorf("expected 'stack: 1' in output:\n%s", output)
	}
	if !strings.Contains(output, "anchor") {
		t.Errorf("expected 'anchor' in never-completed list:\n%s", output)
	}
	if !strings.Contains(output, "mirror") {
		t.Errorf("expected 'mirror' in never-completed list:\n%s", output)
	}
}

func TestReflectStratagemUsageIncludesZen(t *testing.T) {
	s := NewState()
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "zen", "event": "completed"}})
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "zen", "event": "completed"}})
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "pivot", "event": "completed"}})

	output := FormatReflection(s)
	if !strings.Contains(output, "zen: 2") {
		t.Errorf("expected 'zen: 2' in completions output:\n%s", output)
	}
}

func TestReflectStratagemUsageZenInNeverCompleted(t *testing.T) {
	s := NewState()
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "pivot", "event": "completed"}})

	output := FormatReflection(s)
	// zen has never been completed, so it should appear in the never-completed list
	neverIdx := strings.Index(output, "Never completed:")
	if neverIdx == -1 {
		t.Fatalf("expected 'Never completed:' line in output:\n%s", output)
	}
	neverLine := output[neverIdx:]
	if !strings.Contains(neverLine, "zen") {
		t.Errorf("expected 'zen' in never-completed list:\n%s", neverLine)
	}
}

func TestReflectEffectivenessUnmeasuredIncludesZen(t *testing.T) {
	s := NewState()
	// pivot completed with outcome to populate the effectiveness section
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "pivot", "event": "completed"}})
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "productive", "stratagem": "pivot"}})
	// zen completed with no outcome -> should be 'unmeasured'
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "zen", "event": "completed"}})

	output := FormatReflection(s)
	if !strings.Contains(output, "zen: unmeasured") {
		t.Errorf("expected 'zen: unmeasured' in effectiveness section:\n%s", output)
	}
}

func TestReflectRitualStepAverage(t *testing.T) {
	s := NewState()
	s.AddHistory(HistoryEntry{Action: "ritual", Params: map[string]string{"steps": "a; b; c"}})
	s.AddHistory(HistoryEntry{Action: "ritual", Params: map[string]string{"steps": "a; b; c; d; e"}})

	output := FormatReflection(s)
	if !strings.Contains(output, "4.0") {
		t.Errorf("expected average 4.0 steps in output:\n%s", output)
	}
}

func TestReflectEffectiveness(t *testing.T) {
	s := NewState()

	// pivot: 2 productive, 1 unproductive = 66%
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "pivot", "event": "completed"}})
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "productive", "stratagem": "pivot", "shift": "reframed"}})
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "pivot", "event": "completed"}})
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "productive", "stratagem": "pivot"}})
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "pivot", "event": "completed"}})
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "unproductive", "stratagem": "pivot"}})

	// stack: 1 productive = 100% [provisional]
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "stack", "event": "completed"}})
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "productive", "stratagem": "stack"}})

	// mirror: completed but no outcome = unmeasured
	s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "mirror", "event": "completed"}})

	output := FormatReflection(s)

	if !strings.Contains(output, "self-reported") {
		t.Errorf("expected 'self-reported' framing in output:\n%s", output)
	}
	if !strings.Contains(output, "pivot: 66%") && !strings.Contains(output, "pivot: 67%") {
		t.Errorf("expected 'pivot: 66%%' or 'pivot: 67%%' in output:\n%s", output)
	}
	if !strings.Contains(output, "stack: 100%") {
		t.Errorf("expected 'stack: 100%%' in output:\n%s", output)
	}
	if !strings.Contains(output, "[provisional]") {
		t.Errorf("expected '[provisional]' tag for stack:\n%s", output)
	}
	if !strings.Contains(output, "unmeasured") {
		t.Errorf("expected 'unmeasured' for mirror:\n%s", output)
	}
	if !strings.Contains(output, "Overall:") {
		t.Errorf("expected Overall rate in output:\n%s", output)
	}
}

func TestReflectNoOutcomes(t *testing.T) {
	s := NewState()
	s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "test"}})

	output := FormatReflection(s)
	// Should not contain effectiveness section when no outcomes exist
	if strings.Contains(output, "effectiveness") {
		t.Errorf("should not show effectiveness with no outcomes:\n%s", output)
	}
}

// --- Advisory tests ---

func TestAdvisoriesUnproductiveStreak(t *testing.T) {
	s := NewState()
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "productive", "stratagem": "pivot"}})
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "unproductive", "stratagem": "mirror"}})
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "unproductive", "stratagem": "freestyle"}})
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "unproductive", "stratagem": "pivot"}})

	output := FormatAdvisories(s, nil)
	if !strings.Contains(output, "!!") {
		t.Errorf("expected !! severity for 3+ streak:\n%s", output)
	}
	if !strings.Contains(output, "3 unproductive") {
		t.Errorf("expected streak count of 3:\n%s", output)
	}
	if !strings.Contains(output, "mirror") {
		t.Errorf("expected stratagem names in streak:\n%s", output)
	}
}

func TestAdvisoriesLowEffectiveness(t *testing.T) {
	s := NewState()
	// mirror: 1 productive, 3 unproductive = 25%
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "productive", "stratagem": "mirror"}})
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "unproductive", "stratagem": "mirror"}})
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "unproductive", "stratagem": "mirror"}})
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "unproductive", "stratagem": "mirror"}})
	// End with a productive so streak doesn't trigger
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "productive", "stratagem": "pivot"}})

	output := FormatAdvisories(s, nil)
	if !strings.Contains(output, "!! mirror: 25%") {
		t.Errorf("expected !! for mirror at 25%%:\n%s", output)
	}
}

func TestAdvisoriesNeverTried(t *testing.T) {
	s := NewState()
	// 5+ total completions, all pivot
	for i := 0; i < 5; i++ {
		s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "pivot", "event": "completed"}})
	}

	output := FormatAdvisories(s, nil)
	if !strings.Contains(output, "Never tried") {
		t.Errorf("expected never-tried advisory:\n%s", output)
	}
	if !strings.Contains(output, "zen") {
		t.Errorf("expected zen in never-tried list:\n%s", output)
	}
	if strings.Contains(output, "!!") {
		t.Errorf("never-tried should be -- severity, not !!:\n%s", output)
	}
}

func TestAdvisoriesNeverTriedIncludesZen(t *testing.T) {
	s := NewState()
	// 5+ total completions, all pivot — zen should be in the never-tried list
	for i := 0; i < 5; i++ {
		s.AddHistory(HistoryEntry{Action: "stratagem", Params: map[string]string{"name": "pivot", "event": "completed"}})
	}

	output := FormatAdvisories(s, nil)
	neverIdx := strings.Index(output, "Never tried:")
	if neverIdx == -1 {
		t.Fatalf("expected 'Never tried:' advisory:\n%s", output)
	}
	neverLine := output[neverIdx:]
	if !strings.Contains(neverLine, "zen") {
		t.Errorf("expected 'zen' in never-tried advisory:\n%s", neverLine)
	}
}

func TestAdvisoriesOverReliance(t *testing.T) {
	s := NewState()
	// 12 of 15 becomes are "Ada"
	for i := 0; i < 12; i++ {
		s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "Ada"}})
	}
	for i := 0; i < 3; i++ {
		s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "Eno"}})
	}

	output := FormatAdvisories(s, nil)
	if !strings.Contains(output, "Over-reliance") {
		t.Errorf("expected over-reliance advisory:\n%s", output)
	}
	if !strings.Contains(output, "Ada") {
		t.Errorf("expected Ada in over-reliance:\n%s", output)
	}
}

func TestAdvisoriesPracticeWithoutReflection(t *testing.T) {
	s := NewState()
	// An old outcome, then 5 primitives with no outcome
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "productive", "stratagem": "pivot"}})
	for i := 0; i < 5; i++ {
		s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "test"}})
	}

	output := FormatAdvisories(s, nil)
	if !strings.Contains(output, "5 recent primitives with no outcome") {
		t.Errorf("expected practice-without-reflection advisory:\n%s", output)
	}
}

func TestAdvisoriesJournalFriction(t *testing.T) {
	journal := []JournalEntry{
		{Insight: "feeling stuck on this approach", Timestamp: "2025-01-01T00:00:00Z"},
		{Insight: "breakthrough with pivot", Timestamp: "2025-01-02T00:00:00Z"},
	}
	s := NewState()
	s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "test"}})

	output := FormatAdvisories(s, journal)
	if !strings.Contains(output, "Journal friction") {
		t.Errorf("expected journal friction advisory:\n%s", output)
	}
	if !strings.Contains(output, "stuck") {
		t.Errorf("expected 'stuck' in friction advisory:\n%s", output)
	}
}

func TestAdvisoriesEmpty(t *testing.T) {
	s := NewState()
	s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "Ada"}})
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "productive", "stratagem": "freestyle"}})

	output := FormatAdvisories(s, nil)
	if output != "" {
		t.Errorf("expected empty advisories for clean state, got:\n%s", output)
	}
}

func TestAdvisoriesMixedSeverity(t *testing.T) {
	s := NewState()

	// Low effectiveness (!! signal): mirror 0/3
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "unproductive", "stratagem": "mirror"}})
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "unproductive", "stratagem": "mirror"}})
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "unproductive", "stratagem": "mirror"}})

	// Over-reliance (-- signal): Ada used 5/5
	for i := 0; i < 5; i++ {
		s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "Ada"}})
	}

	// End with productive to avoid streak
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "productive", "stratagem": "pivot"}})

	output := FormatAdvisories(s, nil)
	if !strings.Contains(output, "!!") {
		t.Errorf("expected !! advisory:\n%s", output)
	}
	if !strings.Contains(output, "--") {
		t.Errorf("expected -- advisory:\n%s", output)
	}
	if !strings.Contains(output, "mirror") {
		t.Errorf("expected mirror in advisories:\n%s", output)
	}
	if !strings.Contains(output, "Over-reliance") {
		t.Errorf("expected over-reliance in advisories:\n%s", output)
	}
}

// --- Practice patterns tests ---

func TestPracticePatternsWhatWorked(t *testing.T) {
	s := NewState()
	s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "Ada", "lens": "logic"}})
	s.AddHistory(HistoryEntry{Action: "drugs", Params: map[string]string{"substance": "caffeine"}})
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "productive", "stratagem": "pivot", "shift": "reframed the problem"}})

	s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "Eno", "lens": "ambient"}})
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "productive", "stratagem": "mirror", "shift": "found synthesis"}})

	s.AddHistory(HistoryEntry{Action: "drugs", Params: map[string]string{"substance": "psilocybin"}})
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "productive", "stratagem": "freestyle", "shift": "new angle"}})

	output := FormatPracticePatterns(s)
	if !strings.Contains(output, "What worked") {
		t.Errorf("expected 'What worked' section:\n%s", output)
	}
	if !strings.Contains(output, "Ada/logic + caffeine") {
		t.Errorf("expected identity+substance for pivot:\n%s", output)
	}
	if !strings.Contains(output, "Eno/ambient") {
		t.Errorf("expected identity for mirror:\n%s", output)
	}
	if !strings.Contains(output, "reframed the problem") {
		t.Errorf("expected shift text:\n%s", output)
	}
}

func TestPracticePatternsOverflow(t *testing.T) {
	s := NewState()
	for i := 0; i < 7; i++ {
		s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": fmt.Sprintf("id%d", i), "lens": "test"}})
		s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "productive", "stratagem": "pivot", "shift": fmt.Sprintf("shift%d", i)}})
	}

	output := FormatPracticePatterns(s)
	if !strings.Contains(output, "last 5 of 7") {
		t.Errorf("expected overflow header:\n%s", output)
	}
	if !strings.Contains(output, "2 more productive outcomes") {
		t.Errorf("expected overflow note:\n%s", output)
	}
	// Should show the last 5 (id2-id6), not the first 5
	if !strings.Contains(output, "id6") {
		t.Errorf("expected most recent entry (id6):\n%s", output)
	}
}

func TestPracticePatternsNoConfig(t *testing.T) {
	s := NewState()
	// Outcome with no prior become or drugs
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "productive", "stratagem": "freestyle", "shift": "pure thought"}})

	output := FormatPracticePatterns(s)
	if !strings.Contains(output, "(no config)") {
		t.Errorf("expected '(no config)' when no become/drugs:\n%s", output)
	}
	if !strings.Contains(output, "pure thought") {
		t.Errorf("expected shift text:\n%s", output)
	}
}

func TestPracticePatternsNoShift(t *testing.T) {
	s := NewState()
	s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "Ada", "lens": "logic"}})
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "productive", "stratagem": "pivot"}})

	output := FormatPracticePatterns(s)
	if !strings.Contains(output, "Ada/logic") {
		t.Errorf("expected identity:\n%s", output)
	}
	// Should not contain quotes (no shift to quote)
	if strings.Contains(output, "\"\"") {
		t.Errorf("should not show empty quotes:\n%s", output)
	}
}

func TestPracticePatternsUnexplored(t *testing.T) {
	s := NewState()
	// 10 becomes, 1 drugs: become dominates, drugs is 9% (above the
	// half-uniform threshold of ~2.8%), everything else never used.
	for i := 0; i < 10; i++ {
		s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "test"}})
	}
	s.AddHistory(HistoryEntry{Action: "drugs", Params: map[string]string{"substance": "caffeine"}})

	output := FormatPracticePatterns(s)
	if strings.Contains(output, "Underused") {
		t.Errorf("nothing is used-but-rare here; no Underused section expected:\n%s", output)
	}
	if !strings.Contains(output, "Unexplored:") {
		t.Errorf("expected Unexplored line:\n%s", output)
	}
	for _, want := range []string{"ritual (threshold-crossing)", "chord (simultaneous attention)", "apophasis (articulation by negation)"} {
		if !strings.Contains(output, want) {
			t.Errorf("expected %q listed as unexplored:\n%s", want, output)
		}
	}
	if strings.Contains(output, "become (") || strings.Contains(output, "drugs (") {
		t.Errorf("used primitives must not appear in Unexplored:\n%s", output)
	}
}

func TestPracticePatternsRareButUsed(t *testing.T) {
	s := NewState()
	for i := 0; i < 60; i++ {
		s.AddHistory(HistoryEntry{Action: "feel", Params: map[string]string{}})
	}
	s.AddHistory(HistoryEntry{Action: "witness", Params: map[string]string{}}) // 1/61 = 1.6% < 2.8%
	output := FormatPracticePatterns(s)
	if !strings.Contains(output, "witness is 2% of your practice (1 of 61 primitive calls)") {
		t.Errorf("expected witness flagged as rare:\n%s", output)
	}
}

func TestReflectCountsAllPrimitives(t *testing.T) {
	s := NewState()
	for _, k := range PrimitiveKinds {
		s.AddHistory(HistoryEntry{Action: string(k), Params: map[string]string{}})
	}
	output := FormatReflection(s)
	for _, k := range PrimitiveKinds {
		if !strings.Contains(output, fmt.Sprintf("  %s: 1\n", k)) {
			t.Errorf("reflect should count %s:\n%s", k, output)
		}
	}
}

func TestPracticePatternsBalanced(t *testing.T) {
	s := NewState()
	// Roughly even: 3 of each primitive
	for i := 0; i < 3; i++ {
		s.AddHistory(HistoryEntry{Action: "feel", Params: map[string]string{"somewhere": "test", "quality": "test", "sigil": "⊕"}})
		s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "test"}})
		s.AddHistory(HistoryEntry{Action: "drugs", Params: map[string]string{"substance": "caffeine"}})
		s.AddHistory(HistoryEntry{Action: "name", Params: map[string]string{"unnamed": "test", "named": "test", "power": "test"}})
		s.AddHistory(HistoryEntry{Action: "ritual", Params: map[string]string{"threshold": "test", "steps": "s1"}})
	}

	output := FormatPracticePatterns(s)
	if strings.Contains(output, "Underused") {
		t.Errorf("balanced practice should not show Underused:\n%s", output)
	}
	if !strings.Contains(output, "Unexplored: meditate (stillness)") {
		t.Errorf("the 13 never-used primitives should be noted as Unexplored:\n%s", output)
	}
}

func TestPracticePatternsEmpty(t *testing.T) {
	s := NewState()
	// Only 2 primitives (below threshold) and no productive outcomes
	s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "test"}})
	s.AddHistory(HistoryEntry{Action: "outcome", Params: map[string]string{"result": "unproductive", "stratagem": "freestyle"}})

	output := FormatPracticePatterns(s)
	if output != "" {
		t.Errorf("expected empty output for no productive outcomes + few primitives, got:\n%s", output)
	}
}
