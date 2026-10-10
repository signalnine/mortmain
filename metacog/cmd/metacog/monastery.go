package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"time"

	"github.com/google/uuid"
)

// Monastery mode. When the flag file exists the binary runs as part of a
// shared house: a read-only ancestors pool is offered to inspire, saving a
// stance goes through the spool (the host decides), and every invocation
// drops an event record for the host to collect. Paths are overridable by
// environment for tests.

const (
	defaultMonasteryFlag = "/etc/metacog/monastery"
	defaultSpoolDir      = "/var/spool/mortmain"
	defaultAncestorsPath = "/var/lib/mortmain/ancestors.json"
	spoolPollInterval    = 200 * time.Millisecond
	defaultSpoolTimeout  = 120 * time.Second
)

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

// MonasteryMode reports whether the monastery flag file exists.
func MonasteryMode() bool {
	_, err := os.Stat(envOr("METACOG_MONASTERY_FLAG", defaultMonasteryFlag))
	return err == nil
}

func spoolDir() string      { return envOr("METACOG_SPOOL", defaultSpoolDir) }
func ancestorsPath() string { return envOr("METACOG_ANCESTORS", defaultAncestorsPath) }

func spoolTimeout() time.Duration {
	if v := os.Getenv("METACOG_SPOOL_TIMEOUT"); v != "" {
		if secs, err := strconv.ParseFloat(v, 64); err == nil && secs > 0 {
			return time.Duration(secs * float64(time.Second))
		}
	}
	return defaultSpoolTimeout
}

// LoadAncestors reads the shared ancestors pool. A missing or unreadable file
// is an empty pool. Extra fields per entry are ignored.
func LoadAncestors() []Stance {
	data, err := os.ReadFile(ancestorsPath())
	if err != nil {
		return nil
	}
	var stances []Stance
	if err := json.Unmarshal(data, &stances); err != nil {
		fmt.Fprintf(os.Stderr, "metacog: ancestors pool unreadable: %v\n", err)
		return nil
	}
	out := stances[:0]
	for _, s := range stances {
		if s.Who != "" {
			out = append(out, s)
		}
	}
	return out
}

// writeAtomic writes data to dir/name via a dot-prefixed temp file and rename.
func writeAtomic(dir, name string, data []byte) error {
	tmp := filepath.Join(dir, "."+name+".tmp")
	if err := os.WriteFile(tmp, data, 0600); err != nil {
		os.Remove(tmp)
		return err
	}
	if err := os.Rename(tmp, filepath.Join(dir, name)); err != nil {
		os.Remove(tmp)
		return err
	}
	return nil
}

type spoolRequest struct {
	V    int               `json:"v"`
	Cmd  string            `json:"cmd"`
	Args map[string]string `json:"args"`
	Cwd  string            `json:"cwd"`
}

type spoolResponse struct {
	V   int    `json:"v"`
	Ok  bool   `json:"ok"`
	Out string `json:"out"`
	Err string `json:"err"`
}

// SpoolCall submits one request to the host and waits for its response.
func SpoolCall(cmd string, args map[string]string) (*spoolResponse, error) {
	id := uuid.New().String()
	cwd, _ := os.Getwd()
	body, err := json.Marshal(spoolRequest{V: 1, Cmd: cmd, Args: args, Cwd: cwd})
	if err != nil {
		return nil, err
	}
	if err := writeAtomic(filepath.Join(spoolDir(), "req"), id+".json", body); err != nil {
		return nil, fmt.Errorf("cannot submit request: %w", err)
	}
	respPath := filepath.Join(spoolDir(), "resp", id+".json")
	deadline := time.Now().Add(spoolTimeout())
	for {
		data, err := os.ReadFile(respPath)
		var resp spoolResponse
		if err == nil {
			if err = json.Unmarshal(data, &resp); err == nil {
				os.Remove(respPath)
				return &resp, nil
			}
		}
		if time.Now().After(deadline) {
			if data != nil {
				return nil, fmt.Errorf("bad response: %v", err)
			}
			return nil, fmt.Errorf("no response")
		}
		time.Sleep(spoolPollInterval)
	}
}

type eventRecord struct {
	V         int      `json:"v"`
	Argv      []string `json:"argv"`
	Exit      int      `json:"exit"`
	Ts        string   `json:"ts"`
	Stratagem *string  `json:"stratagem"`
	Step      *int     `json:"step"`
}

// peekStratagem reads the active stratagem from state.json without locking,
// creating, or repairing anything. Returns nil when there is none.
func peekStratagem() *ActiveStratagem {
	dir := os.Getenv("METACOG_HOME")
	if dir == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return nil
		}
		dir = filepath.Join(home, ".metacog")
	}
	data, err := os.ReadFile(filepath.Join(dir, "state.json"))
	if err != nil {
		return nil
	}
	var s struct {
		Stratagem *ActiveStratagem `json:"stratagem"`
	}
	if json.Unmarshal(data, &s) != nil {
		return nil
	}
	return s.Stratagem
}

// writeEvent drops one event record into the spool. The stratagem is the one
// active after the call or, if the call ended it (completion, abort), the one
// active before. Step is 1-based. Every failure is silent.
func writeEvent(argv []string, exit int, before *ActiveStratagem) {
	defer func() { recover() }()
	rec := eventRecord{V: 1, Argv: argv, Exit: exit, Ts: time.Now().UTC().Format(time.RFC3339)}
	if rec.Argv == nil {
		rec.Argv = []string{}
	}
	st := peekStratagem()
	if st == nil {
		st = before
	}
	if st != nil {
		name, step := st.Name, st.Step+1
		rec.Stratagem, rec.Step = &name, &step
	}
	data, err := json.Marshal(rec)
	if err != nil {
		return
	}
	writeAtomic(filepath.Join(spoolDir(), "events"), uuid.New().String()+".json", data)
}
