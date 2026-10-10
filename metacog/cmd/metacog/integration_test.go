//go:build integration

package main

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func buildBinary(t *testing.T) string {
	t.Helper()
	binary := filepath.Join(t.TempDir(), "metacog")
	cmd := exec.Command("go", "build", "-o", binary, "./cmd/metacog")
	// Run from repo root
	cmd.Dir = filepath.Join(".", "..", "..")
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("build failed: %v\n%s", err, out)
	}
	return binary
}

func runMetacog(t *testing.T, binary, stateDir string, args ...string) (string, error) {
	t.Helper()
	cmd := exec.Command(binary, args...)
	cmd.Env = append(os.Environ(), "METACOG_HOME="+stateDir)
	out, err := cmd.CombinedOutput()
	return string(out), err
}

func TestIntegrationFullPivot(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()

	// Start pivot
	out, err := runMetacog(t, binary, stateDir, "stratagem", "start", "pivot")
	if err != nil {
		t.Fatalf("start pivot: %v\n%s", err, out)
	}

	// Call drugs
	_, err = runMetacog(t, binary, stateDir, "drugs", "--substance", "test", "--method", "test", "--qualia", "test")
	if err != nil {
		t.Fatalf("drugs: %v", err)
	}

	// Advance
	_, err = runMetacog(t, binary, stateDir, "stratagem", "next")
	if err != nil {
		t.Fatalf("next after drugs: %v", err)
	}

	// THINK step — advance freely
	_, err = runMetacog(t, binary, stateDir, "stratagem", "next")
	if err != nil {
		t.Fatalf("next after THINK: %v", err)
	}

	// Call become
	_, err = runMetacog(t, binary, stateDir, "become", "--name", "test", "--lens", "test", "--env", "test")
	if err != nil {
		t.Fatalf("become: %v", err)
	}

	// Advance
	_, err = runMetacog(t, binary, stateDir, "stratagem", "next")
	if err != nil {
		t.Fatalf("next after become: %v", err)
	}

	// THINK step
	_, err = runMetacog(t, binary, stateDir, "stratagem", "next")
	if err != nil {
		t.Fatalf("next after THINK 2: %v", err)
	}

	// Call ritual
	_, err = runMetacog(t, binary, stateDir, "ritual", "--threshold", "test", "--steps", "s1", "--result", "test")
	if err != nil {
		t.Fatalf("ritual: %v", err)
	}

	// Final advance — should complete
	out, err = runMetacog(t, binary, stateDir, "stratagem", "next")
	if err != nil {
		t.Fatalf("final next: %v\n%s", err, out)
	}

	// Status should show no active stratagem
	out, err = runMetacog(t, binary, stateDir, "status")
	if err != nil {
		t.Fatalf("status: %v\n%s", err, out)
	}
}

func TestIntegrationStatePersistence(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()

	runMetacog(t, binary, stateDir, "become", "--name", "Ada", "--lens", "logic", "--env", "lab")

	out, err := runMetacog(t, binary, stateDir, "status")
	if err != nil {
		t.Fatalf("status: %v\n%s", err, out)
	}
	if !strings.Contains(out, "Ada") {
		t.Error("status should show Ada")
	}
}

func TestIntegrationReset(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()

	runMetacog(t, binary, stateDir, "become", "--name", "Ada", "--lens", "logic", "--env", "lab")
	runMetacog(t, binary, stateDir, "reset")

	out, _ := runMetacog(t, binary, stateDir, "status")
	if strings.Contains(out, "Ada") {
		t.Error("reset should clear identity")
	}
}

func TestIntegrationResetPreservesSession(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()

	// Start session, do work, reset, then end session
	out, err := runMetacog(t, binary, stateDir, "session", "start", "my-session")
	if err != nil {
		t.Fatalf("session start: %v\n%s", err, out)
	}

	runMetacog(t, binary, stateDir, "become", "--name", "Ada", "--lens", "logic", "--env", "lab")
	runMetacog(t, binary, stateDir, "reset")

	// Session end should still work after reset
	out, err = runMetacog(t, binary, stateDir, "session", "end")
	if err != nil {
		t.Fatalf("session end after reset should work: %v\n%s", err, out)
	}

	// History should still exist
	out, err = runMetacog(t, binary, stateDir, "history")
	if err != nil {
		t.Fatalf("history: %v\n%s", err, out)
	}
	if !strings.Contains(out, "Ada") {
		t.Errorf("history should survive reset:\n%s", out)
	}
}

func TestIntegrationRepair(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()

	// Corrupt state file
	os.MkdirAll(stateDir, 0755)
	os.WriteFile(filepath.Join(stateDir, "state.json"), []byte("corrupt{{{"), 0644)

	out, err := runMetacog(t, binary, stateDir, "repair")
	if err != nil {
		t.Fatalf("repair: %v\n%s", err, out)
	}
	if !strings.Contains(out, "Original preserved at") {
		t.Errorf("repair should report the backup: %s", out)
	}
	backups, _ := filepath.Glob(filepath.Join(stateDir, "state.corrupt.*"))
	if len(backups) != 1 {
		t.Errorf("expected one backup file, got %v", backups)
	}

	// Should work now
	_, err = runMetacog(t, binary, stateDir, "status")
	if err != nil {
		t.Fatalf("status after repair: %v", err)
	}
}

func TestIntegrationJSONOutput(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()

	out, err := runMetacog(t, binary, stateDir, "version", "--json")
	if err != nil {
		t.Fatalf("version --json: %v\n%s", err, out)
	}

	var parsed map[string]any
	if err := json.Unmarshal([]byte(strings.TrimSpace(out)), &parsed); err != nil {
		t.Errorf("not valid JSON: %v\noutput: %s", err, out)
	}
}

func TestIntegrationReflect(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()

	runMetacog(t, binary, stateDir, "become", "--name", "Ada", "--lens", "logic", "--env", "lab")
	runMetacog(t, binary, stateDir, "drugs", "--substance", "caffeine", "--method", "antagonism", "--qualia", "sharp")
	runMetacog(t, binary, stateDir, "ritual", "--threshold", "test", "--steps", "s1", "--steps", "s2", "--result", "done")

	out, err := runMetacog(t, binary, stateDir, "reflect")
	if err != nil {
		t.Fatalf("reflect: %v\n%s", err, out)
	}
	if !strings.Contains(out, "become: 1") {
		t.Errorf("reflect should show become count:\n%s", out)
	}
}

func TestIntegrationSession(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()

	out, err := runMetacog(t, binary, stateDir, "session", "start", "test-session")
	if err != nil {
		t.Fatalf("session start: %v\n%s", err, out)
	}

	runMetacog(t, binary, stateDir, "become", "--name", "Ada", "--lens", "logic", "--env", "lab")

	out, err = runMetacog(t, binary, stateDir, "session", "end")
	if err != nil {
		t.Fatalf("session end: %v\n%s", err, out)
	}

	out, err = runMetacog(t, binary, stateDir, "session", "list")
	if err != nil {
		t.Fatalf("session list: %v\n%s", err, out)
	}
	if !strings.Contains(out, "test-session") {
		t.Errorf("session list should contain 'test-session':\n%s", out)
	}

	out, err = runMetacog(t, binary, stateDir, "history", "--session", "test-session")
	if err != nil {
		t.Fatalf("history --session: %v\n%s", err, out)
	}
	if !strings.Contains(out, "Ada") {
		t.Errorf("filtered history should contain Ada:\n%s", out)
	}
}

func TestIntegrationInspireSave(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()

	runMetacog(t, binary, stateDir, "become", "--name", "Ada", "--lens", "logic", "--env", "lab")

	out, err := runMetacog(t, binary, stateDir, "inspire", "--save")
	if err != nil {
		t.Fatalf("inspire --save: %v\n%s", err, out)
	}
	if !strings.Contains(out, "Ada") {
		t.Errorf("save output should mention identity:\n%s", out)
	}

	out, err = runMetacog(t, binary, stateDir, "inspire", "--pool", "personal")
	if err != nil {
		t.Fatalf("inspire --pool personal: %v\n%s", err, out)
	}
	if !strings.Contains(out, "Ada") {
		t.Errorf("personal pool should contain Ada:\n%s", out)
	}
}

func TestIntegrationOutcome(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()

	// Complete a stratagem (use reset — shortest: ritual, THINK, ritual)
	runMetacog(t, binary, stateDir, "stratagem", "start", "reset")
	runMetacog(t, binary, stateDir, "ritual", "--threshold", "test", "--steps", "s1", "--result", "done")
	runMetacog(t, binary, stateDir, "stratagem", "next")
	runMetacog(t, binary, stateDir, "stratagem", "next") // THINK
	runMetacog(t, binary, stateDir, "ritual", "--threshold", "ground", "--steps", "s1", "--result", "done")
	runMetacog(t, binary, stateDir, "stratagem", "next") // completes

	// Record outcome
	out, err := runMetacog(t, binary, stateDir, "outcome", "--result", "productive", "--shift", "test shift")
	if err != nil {
		t.Fatalf("outcome: %v\n%s", err, out)
	}
	if !strings.Contains(out, "productive") {
		t.Errorf("outcome output should mention productive:\n%s", out)
	}

	// Reflect should show effectiveness
	out, err = runMetacog(t, binary, stateDir, "reflect")
	if err != nil {
		t.Fatalf("reflect: %v\n%s", err, out)
	}
	if !strings.Contains(out, "reset: 100%") {
		t.Errorf("reflect should show reset effectiveness:\n%s", out)
	}

	// Duplicate should fail
	_, err = runMetacog(t, binary, stateDir, "outcome", "--result", "unproductive")
	if err == nil {
		t.Error("expected error on duplicate outcome")
	}

	// Amend should work
	out, err = runMetacog(t, binary, stateDir, "outcome", "--amend", "--result", "unproductive")
	if err != nil {
		t.Fatalf("amend: %v\n%s", err, out)
	}
}

func TestIntegrationFreestyleOutcome(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()

	// Freestyle: just primitives, no stratagem
	runMetacog(t, binary, stateDir, "become", "--name", "Ada", "--lens", "logic", "--env", "lab")
	runMetacog(t, binary, stateDir, "drugs", "--substance", "caffeine", "--method", "antagonism", "--qualia", "sharp")

	// Record freestyle outcome
	out, err := runMetacog(t, binary, stateDir, "outcome", "--result", "productive", "--shift", "found new angle")
	if err != nil {
		t.Fatalf("freestyle outcome: %v\n%s", err, out)
	}
	if !strings.Contains(out, "freestyle") {
		t.Errorf("output should mention freestyle:\n%s", out)
	}

	// Reflect should show freestyle in effectiveness
	out, err = runMetacog(t, binary, stateDir, "reflect")
	if err != nil {
		t.Fatalf("reflect: %v\n%s", err, out)
	}
	if !strings.Contains(out, "freestyle") {
		t.Errorf("reflect should show freestyle effectiveness:\n%s", out)
	}
}

func TestIntegrationJournal(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()

	// Record an insight
	out, err := runMetacog(t, binary, stateDir, "journal", "identity shifts compound")
	if err != nil {
		t.Fatalf("journal: %v\n%s", err, out)
	}
	if !strings.Contains(out, "identity shifts compound") {
		t.Errorf("output should contain insight:\n%s", out)
	}

	// Record with tags
	out, err = runMetacog(t, binary, stateDir, "journal", "--tag", "practice", "--tag", "identity", "tagged insight")
	if err != nil {
		t.Fatalf("journal with tags: %v\n%s", err, out)
	}

	// List all
	out, err = runMetacog(t, binary, stateDir, "journal", "list")
	if err != nil {
		t.Fatalf("journal list: %v\n%s", err, out)
	}
	if !strings.Contains(out, "identity shifts compound") {
		t.Errorf("list should show first insight:\n%s", out)
	}
	if !strings.Contains(out, "tagged insight") {
		t.Errorf("list should show tagged insight:\n%s", out)
	}

	// Filter by tag
	out, err = runMetacog(t, binary, stateDir, "journal", "list", "--tag", "practice")
	if err != nil {
		t.Fatalf("journal list --tag: %v\n%s", err, out)
	}
	if strings.Contains(out, "identity shifts compound") {
		t.Errorf("filtered list should not show untagged insight:\n%s", out)
	}
	if !strings.Contains(out, "tagged insight") {
		t.Errorf("filtered list should show tagged insight:\n%s", out)
	}

	// List with --last
	out, err = runMetacog(t, binary, stateDir, "journal", "list", "--last", "1")
	if err != nil {
		t.Fatalf("journal list --last: %v\n%s", err, out)
	}
	if strings.Contains(out, "identity shifts compound") {
		t.Errorf("--last 1 should not show first insight:\n%s", out)
	}
}

func TestIntegrationJournalWithSession(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()

	// Start session, record insight
	runMetacog(t, binary, stateDir, "session", "start", "deep-dive")
	out, err := runMetacog(t, binary, stateDir, "journal", "session-tagged insight")
	if err != nil {
		t.Fatalf("journal in session: %v\n%s", err, out)
	}
	if !strings.Contains(out, "deep-dive") {
		t.Errorf("output should mention session:\n%s", out)
	}

	runMetacog(t, binary, stateDir, "session", "end")

	// Record without session
	runMetacog(t, binary, stateDir, "journal", "no-session insight")

	// Filter by session
	out, err = runMetacog(t, binary, stateDir, "journal", "list", "--session", "deep-dive")
	if err != nil {
		t.Fatalf("journal list --session: %v\n%s", err, out)
	}
	if !strings.Contains(out, "session-tagged") {
		t.Errorf("should contain session-tagged insight:\n%s", out)
	}
	if strings.Contains(out, "no-session") {
		t.Errorf("should not contain no-session insight:\n%s", out)
	}
}

func TestIntegrationJournalInReflect(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()

	// Add some history so reflect has content
	runMetacog(t, binary, stateDir, "become", "--name", "Ada", "--lens", "logic", "--env", "lab")

	// Record a journal entry
	runMetacog(t, binary, stateDir, "journal", "the pivot revealed a blind spot")

	// Reflect should include recent insights
	out, err := runMetacog(t, binary, stateDir, "reflect")
	if err != nil {
		t.Fatalf("reflect: %v\n%s", err, out)
	}
	if !strings.Contains(out, "Recent insights") {
		t.Errorf("reflect should show Recent insights section:\n%s", out)
	}
	if !strings.Contains(out, "blind spot") {
		t.Errorf("reflect should show journal entry:\n%s", out)
	}
}

func TestIntegrationAdvisories(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()

	// Build up 3 unproductive outcomes via freestyle
	runMetacog(t, binary, stateDir, "become", "--name", "Ada", "--lens", "logic", "--env", "lab")
	runMetacog(t, binary, stateDir, "outcome", "--result", "unproductive")

	runMetacog(t, binary, stateDir, "become", "--name", "Eno", "--lens", "ambient", "--env", "studio")
	runMetacog(t, binary, stateDir, "outcome", "--result", "unproductive")

	runMetacog(t, binary, stateDir, "become", "--name", "Doepfer", "--lens", "modular", "--env", "lab")
	runMetacog(t, binary, stateDir, "outcome", "--result", "unproductive")

	// Reflect should show advisories
	out, err := runMetacog(t, binary, stateDir, "reflect")
	if err != nil {
		t.Fatalf("reflect: %v\n%s", err, out)
	}
	if !strings.Contains(out, "Advisories:") {
		t.Errorf("reflect should contain Advisories section:\n%s", out)
	}
	if !strings.Contains(out, "!! 3 unproductive") {
		t.Errorf("reflect should flag 3 unproductive streak:\n%s", out)
	}
}

func TestIntegrationPracticePatterns(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()

	// Build productive outcomes with configs
	runMetacog(t, binary, stateDir, "become", "--name", "Ada", "--lens", "logic", "--env", "lab")
	runMetacog(t, binary, stateDir, "drugs", "--substance", "caffeine", "--method", "antagonism", "--qualia", "sharp")
	runMetacog(t, binary, stateDir, "outcome", "--result", "productive", "--shift", "reframed the problem")

	runMetacog(t, binary, stateDir, "become", "--name", "Eno", "--lens", "ambient", "--env", "studio")
	runMetacog(t, binary, stateDir, "outcome", "--result", "productive", "--shift", "found new angle")

	out, err := runMetacog(t, binary, stateDir, "reflect")
	if err != nil {
		t.Fatalf("reflect: %v\n%s", err, out)
	}
	if !strings.Contains(out, "Practice patterns:") {
		t.Errorf("reflect should contain Practice patterns section:\n%s", out)
	}
	if !strings.Contains(out, "What worked") {
		t.Errorf("reflect should contain What worked:\n%s", out)
	}
	if !strings.Contains(out, "Ada/logic") {
		t.Errorf("reflect should show identity config:\n%s", out)
	}
	if !strings.Contains(out, "reframed the problem") {
		t.Errorf("reflect should show shift text:\n%s", out)
	}
}

func TestIntegrationFeel(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()

	out, err := runMetacog(t, binary, stateDir, "feel", "--somewhere", "the chest", "--quality", "tight and warm", "--sigil", "⊕")
	if err != nil {
		t.Fatalf("feel: %v\n%s", err, out)
	}
	if !strings.Contains(out, "⊕") {
		t.Errorf("output should contain sigil:\n%s", out)
	}
	if !strings.Contains(out, "tight and warm") {
		t.Errorf("output should contain quality:\n%s", out)
	}
}

func TestIntegrationName(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()

	out, err := runMetacog(t, binary, stateDir, "name", "--unnamed", "the pressure", "--named", "The Weight", "--power", "seeing choice-cost")
	if err != nil {
		t.Fatalf("name: %v\n%s", err, out)
	}
	if !strings.Contains(out, "The Weight") {
		t.Errorf("output should contain named:\n%s", out)
	}
	if !strings.Contains(out, "seeing choice-cost") {
		t.Errorf("output should contain power:\n%s", out)
	}
}

func TestIntegrationResetConfirms(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()

	if _, err := runMetacog(t, binary, stateDir, "become", "--name", "Ada", "--lens", "logic", "--env", "lab"); err != nil {
		t.Fatalf("become: %v", err)
	}

	out, err := runMetacog(t, binary, stateDir, "reset")
	if err != nil {
		t.Fatalf("reset: %v\n%s", err, out)
	}
	if strings.TrimSpace(out) == "" {
		t.Errorf("reset should print a confirmation message on success, got empty output")
	}
	lower := strings.ToLower(out)
	if !strings.Contains(lower, "reset") && !strings.Contains(lower, "clear") {
		t.Errorf("reset output should indicate what happened, got: %q", out)
	}
}

func TestIntegrationExitCodes(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()

	// Missing required flag — exit code 1
	_, err := runMetacog(t, binary, stateDir, "become", "--name", "Ada")
	if err == nil {
		t.Error("expected error for missing flags")
	}

	// Stratagem error — no active stratagem
	_, err = runMetacog(t, binary, stateDir, "stratagem", "next")
	if err == nil {
		t.Error("expected error for next with no stratagem")
	}
}

func TestIntegrationErrorsDoNotDumpUsage(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()
	out, err := runMetacog(t, binary, stateDir, "stratagem", "next")
	if err == nil {
		t.Fatal("expected failure with no active stratagem")
	}
	if strings.Contains(out, "Usage:") {
		t.Errorf("errors should not dump usage:\n%s", out)
	}
	if !strings.Contains(out, "no active stratagem") {
		t.Errorf("error text missing:\n%s", out)
	}
}

func TestIntegrationWhitespaceOnlyFlagsRejected(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()
	out, err := runMetacog(t, binary, stateDir, "become", "--name", "  ", "--lens", "\t", "--env", " ")
	if err == nil {
		t.Fatalf("whitespace-only flags should be rejected:\n%s", out)
	}
	if !strings.Contains(out, "--name") || !strings.Contains(out, "blank") {
		t.Errorf("expected the blank flag to be named:\n%s", out)
	}
	// An explicitly empty optional flag is still allowed (meditate --focus "" = shikantaza).
	out, err = runMetacog(t, binary, stateDir, "meditate", "--release", "r", "--focus", "", "--duration", "d")
	if err != nil {
		t.Fatalf("explicit empty --focus must still be accepted:\n%s", out)
	}
	if !strings.Contains(out, "just sitting") {
		t.Errorf("empty focus should produce objectless output:\n%s", out)
	}
	// Inner whitespace is never touched: a fragment with leading spaces survives verbatim.
	out, err = runMetacog(t, binary, stateDir, "excerpt", "--source", "s", "--fragment", "  two leading spaces", "--why", "w")
	if err != nil || !strings.Contains(out, "  two leading spaces") {
		t.Errorf("flag values must not be altered: %v\n%s", err, out)
	}
}

func TestIntegrationPrimitiveExitsNonZeroWhenStateUnsaveable(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()
	os.MkdirAll(stateDir, 0755)
	os.WriteFile(filepath.Join(stateDir, "state.json"), []byte(`{"version": 99, "history": []}`), 0644)

	out, err := runMetacog(t, binary, stateDir, "feel", "--somewhere", "x", "--quality", "y", "--sigil", "z")
	if err == nil {
		t.Fatalf("primitive must exit non-zero when state cannot be saved:\n%s", out)
	}
	if !strings.Contains(out, "NOT recorded") {
		t.Errorf("error should say the event was not recorded:\n%s", out)
	}
	if !strings.Contains(out, "You are now attending to") {
		t.Errorf("output should still be rendered:\n%s", out)
	}
}

func TestIntegrationStratagemNoteOnStderr(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()
	if _, err := runMetacog(t, binary, stateDir, "stratagem", "start", "pivot"); err != nil {
		t.Fatal(err)
	}
	out, err := runMetacog(t, binary, stateDir, "drugs", "--substance", "s", "--method", "m", "--qualia", "q")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out, "step 1/5 satisfied") {
		t.Errorf("expected stratagem note:\n%s", out)
	}
	out, _ = runMetacog(t, binary, stateDir, "feel", "--somewhere", "x", "--quality", "y", "--sigil", "z")
	if !strings.Contains(out, "recorded as freestyle") {
		t.Errorf("expected off-script note:\n%s", out)
	}
}

func TestIntegrationStructuredJSON(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()
	runMetacog(t, binary, stateDir, "feel", "--somewhere", "x", "--quality", "y", "--sigil", "z")
	runMetacog(t, binary, stateDir, "stratagem", "start", "pivot")

	var status struct {
		SessionID string `json:"session_id"`
		Stratagem *struct {
			Name  string `json:"name"`
			Step  int    `json:"step"`
			Total int    `json:"total"`
			Steps []struct {
				Kind  string `json:"kind"`
				State string `json:"state"`
			} `json:"steps"`
		} `json:"stratagem"`
	}
	out, _ := runMetacog(t, binary, stateDir, "status", "--json")
	if err := json.Unmarshal([]byte(strings.TrimSpace(out)), &status); err != nil {
		t.Fatalf("status --json: %v\n%s", err, out)
	}
	if status.SessionID == "" || status.Stratagem == nil || status.Stratagem.Name != "pivot" || status.Stratagem.Total != 5 || status.Stratagem.Steps[0].State != "current" {
		t.Errorf("unexpected status view: %+v", status)
	}

	var history []struct {
		Action string            `json:"action"`
		Params map[string]string `json:"params"`
	}
	out, _ = runMetacog(t, binary, stateDir, "history", "--json")
	if err := json.Unmarshal([]byte(strings.TrimSpace(out)), &history); err != nil {
		t.Fatalf("history --json: %v\n%s", err, out)
	}
	if len(history) != 2 || history[0].Action != "feel" || history[0].Params["somewhere"] != "x" {
		t.Errorf("unexpected history view: %+v", history)
	}

	// --session filter applies to JSON too; empty result is [] not null.
	out, _ = runMetacog(t, binary, stateDir, "history", "--json", "--session", "nope")
	if strings.TrimSpace(out) != "[]" {
		t.Errorf("filtered-empty history --json should be []:\n%s", out)
	}
	empty := t.TempDir()
	out, _ = runMetacog(t, binary, empty, "history", "--json")
	if strings.TrimSpace(out) != "[]" {
		t.Errorf("empty history --json should be []:\n%s", out)
	}

	// No pools are built in; seed the personal pool so inspire has a draw.
	poolDir := t.TempDir()
	runMetacog(t, binary, poolDir, "become", "--name", "w", "--lens", "l", "--env", "e")
	runMetacog(t, binary, poolDir, "inspire", "--save")
	var stance struct{ Pool, Who, Where, Lens string }
	out, _ = runMetacog(t, binary, poolDir, "inspire", "--json")
	if err := json.Unmarshal([]byte(strings.TrimSpace(out)), &stance); err != nil {
		t.Fatalf("inspire --json: %v\n%s", err, out)
	}
	if stance.Pool == "" || stance.Who == "" || stance.Lens == "" {
		t.Errorf("unexpected stance view: %+v", stance)
	}

	var version struct {
		Version    string   `json:"version"`
		Primitives []string `json:"primitives"`
		Stratagems []string `json:"stratagems"`
	}
	out, _ = runMetacog(t, binary, stateDir, "version", "--json")
	if err := json.Unmarshal([]byte(strings.TrimSpace(out)), &version); err != nil {
		t.Fatalf("version --json: %v\n%s", err, out)
	}
	if version.Version != Version || len(version.Primitives) != len(PrimitiveKinds) || version.Stratagems != nil {
		t.Errorf("unexpected version view: %+v", version)
	}

	var ss struct {
		Stratagem *struct {
			Name string `json:"name"`
		} `json:"stratagem"`
	}
	out, _ = runMetacog(t, binary, stateDir, "stratagem", "status", "--json")
	if err := json.Unmarshal([]byte(strings.TrimSpace(out)), &ss); err != nil || ss.Stratagem == nil || ss.Stratagem.Name != "pivot" {
		t.Errorf("stratagem status --json: %v\n%s", err, out)
	}
}

func TestIntegrationStratagemListJSON(t *testing.T) {
	binary := buildBinary(t)
	stateDir := t.TempDir()
	var list []struct {
		Name  string   `json:"name"`
		Title string   `json:"title"`
		Steps []string `json:"steps"`
	}
	out, err := runMetacog(t, binary, stateDir, "stratagem", "list", "--json")
	if err != nil {
		t.Fatalf("stratagem list --json: %v\n%s", err, out)
	}
	if err := json.Unmarshal([]byte(strings.TrimSpace(out)), &list); err != nil {
		t.Fatalf("not valid JSON: %v\n%s", err, out)
	}
	if len(list) != len(fixtureRites) || list[0].Name != "anchor" || len(list[0].Steps) == 0 {
		t.Errorf("unexpected list view: %d entries, first %+v", len(list), list[0])
	}
	out, _ = runMetacog(t, binary, stateDir, "stratagem", "list")
	if !strings.HasPrefix(out, fmt.Sprintf("%d stratagems", len(fixtureRites))) {
		t.Errorf("text list should open with the count:\n%s", out)
	}
}
