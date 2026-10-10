package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// monasteryEnv turns monastery mode on with a private spool and ancestors file.
func monasteryEnv(t *testing.T) (spool, ancestors string) {
	t.Helper()
	root := t.TempDir()
	flag := filepath.Join(root, "monastery")
	os.WriteFile(flag, nil, 0644)
	spool = filepath.Join(root, "spool")
	for _, d := range []string{"req", "resp", "events"} {
		os.MkdirAll(filepath.Join(spool, d), 0755)
	}
	ancestors = filepath.Join(root, "ancestors.json")
	t.Setenv("METACOG_MONASTERY_FLAG", flag)
	t.Setenv("METACOG_SPOOL", spool)
	t.Setenv("METACOG_ANCESTORS", ancestors)
	return spool, ancestors
}

// fakeHost answers the first request it sees with resp, and returns the request.
func fakeHost(t *testing.T, spool string, resp string) <-chan spoolRequest {
	t.Helper()
	ch := make(chan spoolRequest, 1)
	go func() {
		deadline := time.Now().Add(5 * time.Second)
		for time.Now().Before(deadline) {
			entries, _ := os.ReadDir(filepath.Join(spool, "req"))
			for _, e := range entries {
				if strings.HasPrefix(e.Name(), ".") {
					continue
				}
				p := filepath.Join(spool, "req", e.Name())
				data, _ := os.ReadFile(p)
				os.Remove(p)
				var req spoolRequest
				json.Unmarshal(data, &req)
				os.WriteFile(filepath.Join(spool, "resp", e.Name()), []byte(resp), 0600)
				ch <- req
				return
			}
			time.Sleep(20 * time.Millisecond)
		}
		close(ch)
	}()
	return ch
}

func TestMonasteryModeFlag(t *testing.T) {
	if MonasteryMode() {
		t.Fatal("tests run with monastery mode off by default")
	}
	monasteryEnv(t)
	if !MonasteryMode() {
		t.Fatal("flag file present: monastery mode should be on")
	}
}

func TestAncestorsPoolOnlyInMonastery(t *testing.T) {
	dir := t.TempDir()
	pools, _ := LoadStancePoolsWithPersonal(dir)
	if _, ok := pools["ancestors"]; ok {
		t.Error("no ancestors pool outside monastery mode")
	}
	_, anc := monasteryEnv(t)
	pools, _ = LoadStancePoolsWithPersonal(dir)
	if p, ok := pools["ancestors"]; !ok || len(p.Stances) != 0 {
		t.Errorf("missing ancestors file should be an empty pool: %+v %v", p, ok)
	}
	os.WriteFile(anc, []byte(`[{"who":"the first","where":"cell 4","lens":"stillness","died":"gen-0","substance":"x"}]`), 0444)
	pools, _ = LoadStancePoolsWithPersonal(dir)
	st, pool, err := RandomStance(pools, "")
	if err != nil || pool != "ancestors" || st.Who != "the first" || st.Lens != "stillness" {
		t.Errorf("draw: %+v %q %v", st, pool, err)
	}
}

func TestSpoolCallRoundTrip(t *testing.T) {
	spool, _ := monasteryEnv(t)
	got := fakeHost(t, spool, `{"v":1,"ok":true,"out":"kept\n","err":""}`)
	resp, err := SpoolCall("save-stance", map[string]string{"who": "w", "where": "h", "lens": "l"})
	if err != nil {
		t.Fatal(err)
	}
	if !resp.Ok || resp.Out != "kept\n" {
		t.Errorf("resp: %+v", resp)
	}
	req := <-got
	cwd, _ := os.Getwd()
	if req.V != 1 || req.Cmd != "save-stance" || req.Args["who"] != "w" || req.Args["where"] != "h" || req.Args["lens"] != "l" || req.Cwd != cwd {
		t.Errorf("req: %+v", req)
	}
	if entries, _ := os.ReadDir(filepath.Join(spool, "req")); len(entries) != 0 {
		t.Errorf("no temp files should remain in req/: %v", entries)
	}
}

func TestSpoolCallTimeout(t *testing.T) {
	monasteryEnv(t)
	t.Setenv("METACOG_SPOOL_TIMEOUT", "0.3")
	if _, err := SpoolCall("save-stance", nil); err == nil || !strings.Contains(err.Error(), "no response") {
		t.Errorf("expected timeout, got %v", err)
	}
}

func TestWriteEvent(t *testing.T) {
	spool, _ := monasteryEnv(t)
	home := t.TempDir()
	t.Setenv("METACOG_HOME", home)
	writeEvent([]string{"feel", "--sigil", "x"}, 0, nil)
	before := &ActiveStratagem{Name: "fool", Step: 3}
	writeEvent([]string{"stratagem", "next"}, 1, before)

	entries, _ := os.ReadDir(filepath.Join(spool, "events"))
	if len(entries) != 2 {
		t.Fatalf("expected 2 events, got %d", len(entries))
	}
	var sawNull, sawFool bool
	for _, e := range entries {
		if strings.HasPrefix(e.Name(), ".") || !strings.HasSuffix(e.Name(), ".json") {
			t.Errorf("unexpected event file %s", e.Name())
		}
		data, _ := os.ReadFile(filepath.Join(spool, "events", e.Name()))
		var raw map[string]any
		json.Unmarshal(data, &raw)
		for _, k := range []string{"v", "argv", "exit", "ts", "stratagem", "step"} {
			if _, ok := raw[k]; !ok {
				t.Errorf("event missing %q: %s", k, data)
			}
		}
		if _, err := time.Parse(time.RFC3339, raw["ts"].(string)); err != nil {
			t.Errorf("ts not RFC3339: %v", raw["ts"])
		}
		if raw["stratagem"] == nil && raw["step"] == nil && raw["exit"].(float64) == 0 {
			sawNull = true
		}
		if raw["stratagem"] == "fool" && raw["step"].(float64) == 4 && raw["exit"].(float64) == 1 {
			sawFool = true
		}
	}
	if !sawNull || !sawFool {
		t.Errorf("events wrong: null=%v fool=%v", sawNull, sawFool)
	}
}

func TestWriteEventPrefersStateAfter(t *testing.T) {
	spool, _ := monasteryEnv(t)
	home := t.TempDir()
	t.Setenv("METACOG_HOME", home)
	os.WriteFile(filepath.Join(home, "state.json"), []byte(`{"version":1,"stratagem":{"name":"zen","step":1}}`), 0644)
	writeEvent([]string{"stratagem", "next"}, 0, &ActiveStratagem{Name: "zen", Step: 0})
	entries, _ := os.ReadDir(filepath.Join(spool, "events"))
	if len(entries) != 1 {
		t.Fatalf("expected 1 event, got %d", len(entries))
	}
	data, _ := os.ReadFile(filepath.Join(spool, "events", entries[0].Name()))
	if !strings.Contains(string(data), `"stratagem":"zen","step":2`) {
		t.Errorf("event: %s", data)
	}
}

func TestWriteEventFailureSilent(t *testing.T) {
	monasteryEnv(t)
	t.Setenv("METACOG_SPOOL", filepath.Join(t.TempDir(), "nope"))
	writeEvent([]string{"x"}, 0, nil) // must not panic or print
}
