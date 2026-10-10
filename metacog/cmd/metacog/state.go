package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"github.com/google/uuid"
)

const MaxHistoryEntries = 500

type Identity struct {
	Name string `json:"name"`
	Lens string `json:"lens"`
	Env  string `json:"env"`
}

type Substrate struct {
	Substance string `json:"substance"`
	Method    string `json:"method"`
	Qualia    string `json:"qualia"`
}

type ActiveStratagem struct {
	Name           string   `json:"name"`
	Step           int      `json:"step"`
	StepsCompleted []string `json:"steps_completed"`
	StartedAt      string   `json:"started_at"`
	// Title and Steps are copied from the rite at start time (additive,
	// omitempty), so the session survives the rite file changing or vanishing.
	Title string `json:"title,omitempty"`
	Steps []Step `json:"steps,omitempty"`
}

type HistoryEntry struct {
	Action    string            `json:"action"`
	Params    map[string]string `json:"params"`
	Timestamp string            `json:"timestamp"`
	Session   string            `json:"session,omitempty"`
	// For abandoned stratagems
	Status string `json:"status,omitempty"`
	StepAt int    `json:"step_at,omitempty"`
}

type State struct {
	Version   int              `json:"version"`
	SessionID string           `json:"session_id"`
	Session   string           `json:"session,omitempty"`
	Identity  *Identity        `json:"identity,omitempty"`
	Substrate *Substrate       `json:"substrate,omitempty"`
	Stratagem *ActiveStratagem `json:"stratagem,omitempty"`
	History   []HistoryEntry   `json:"history"`
}

func NewState() *State {
	return &State{
		Version:   StateSchemaVersion,
		SessionID: uuid.New().String(),
		History:   []HistoryEntry{},
	}
}

func (s *State) AddHistory(entry HistoryEntry) {
	if entry.Timestamp == "" {
		entry.Timestamp = time.Now().UTC().Format(time.RFC3339)
	}
	if entry.Session == "" && s.Session != "" {
		entry.Session = s.Session
	}
	s.History = append(s.History, entry)
}

type StateManager struct {
	dir         string
	filePath    string
	lockPath    string
	archivePath string
	journalPath string
}

func NewStateManager(dir string) *StateManager {
	return &StateManager{
		dir:         dir,
		filePath:    filepath.Join(dir, "state.json"),
		lockPath:    filepath.Join(dir, ".state.lock"),
		archivePath: filepath.Join(dir, "history-archive.jsonl"),
		journalPath: filepath.Join(dir, "journal.jsonl"),
	}
}

func DefaultStateManager() *StateManager {
	dir := os.Getenv("METACOG_HOME")
	if dir == "" {
		home, _ := os.UserHomeDir()
		dir = filepath.Join(home, ".metacog")
	}
	os.MkdirAll(dir, 0755)
	return NewStateManager(dir)
}

func (sm *StateManager) lock() (*os.File, error) {
	os.MkdirAll(sm.dir, 0755)
	f, err := os.OpenFile(sm.lockPath, os.O_CREATE|os.O_RDWR, 0644)
	if err != nil {
		return nil, fmt.Errorf("cannot open lock file: %w", err)
	}
	if err := syscall.Flock(int(f.Fd()), syscall.LOCK_EX); err != nil {
		f.Close()
		return nil, fmt.Errorf("cannot acquire lock: %w", err)
	}
	return f, nil
}

func (sm *StateManager) unlock(f *os.File) {
	syscall.Flock(int(f.Fd()), syscall.LOCK_UN)
	f.Close()
}

// NewerStateError means the state file was written by a newer metacog whose
// schema this binary does not understand. It is a version mismatch, not
// corruption: the fix is to upgrade, never to repair.
type NewerStateError struct {
	FileVersion int
}

func (e *NewerStateError) Error() string {
	return fmt.Sprintf("state file version %d requires a newer metacog. You're running v%s", e.FileVersion, Version)
}

// loadErrorWithHint wraps a loadUnlocked failure with the action the user
// should take. Version mismatches must never be "repaired".
func loadErrorWithHint(err error) error {
	var newer *NewerStateError
	if errors.As(err, &newer) {
		return fmt.Errorf("cannot load state: %w\n  Upgrade metacog. Do not run 'metacog repair': it would discard this state", err)
	}
	return fmt.Errorf("cannot load state: %w\n  Run 'metacog repair' (the corrupt file is preserved as state.corrupt.<timestamp>.json)", err)
}

func (sm *StateManager) Load() (*State, error) {
	lockFile, err := sm.lock()
	if err != nil {
		return nil, err
	}
	defer sm.unlock(lockFile)

	_, statErr := os.Stat(sm.filePath)
	s, err := sm.loadUnlocked()
	if err != nil {
		return nil, loadErrorWithHint(err)
	}
	if os.IsNotExist(statErr) {
		// First touch of this state dir: persist so the freshly minted
		// session ID is the same one every later invocation sees.
		if err := sm.saveUnlocked(s); err != nil {
			return nil, err
		}
	}
	return s, nil
}

func (sm *StateManager) loadUnlocked() (*State, error) {
	data, err := os.ReadFile(sm.filePath)
	if os.IsNotExist(err) {
		return NewState(), nil
	}
	if err != nil {
		return nil, fmt.Errorf("cannot read state file: %w", err)
	}

	// Check version first
	var versionCheck struct {
		Version int `json:"version"`
	}
	if err := json.Unmarshal(data, &versionCheck); err != nil {
		return nil, fmt.Errorf("state file corrupted (invalid JSON): %w", err)
	}
	if versionCheck.Version > StateSchemaVersion {
		return nil, &NewerStateError{FileVersion: versionCheck.Version}
	}

	var s State
	if err := json.Unmarshal(data, &s); err != nil {
		return nil, fmt.Errorf("state file corrupted: %w", err)
	}
	return &s, nil
}

func (sm *StateManager) Save(s *State) error {
	lockFile, err := sm.lock()
	if err != nil {
		return err
	}
	defer sm.unlock(lockFile)

	return sm.saveUnlocked(s)
}

func (sm *StateManager) archiveAndTrim(s *State) {
	if len(s.History) <= MaxHistoryEntries {
		return
	}
	overflow := s.History[:len(s.History)-MaxHistoryEntries]
	s.History = s.History[len(s.History)-MaxHistoryEntries:]

	os.MkdirAll(sm.dir, 0755)
	f, err := os.OpenFile(sm.archivePath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Warning: could not open archive: %v\n", err)
		return
	}
	defer f.Close()
	for _, e := range overflow {
		data, err := json.Marshal(e)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Warning: could not marshal archive entry: %v\n", err)
			continue
		}
		fmt.Fprintf(f, "%s\n", data)
	}
}

func (sm *StateManager) saveUnlocked(s *State) error {
	os.MkdirAll(sm.dir, 0755)
	sm.archiveAndTrim(s)

	data, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return fmt.Errorf("cannot marshal state: %w", err)
	}

	tmpPath := filepath.Join(sm.dir, ".state.json.tmp")
	if err := os.WriteFile(tmpPath, data, 0644); err != nil {
		return fmt.Errorf("cannot write temp state file: %w", err)
	}

	if err := os.Rename(tmpPath, sm.filePath); err != nil {
		return fmt.Errorf("cannot rename state file: %w", err)
	}
	return nil
}

func (sm *StateManager) SaveWithLock(fn func(s *State) error) error {
	lockFile, err := sm.lock()
	if err != nil {
		return err
	}
	defer sm.unlock(lockFile)

	s, err := sm.loadUnlocked()
	if err != nil {
		return loadErrorWithHint(err)
	}

	if err := fn(s); err != nil {
		return err
	}

	return sm.saveUnlocked(s)
}

func (sm *StateManager) AppendJournal(entry JournalEntry) error {
	lockFile, err := sm.lock()
	if err != nil {
		return err
	}
	defer sm.unlock(lockFile)

	os.MkdirAll(sm.dir, 0755)
	f, err := os.OpenFile(sm.journalPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return fmt.Errorf("cannot open journal: %w", err)
	}
	defer f.Close()

	data, err := json.Marshal(entry)
	if err != nil {
		return fmt.Errorf("cannot marshal journal entry: %w", err)
	}
	_, err = fmt.Fprintf(f, "%s\n", data)
	return err
}

func (sm *StateManager) LoadJournal() ([]JournalEntry, error) {
	lockFile, err := sm.lock()
	if err != nil {
		return nil, err
	}
	defer sm.unlock(lockFile)

	data, err := os.ReadFile(sm.journalPath)
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("cannot read journal: %w", err)
	}

	var entries []JournalEntry
	for _, line := range strings.Split(strings.TrimSpace(string(data)), "\n") {
		if line == "" {
			continue
		}
		var entry JournalEntry
		if err := json.Unmarshal([]byte(line), &entry); err != nil {
			continue // skip malformed lines
		}
		entries = append(entries, entry)
	}
	return entries, nil
}

func (sm *StateManager) LoadHistoryArchive() ([]HistoryEntry, error) {
	data, err := os.ReadFile(sm.archivePath)
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("cannot read history archive: %w", err)
	}

	var entries []HistoryEntry
	for _, line := range strings.Split(strings.TrimSpace(string(data)), "\n") {
		if line == "" {
			continue
		}
		var entry HistoryEntry
		if err := json.Unmarshal([]byte(line), &entry); err != nil {
			continue
		}
		entries = append(entries, entry)
	}
	return entries, nil
}

// Repair validates the state file. A healthy (or absent) file returns ("", nil).
// A corrupt file is moved aside to state.corrupt.<timestamp>.json, a fresh
// state is written, and the backup path is returned. A file written by a newer
// metacog is refused untouched: that is a version mismatch, not corruption.
func (sm *StateManager) Repair() (string, error) {
	lockFile, err := sm.lock()
	if err != nil {
		return "", err
	}
	defer sm.unlock(lockFile)

	_, loadErr := sm.loadUnlocked()
	if loadErr == nil {
		return "", nil
	}
	var newer *NewerStateError
	if errors.As(loadErr, &newer) {
		return "", fmt.Errorf("refusing to repair: %w\n  This is a version mismatch, not corruption. Upgrade metacog instead", loadErr)
	}

	backup := filepath.Join(sm.dir, fmt.Sprintf("state.corrupt.%s.json", time.Now().UTC().Format("20060102T150405.000000000Z")))
	if err := os.Rename(sm.filePath, backup); err != nil {
		return "", fmt.Errorf("cannot back up corrupt state file: %w", err)
	}
	if err := sm.saveUnlocked(NewState()); err != nil {
		return "", err
	}
	return backup, nil
}
