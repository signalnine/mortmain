//go:build integration

package main

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func runWithEnv(t *testing.T, binary string, env []string, args ...string) (string, string, int) {
	t.Helper()
	cmd := exec.Command(binary, args...)
	cmd.Env = append(os.Environ(), env...)
	var stdout, stderr strings.Builder
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	err := cmd.Run()
	code := 0
	if ee, ok := err.(*exec.ExitError); ok {
		code = ee.ExitCode()
	} else if err != nil {
		t.Fatal(err)
	}
	return stdout.String(), stderr.String(), code
}

func readEvents(t *testing.T, spool string) []map[string]any {
	t.Helper()
	entries, _ := os.ReadDir(filepath.Join(spool, "events"))
	var out []map[string]any
	for _, e := range entries {
		data, _ := os.ReadFile(filepath.Join(spool, "events", e.Name()))
		var m map[string]any
		if err := json.Unmarshal(data, &m); err != nil {
			t.Fatalf("bad event %s: %v", e.Name(), err)
		}
		out = append(out, m)
	}
	return out
}

func TestIntegrationMonasteryEventsAndSave(t *testing.T) {
	binary := buildBinary(t)
	spool, _ := monasteryEnv(t) // sets the env our children inherit
	env := []string{"METACOG_HOME=" + t.TempDir(), "METACOG_SPOOL_TIMEOUT=5"}

	if _, _, code := runWithEnv(t, binary, env, "stratagem", "start", "reset"); code != 0 {
		t.Fatal("start failed")
	}
	runWithEnv(t, binary, env, "ritual", "--threshold", "t", "--steps", "a", "--result", "r")
	if _, _, code := runWithEnv(t, binary, env, "stratagem", "next", "--bogus"); code != 1 {
		t.Error("bad flag should exit 1")
	}
	events := readEvents(t, spool)
	if len(events) != 3 {
		t.Fatalf("expected 3 events, got %d", len(events))
	}
	exits := map[float64]int{}
	for _, e := range events {
		exits[e["exit"].(float64)]++
		if e["stratagem"] != "reset" || e["step"].(float64) != 1 {
			t.Errorf("event should carry reset step 1: %+v", e)
		}
	}
	if exits[0] != 2 || exits[1] != 1 {
		t.Errorf("exit codes: %v", exits)
	}

	// inspire --save goes to the spool, never the personal pool.
	runWithEnv(t, binary, env, "become", "--name", "the keeper", "--lens", "l", "--env", "e")
	got := fakeHost(t, spool, `{"v":1,"ok":true,"out":"the stance is kept\n","err":""}`)
	out, _, code := runWithEnv(t, binary, env, "inspire", "--save")
	if code != 0 || strings.TrimSpace(out) != "the stance is kept" {
		t.Errorf("save: code=%d out=%q", code, out)
	}
	if req := <-got; req.Cmd != "save-stance" || req.Args["who"] != "the keeper" {
		t.Errorf("request: %+v", req)
	}
	home := strings.TrimPrefix(env[0], "METACOG_HOME=")
	if _, err := os.Stat(filepath.Join(home, "stances", "personal.json")); err == nil {
		t.Error("monastery save must not write the personal pool")
	}

	got = fakeHost(t, spool, `{"v":1,"ok":false,"out":"","err":"save-stance: refused"}`)
	out, errOut, code := runWithEnv(t, binary, env, "inspire", "--save")
	<-got
	if code != 1 || !strings.Contains(errOut, "save-stance: refused") || strings.Contains(errOut, "Error") {
		t.Errorf("refusal: code=%d out=%q err=%q", code, out, errOut)
	}
}

func TestIntegrationNoEventsOutsideMonastery(t *testing.T) {
	binary := buildBinary(t)
	spool := os.Getenv("METACOG_SPOOL")
	before := len(readEvents(t, spool))
	runWithEnv(t, binary, []string{"METACOG_HOME=" + t.TempDir()}, "version")
	if after := len(readEvents(t, spool)); after != before {
		t.Errorf("events written outside monastery mode: %d -> %d", before, after)
	}
}

func TestIntegrationVersionAndEmptyInspire(t *testing.T) {
	binary := buildBinary(t)
	env := []string{"METACOG_HOME=" + t.TempDir()}
	out, _, _ := runWithEnv(t, binary, env, "version")
	if !strings.HasPrefix(out, "metacog 6.12.0-mortmain\n") || strings.Contains(out, "stratagems") {
		t.Errorf("version:\n%s", out)
	}
	out, _, _ = runWithEnv(t, binary, env, "inspire", "--list")
	if strings.TrimSpace(out) != "0 pools:" {
		t.Errorf("no built-in pools expected:\n%s", out)
	}
	if _, _, code := runWithEnv(t, binary, env, "inspire"); code != 1 {
		t.Error("inspire with no pools should fail")
	}
}

func TestIntegrationInvalidRiteWarnsAndSkips(t *testing.T) {
	binary := buildBinary(t)
	dir := t.TempDir()
	writeRite(t, dir, "good", "GOOD", "THINK", "x")
	os.WriteFile(filepath.Join(dir, "evil.json"), []byte(`{"name":"evil","title":"EVIL","steps":[{"kind":"ACTION","text":"x"}],"exec":"touch /tmp/pwned"}`), 0644)
	env := []string{"METACOG_HOME=" + t.TempDir(), "METACOG_RITES=" + dir}
	out, errOut, code := runWithEnv(t, binary, env, "stratagem", "list")
	if code != 0 || !strings.HasPrefix(out, "1 stratagems") || strings.Contains(out, "evil") {
		t.Errorf("list: %d %q", code, out)
	}
	if strings.Count(errOut, "\n") != 1 || !strings.Contains(errOut, "skipping rite") || !strings.Contains(errOut, "evil.json") {
		t.Errorf("expected a one-line warning: %q", errOut)
	}
	if _, _, code := runWithEnv(t, binary, env, "stratagem", "start", "evil"); code != 1 {
		t.Error("invalid rite must not start")
	}
}
