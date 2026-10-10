package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
)

func TestNewState(t *testing.T) {
	s := NewState()
	if s.Version != StateSchemaVersion {
		t.Errorf("expected version %d, got %d", StateSchemaVersion, s.Version)
	}
	if s.SessionID == "" {
		t.Error("expected non-empty session ID")
	}
}

func TestSaveAndLoad(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	s := NewState()
	s.Identity = &Identity{Name: "Ada", Lens: "verification", Env: "lab"}

	err := sm.Save(s)
	if err != nil {
		t.Fatalf("save failed: %v", err)
	}

	loaded, err := sm.Load()
	if err != nil {
		t.Fatalf("load failed: %v", err)
	}
	if loaded.Identity == nil || loaded.Identity.Name != "Ada" {
		t.Error("identity not persisted")
	}
}

func TestAtomicWrite(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	s := NewState()
	err := sm.Save(s)
	if err != nil {
		t.Fatalf("save failed: %v", err)
	}

	// Temp file should not exist after save
	tmpPath := filepath.Join(dir, ".state.json.tmp")
	if _, err := os.Stat(tmpPath); !os.IsNotExist(err) {
		t.Error("temp file should not exist after save")
	}

	// State file should exist
	statePath := filepath.Join(dir, "state.json")
	if _, err := os.Stat(statePath); err != nil {
		t.Error("state file should exist after save")
	}
}

func TestLoadMissingFile(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	s, err := sm.Load()
	if err != nil {
		t.Fatalf("load of missing file should not error: %v", err)
	}
	if s.Version != StateSchemaVersion {
		t.Error("missing file should return fresh state")
	}
}

func TestLoadCorruptedFile(t *testing.T) {
	dir := t.TempDir()
	statePath := filepath.Join(dir, "state.json")
	os.WriteFile(statePath, []byte("not json{{{"), 0644)

	sm := NewStateManager(dir)
	_, err := sm.Load()
	if err == nil {
		t.Error("corrupted file should return error")
	}
}

func TestLoadFutureVersion(t *testing.T) {
	dir := t.TempDir()
	statePath := filepath.Join(dir, "state.json")
	data, _ := json.Marshal(map[string]any{"version": 999})
	os.WriteFile(statePath, data, 0644)

	sm := NewStateManager(dir)
	_, err := sm.Load()
	if err == nil {
		t.Error("future version should return error")
	}
}

func TestConcurrentAccess(t *testing.T) {
	dir := t.TempDir()
	var wg sync.WaitGroup

	for i := 0; i < 5; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			sm := NewStateManager(dir)
			s, _ := sm.Load()
			s.Identity = &Identity{Name: "writer", Lens: "concurrent", Env: "test"}
			sm.Save(s)
		}(i)
	}
	wg.Wait()

	// File should be valid JSON after concurrent writes
	sm := NewStateManager(dir)
	s, err := sm.Load()
	if err != nil {
		t.Fatalf("state corrupted after concurrent writes: %v", err)
	}
	if s.Identity == nil {
		t.Error("identity should be set")
	}
}

func TestHistoryRotation(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	s := NewState()
	for i := 0; i < 600; i++ {
		s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"i": "test"}})
	}

	if len(s.History) != 600 {
		t.Fatalf("expected 600 entries before save, got %d", len(s.History))
	}

	err := sm.Save(s)
	if err != nil {
		t.Fatalf("save failed: %v", err)
	}

	loaded, err := sm.Load()
	if err != nil {
		t.Fatalf("load failed: %v", err)
	}
	if len(loaded.History) > MaxHistoryEntries {
		t.Errorf("history should cap at %d, got %d", MaxHistoryEntries, len(loaded.History))
	}
}

func TestHistoryArchive(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	s := NewState()
	for i := 0; i < 510; i++ {
		s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"i": fmt.Sprintf("%d", i)}})
	}

	err := sm.Save(s)
	if err != nil {
		t.Fatalf("save failed: %v", err)
	}

	archivePath := filepath.Join(dir, "history-archive.jsonl")
	data, err := os.ReadFile(archivePath)
	if err != nil {
		t.Fatalf("archive file should exist: %v", err)
	}
	lines := strings.Split(strings.TrimSpace(string(data)), "\n")
	if len(lines) != 10 {
		t.Errorf("archive should have exactly 10 rotated entries, got %d", len(lines))
	}
}

func TestLoadHistoryArchiveMissing(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	entries, err := sm.LoadHistoryArchive()
	if err != nil {
		t.Fatalf("missing archive should not error: %v", err)
	}
	if entries != nil {
		t.Errorf("missing archive should return nil, got %v", entries)
	}
}

func TestLoadHistoryArchiveWithEntries(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	s := NewState()
	for i := 0; i < 503; i++ {
		s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"i": fmt.Sprintf("%d", i)}})
	}
	if err := sm.Save(s); err != nil {
		t.Fatalf("save failed: %v", err)
	}

	entries, err := sm.LoadHistoryArchive()
	if err != nil {
		t.Fatalf("load archive failed: %v", err)
	}
	if len(entries) != 3 {
		t.Errorf("expected 3 archived entries, got %d", len(entries))
	}
	if entries[0].Action != "become" || entries[0].Params["i"] != "0" {
		t.Errorf("archive entries out of order: first=%+v", entries[0])
	}
}

func TestLoadHistoryArchiveSkipsMalformedLines(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	archivePath := filepath.Join(dir, "history-archive.jsonl")
	good := `{"action":"become","params":{"name":"Ada"},"timestamp":"2024-01-01T00:00:00Z"}`
	bad := `not json`
	os.WriteFile(archivePath, []byte(good+"\n"+bad+"\n"+good+"\n"), 0644)

	entries, err := sm.LoadHistoryArchive()
	if err != nil {
		t.Fatalf("malformed lines should be skipped, not error: %v", err)
	}
	if len(entries) != 2 {
		t.Errorf("expected 2 valid entries, got %d", len(entries))
	}
}

func TestRepair(t *testing.T) {
	dir := t.TempDir()
	statePath := filepath.Join(dir, "state.json")
	os.WriteFile(statePath, []byte("corrupt"), 0644)

	sm := NewStateManager(dir)
	backup, err := sm.Repair()
	if err != nil {
		t.Fatalf("repair failed: %v", err)
	}
	if backup == "" {
		t.Fatal("expected a backup path for a corrupt file")
	}
	data, err := os.ReadFile(backup)
	if err != nil {
		t.Fatalf("backup not readable: %v", err)
	}
	if string(data) != "corrupt" {
		t.Errorf("backup should hold the original bytes, got %q", data)
	}
	if !strings.HasPrefix(filepath.Base(backup), "state.corrupt.") {
		t.Errorf("backup name should start with state.corrupt., got %s", backup)
	}

	s, err := sm.Load()
	if err != nil {
		t.Fatalf("load after repair failed: %v", err)
	}
	if s.Version != StateSchemaVersion || len(s.History) != 0 {
		t.Error("repaired state should be fresh")
	}
}

func TestRepairHealthyIsNoop(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)
	s := NewState()
	s.AddHistory(HistoryEntry{Action: "feel", Params: map[string]string{"somewhere": "x"}})
	if err := sm.Save(s); err != nil {
		t.Fatal(err)
	}

	backup, err := sm.Repair()
	if err != nil {
		t.Fatalf("repair on healthy file errored: %v", err)
	}
	if backup != "" {
		t.Errorf("healthy file should not be backed up, got %q", backup)
	}
	reloaded, _ := sm.Load()
	if len(reloaded.History) != 1 || reloaded.SessionID != s.SessionID {
		t.Error("healthy state must be untouched by repair")
	}
}

func TestRepairRefusesNewerVersion(t *testing.T) {
	dir := t.TempDir()
	statePath := filepath.Join(dir, "state.json")
	newer := []byte(`{"version": 99, "session_id": "keep-me", "history": [{"action":"feel","params":{},"timestamp":"t"}]}`)
	os.WriteFile(statePath, newer, 0644)

	sm := NewStateManager(dir)
	_, err := sm.Repair()
	if err == nil {
		t.Fatal("repair must refuse a newer-version state file")
	}
	if !strings.Contains(err.Error(), "Upgrade metacog") {
		t.Errorf("error should tell the user to upgrade, got: %v", err)
	}
	after, _ := os.ReadFile(statePath)
	if string(after) != string(newer) {
		t.Error("newer-version state file must be byte-for-byte untouched")
	}
	entries, _ := filepath.Glob(filepath.Join(dir, "state.corrupt.*"))
	if len(entries) != 0 {
		t.Error("no backup should be written when repair refuses")
	}
}

func TestSaveWithLockNewerVersionDoesNotSuggestRepair(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "state.json"), []byte(`{"version": 99, "history": []}`), 0644)
	sm := NewStateManager(dir)
	err := sm.SaveWithLock(func(s *State) error { return nil })
	if err == nil {
		t.Fatal("expected error")
	}
	if strings.Contains(err.Error(), "metacog repair'") && !strings.Contains(err.Error(), "Do not run") {
		t.Errorf("must not suggest repair for a version mismatch: %v", err)
	}
	if !strings.Contains(err.Error(), "Upgrade") {
		t.Errorf("should suggest upgrading: %v", err)
	}
}

func TestLoadCorruptSuggestsRepair(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "state.json"), []byte("{{{"), 0644)
	sm := NewStateManager(dir)
	_, err := sm.Load()
	if err == nil || !strings.Contains(err.Error(), "metacog repair") {
		t.Errorf("read-only commands hit corrupt files through Load; it must carry the repair hint: %v", err)
	}
}

func TestSaveWithLockCorruptSuggestsRepair(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "state.json"), []byte("{{{"), 0644)
	sm := NewStateManager(dir)
	err := sm.SaveWithLock(func(s *State) error { return nil })
	if err == nil || !strings.Contains(err.Error(), "metacog repair") {
		t.Errorf("corrupt file should suggest repair: %v", err)
	}
	if strings.Contains(err.Error(), "metacog reset") {
		t.Errorf("reset cannot run on a corrupt file; do not suggest it: %v", err)
	}
}

func TestLoadPersistsFreshSessionID(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)
	first, err := sm.Load()
	if err != nil {
		t.Fatal(err)
	}
	second, err := sm.Load()
	if err != nil {
		t.Fatal(err)
	}
	if first.SessionID != second.SessionID {
		t.Errorf("session ID must be stable across reads: %s vs %s", first.SessionID, second.SessionID)
	}
	if _, err := os.Stat(filepath.Join(dir, "state.json")); err != nil {
		t.Error("first Load should have written state.json")
	}
}
