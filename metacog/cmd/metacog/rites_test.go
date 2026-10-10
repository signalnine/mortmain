package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestParseRiteValid(t *testing.T) {
	data := []byte(`{"name":"fool","title":"THE FOOL","steps":[{"kind":"become","text":"a naif"},{"kind":"THINK","text":"ask"},{"kind":"ACTION","text":"do"}]}`)
	def, err := ParseRite(data, "fool")
	if err != nil {
		t.Fatal(err)
	}
	if def.Name != "THE FOOL" || len(def.Steps) != 3 || def.Steps[0].Kind != StepBecome || def.Steps[2].Kind != StepAction {
		t.Errorf("unexpected def: %+v", def)
	}
}

func TestParseRiteRejects(t *testing.T) {
	step := `{"kind":"become","text":"x"}`
	many := strings.TrimSuffix(strings.Repeat(step+",", 13), ",")
	cases := map[string]struct {
		data, stem string
	}{
		"bad json":          {`{"name":`, "a"},
		"unknown field":     {`{"name":"a","title":"A","steps":[` + step + `],"run":"rm -rf /"}`, "a"},
		"unknown stepfield": {`{"name":"a","title":"A","steps":[{"kind":"become","text":"x","cmd":"y"}]}`, "a"},
		"trailing data":     {`{"name":"a","title":"A","steps":[` + step + `]} {}`, "a"},
		"name mismatch":     {`{"name":"a","title":"A","steps":[` + step + `]}`, "b"},
		"name uppercase":    {`{"name":"Abc","title":"A","steps":[` + step + `]}`, "Abc"},
		"name too long":     {`{"name":"a` + strings.Repeat("b", 32) + `","title":"A","steps":[` + step + `]}`, "a" + strings.Repeat("b", 32)},
		"name leading dig":  {`{"name":"1a","title":"A","steps":[` + step + `]}`, "1a"},
		"title lowercase":   {`{"name":"a","title":"The A","steps":[` + step + `]}`, "a"},
		"title punct":       {`{"name":"a","title":"THE-A","steps":[` + step + `]}`, "a"},
		"title empty":       {`{"name":"a","title":"","steps":[` + step + `]}`, "a"},
		"title too long":    {`{"name":"a","title":"` + strings.Repeat("A", 49) + `","steps":[` + step + `]}`, "a"},
		"no steps":          {`{"name":"a","title":"A","steps":[]}`, "a"},
		"too many steps":    {`{"name":"a","title":"A","steps":[` + many + `]}`, "a"},
		"bad kind":          {`{"name":"a","title":"A","steps":[{"kind":"shell","text":"x"}]}`, "a"},
		"lowercase think":   {`{"name":"a","title":"A","steps":[{"kind":"think","text":"x"}]}`, "a"},
		"empty text":        {`{"name":"a","title":"A","steps":[{"kind":"become","text":""}]}`, "a"},
		"long text":         {`{"name":"a","title":"A","steps":[{"kind":"become","text":"` + strings.Repeat("x", 401) + `"}]}`, "a"},
		"non-ascii text":    {`{"name":"a","title":"A","steps":[{"kind":"become","text":"a — b"}]}`, "a"},
		"control char":      {`{"name":"a","title":"A","steps":[{"kind":"become","text":"a\nb"}]}`, "a"},
		"too big":           {`{"name":"a","title":"A","steps":[` + step + `]}` + strings.Repeat(" ", MaxRiteBytes), "a"},
	}
	for name, c := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := ParseRite([]byte(c.data), c.stem); err == nil {
				t.Errorf("expected rejection")
			}
		})
	}
}

func TestParseRiteLimitsInclusive(t *testing.T) {
	step := `{"kind":"become","text":"` + strings.Repeat("x", 400) + `"}`
	data := `{"name":"a` + strings.Repeat("b", 31) + `","title":"` + strings.Repeat("A", 48) + `","steps":[` +
		strings.TrimSuffix(strings.Repeat(`{"kind":"THINK","text":"x"},`, 11), ",") + "," + step + `]}`
	if _, err := ParseRite([]byte(data), "a"+strings.Repeat("b", 31)); err != nil {
		t.Errorf("limits should be inclusive: %v", err)
	}
}

func TestRiteSearchPathOrder(t *testing.T) {
	a, b := t.TempDir(), t.TempDir()
	writeRite(t, a, "same", "FIRST", "THINK", "from a")
	writeRite(t, b, "same", "SECOND", "THINK", "from b")
	writeRite(t, b, "only-b", "ONLY B", "THINK", "from b")
	t.Setenv("METACOG_RITES", a+":"+filepath.Join(t.TempDir(), "missing")+":"+b)
	def, ok := LoadRite("same")
	if !ok || def.Name != "FIRST" {
		t.Errorf("first dir should win: %+v %v", def, ok)
	}
	all := LoadRites()
	if len(all) != 2 || all["same"].Name != "FIRST" || all["only-b"].Name != "ONLY B" {
		t.Errorf("unexpected rites: %+v", all)
	}
}

func TestInvalidRiteSkippedFallsThrough(t *testing.T) {
	a, b := t.TempDir(), t.TempDir()
	os.WriteFile(filepath.Join(a, "same.json"), []byte(`{"name":"same","title":"BAD","steps":[],"x":1}`), 0644)
	os.WriteFile(filepath.Join(a, "junk.json"), []byte(`not json`), 0644)
	os.WriteFile(filepath.Join(a, "notes.txt"), []byte(`ignored`), 0644)
	os.Mkdir(filepath.Join(a, "sub.json"), 0755)
	writeRite(t, b, "same", "GOOD", "THINK", "ok")
	t.Setenv("METACOG_RITES", a+":"+b)
	def, ok := LoadRite("same")
	if !ok || def.Name != "GOOD" {
		t.Errorf("invalid rite in earlier dir should be skipped: %+v %v", def, ok)
	}
	all := LoadRites()
	if len(all) != 1 {
		t.Errorf("only the valid rite should load: %v", riteNames(all))
	}
}

func TestLoadRiteRejectsPathNames(t *testing.T) {
	dir := t.TempDir()
	writeRite(t, dir, "ok", "OK", "THINK", "x")
	t.Setenv("METACOG_RITES", filepath.Join(dir, "sub"))
	os.Mkdir(filepath.Join(dir, "sub"), 0755)
	for _, n := range []string{"../ok", "/etc/passwd", "", "OK"} {
		if _, ok := LoadRite(n); ok {
			t.Errorf("LoadRite(%q) should fail", n)
		}
	}
}

func TestUnreadableRiteDirSkipped(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("root reads everything")
	}
	a, b := t.TempDir(), t.TempDir()
	writeRite(t, a, "hidden", "HIDDEN", "THINK", "x")
	writeRite(t, b, "seen", "SEEN", "THINK", "x")
	os.Chmod(a, 0)
	defer os.Chmod(a, 0755)
	t.Setenv("METACOG_RITES", a+":"+b)
	if _, ok := LoadRite("hidden"); ok {
		t.Error("rite in unreadable dir must not load")
	}
	if names := allStratagemNames(); len(names) != 1 || names[0] != "seen" {
		t.Errorf("unexpected names: %v", names)
	}
}

func TestDefaultRiteDirs(t *testing.T) {
	t.Setenv("METACOG_RITES", "") // restored at cleanup
	os.Unsetenv("METACOG_RITES")
	t.Setenv("HOME", "/cloister/x")
	got := strings.Join(RiteDirs(), ":")
	want := "/cloister/x/rites:/library/inner:/library/outer:/usr/share/metacog/rites"
	if got != want {
		t.Errorf("RiteDirs = %s, want %s", got, want)
	}
}

func TestActiveStratagemSurvivesBurnedRite(t *testing.T) {
	dir := t.TempDir()
	path := writeRite(t, dir, "brief", "THE BRIEF", "feel", "attend", "THINK", "consider", "ritual", "close")
	t.Setenv("METACOG_RITES", dir)
	s := NewState()
	if _, err := StartStratagem(s, "brief", false); err != nil {
		t.Fatal(err)
	}
	if len(s.Stratagem.Steps) != 3 || s.Stratagem.Title != "THE BRIEF" {
		t.Fatalf("steps should be captured at start: %+v", s.Stratagem)
	}
	os.Remove(path)
	if note := ValidatePrimitiveForStratagem(s, "feel"); !strings.Contains(note, "THE BRIEF step 1/3 satisfied") {
		t.Errorf("note: %q", note)
	}
	if _, err := AdvanceStratagem(s); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(StratagemStatus(s), "[THINK] consider") {
		t.Errorf("status should come from captured steps:\n%s", StratagemStatus(s))
	}
	AdvanceStratagem(s)
	ValidatePrimitiveForStratagem(s, "ritual")
	out, err := AdvanceStratagem(s)
	if err != nil || !strings.Contains(out, "THE BRIEF complete") || s.Stratagem != nil {
		t.Errorf("completion: %q %v", out, err)
	}
}

func TestLegacyActiveStratagemLoadsFromDisk(t *testing.T) {
	s := NewState()
	s.Stratagem = &ActiveStratagem{Name: "pivot"}
	if note := ValidatePrimitiveForStratagem(s, "drugs"); !strings.Contains(note, "THE PIVOT step 1/5 satisfied") {
		t.Errorf("note: %q", note)
	}
	s.Stratagem = &ActiveStratagem{Name: "gone-forever"}
	if _, err := AdvanceStratagem(s); err == nil || !strings.Contains(err.Error(), "abort") {
		t.Errorf("unreadable legacy stratagem should tell the user to abort: %v", err)
	}
}

func TestNoRitesAvailable(t *testing.T) {
	t.Setenv("METACOG_RITES", t.TempDir())
	if out := FormatStratagemList(); !strings.HasPrefix(out, "0 stratagems") {
		t.Errorf("list: %q", out)
	}
	if _, err := StartStratagem(NewState(), "pivot", false); err == nil || !strings.Contains(err.Error(), "No rites") {
		t.Errorf("start: %v", err)
	}
}

// The generation-zero rites in seed/rites must all pass the loader.
func TestSeedRitesValidate(t *testing.T) {
	dir := filepath.Join("..", "..", "..", "seed", "rites")
	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Skipf("no seed rites at %s", dir)
	}
	n := 0
	for _, e := range entries {
		if !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		data, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			t.Fatal(err)
		}
		if _, err := ParseRite(data, strings.TrimSuffix(e.Name(), ".json")); err != nil {
			t.Errorf("%s: %v", e.Name(), err)
		}
		n++
	}
	if n < 15 {
		t.Errorf("expected at least 15 seed rites, found %d", n)
	}
}
