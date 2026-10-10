package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

// Nothing is compiled in, so every test runs against rite files on disk.
// TestMain writes the fixture rites below to a temp dir and points
// METACOG_RITES at it. It also pins monastery mode off and the spool to a
// temp dir, so a host that happens to have /etc/metacog/monastery does not
// change test behaviour. Integration tests inherit this environment.

type fixtureStep struct{ kind, text string }

var fixtureRites = map[string]struct {
	title string
	steps []fixtureStep
}{
	"pivot": {"THE PIVOT", []fixtureStep{
		{"drugs", "Loosen categories, see shapes not names"},
		{"THINK", "What else has this shape?"},
		{"become", "Install the methodology as operating system"},
		{"THINK", "Apply the methodology to the original problem"},
		{"ritual", "Lock in methodology as default behavior"},
	}},
	"mirror": {"THE MIRROR", []fixtureStep{
		{"become", "Inhabit the strongest advocate of one position"},
		{"become", "Inhabit the strongest advocate of the opposing position"},
		{"THINK", "Where do they actually conflict?"},
		{"ritual", "Name the synthesis that transcends both frames"},
	}},
	"reset": {"THE RESET", []fixtureStep{
		{"ritual", "Name what you are letting go"},
		{"THINK", "What artifact survives the return?"},
		{"ritual", "Re-establish baseline with the artifact installed"},
	}},
	"anchor": {"THE ANCHOR", []fixtureStep{
		{"ritual", "Establish the clean room"},
		{"become", "Inhabit someone who can examine this"},
		{"ACTION", "The dangerous observation"},
		{"ritual", "Name the artifact, close the boundary, return"},
	}},
	"manifold": {"THE MANIFOLD", []fixtureStep{
		{"fork", "Declare parallel threads"},
		{"THINK", "Run each thread to its conclusion"},
		{"synthesis", "Treat surviving threads as lenses"},
		{"ritual", "Commit to what the suppressed tension reveals"},
	}},
	"zen": {"THE ZEN", []fixtureStep{
		{"meditate", "Sit. Release what clings."},
		{"THINK", "What surfaced in the silence?"},
		{"name", "Give the surfaced thing a single word"},
		{"ritual", "Return carrying the named thing"},
	}},
	"anchor-duo": {"THE ANCHOR DUO", []fixtureStep{
		{"commitment", "Pre-commit to two fixed points"},
		{"excerpt", "Pin fragment one"},
		{"excerpt", "Pin fragment two"},
		{"fork", "Open one thread per anchor"},
		{"ritual", "Lock the answer"},
	}},
	"chorus": {"THE CHORUS", []fixtureStep{
		{"become", "Inhabit voice one"},
		{"become", "Inhabit voice two"},
		{"become", "Inhabit voice three"},
		{"fork", "Open one thread per voice"},
		{"ritual", "Lock the multi-voice answer"},
	}},
}

// writeRite writes one rite file. Steps alternate kind, text.
func writeRite(t testing.TB, dir, name, title string, steps ...string) string {
	t.Helper()
	type st struct {
		Kind string `json:"kind"`
		Text string `json:"text"`
	}
	r := struct {
		Name  string `json:"name"`
		Title string `json:"title"`
		Steps []st   `json:"steps"`
	}{Name: name, Title: title}
	for i := 0; i+1 < len(steps); i += 2 {
		r.Steps = append(r.Steps, st{steps[i], steps[i+1]})
	}
	data, err := json.MarshalIndent(r, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(dir, name+".json")
	if err := os.WriteFile(path, data, 0644); err != nil {
		t.Fatal(err)
	}
	return path
}

func writeFixtureRites(dir string) error {
	for name, r := range fixtureRites {
		type st struct {
			Kind string `json:"kind"`
			Text string `json:"text"`
		}
		var steps []st
		for _, s := range r.steps {
			steps = append(steps, st{s.kind, s.text})
		}
		data, err := json.Marshal(map[string]any{"name": name, "title": r.title, "steps": steps})
		if err != nil {
			return err
		}
		if err := os.WriteFile(filepath.Join(dir, name+".json"), data, 0644); err != nil {
			return err
		}
	}
	return nil
}

// fixtureDef returns a fixture rite as a StratagemDef.
func fixtureDef(name string) StratagemDef {
	r := fixtureRites[name]
	def := StratagemDef{Name: r.title}
	for _, s := range r.steps {
		def.Steps = append(def.Steps, Step{StepKind(s.kind), s.text})
	}
	return def
}

func TestMain(m *testing.M) {
	tmp, err := os.MkdirTemp("", "metacog-test-")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	rites := filepath.Join(tmp, "rites")
	spool := filepath.Join(tmp, "spool")
	for _, d := range []string{rites, filepath.Join(spool, "req"), filepath.Join(spool, "resp"), filepath.Join(spool, "events")} {
		os.MkdirAll(d, 0755)
	}
	if err := writeFixtureRites(rites); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	os.Setenv("METACOG_RITES", rites)
	os.Setenv("METACOG_MONASTERY_FLAG", filepath.Join(tmp, "no-monastery"))
	os.Setenv("METACOG_SPOOL", spool)
	os.Setenv("METACOG_ANCESTORS", filepath.Join(tmp, "no-ancestors.json"))
	code := m.Run()
	os.RemoveAll(tmp)
	os.Exit(code)
}
