package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

// Rites are stratagems stored as data on disk. Nothing is compiled in: the
// binary finds rites along a search path, validates each file strictly, and
// never executes anything a rite contains. A rite's steps are only ever
// printed back as instructions.

const (
	MaxRiteBytes    = 8192
	MaxRiteSteps    = 12
	MaxRiteStepText = 400
	MaxRiteTitle    = 48
)

var (
	riteNameRe  = regexp.MustCompile(`^[a-z][a-z0-9-]{0,31}$`)
	riteTitleRe = regexp.MustCompile(`^[A-Z ]+$`)
)

// DefaultRiteDirs is the search path used when METACOG_RITES is unset.
// "~" is expanded to the caller's home directory (the monk's cell).
var DefaultRiteDirs = []string{"~/rites", "/library/inner", "/library/outer", "/usr/share/metacog/rites"}

type riteStepFile struct {
	Kind string `json:"kind"`
	Text string `json:"text"`
}

type riteFile struct {
	Name  string         `json:"name"`
	Title string         `json:"title"`
	Steps []riteStepFile `json:"steps"`
}

// RiteDirs returns the rite search path in priority order.
func RiteDirs() []string {
	var dirs []string
	if env, ok := os.LookupEnv("METACOG_RITES"); ok {
		for _, d := range strings.Split(env, ":") {
			if d != "" {
				dirs = append(dirs, d)
			}
		}
		return dirs
	}
	home, _ := os.UserHomeDir()
	for _, d := range DefaultRiteDirs {
		if strings.HasPrefix(d, "~/") {
			if home == "" {
				continue
			}
			d = filepath.Join(home, d[2:])
		}
		dirs = append(dirs, d)
	}
	return dirs
}

func isStepKind(k string) bool {
	return IsPrimitive(k) || k == string(StepThink) || k == string(StepAction)
}

func isPrintableASCII(s string) bool {
	for i := 0; i < len(s); i++ {
		if s[i] < 0x20 || s[i] > 0x7e {
			return false
		}
	}
	return true
}

// ParseRite validates raw rite bytes against the schema. stem is the filename
// without ".json"; the rite's name must equal it.
func ParseRite(data []byte, stem string) (StratagemDef, error) {
	if len(data) > MaxRiteBytes {
		return StratagemDef{}, fmt.Errorf("larger than %d bytes", MaxRiteBytes)
	}
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.DisallowUnknownFields()
	var rf riteFile
	if err := dec.Decode(&rf); err != nil {
		return StratagemDef{}, fmt.Errorf("bad json: %v", err)
	}
	if _, err := dec.Token(); err != io.EOF {
		return StratagemDef{}, fmt.Errorf("trailing data after rite")
	}
	if !riteNameRe.MatchString(rf.Name) {
		return StratagemDef{}, fmt.Errorf("bad name %q", rf.Name)
	}
	if rf.Name != stem {
		return StratagemDef{}, fmt.Errorf("name %q does not match file name", rf.Name)
	}
	if len(rf.Title) == 0 || len(rf.Title) > MaxRiteTitle || !riteTitleRe.MatchString(rf.Title) {
		return StratagemDef{}, fmt.Errorf("bad title")
	}
	if len(rf.Steps) < 1 || len(rf.Steps) > MaxRiteSteps {
		return StratagemDef{}, fmt.Errorf("need 1 to %d steps, got %d", MaxRiteSteps, len(rf.Steps))
	}
	def := StratagemDef{Name: rf.Title, Steps: make([]Step, len(rf.Steps))}
	for i, st := range rf.Steps {
		if !isStepKind(st.Kind) {
			return StratagemDef{}, fmt.Errorf("step %d: unknown kind %q", i+1, st.Kind)
		}
		if len(st.Text) < 1 || len(st.Text) > MaxRiteStepText || !isPrintableASCII(st.Text) {
			return StratagemDef{}, fmt.Errorf("step %d: text must be 1 to %d printable ascii characters", i+1, MaxRiteStepText)
		}
		def.Steps[i] = Step{Kind: StepKind(st.Kind), Description: st.Text}
	}
	return def, nil
}

// readRiteFile reads at most MaxRiteBytes+1 bytes from a regular file.
func readRiteFile(path string) ([]byte, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	fi, err := f.Stat()
	if err != nil {
		return nil, err
	}
	if !fi.Mode().IsRegular() {
		return nil, fmt.Errorf("not a regular file")
	}
	return io.ReadAll(io.LimitReader(f, MaxRiteBytes+1))
}

// riteWarned keeps each invalid file to one warning per invocation, however
// many times the search path is walked.
var riteWarned = map[string]bool{}

func riteWarn(path string, err error) {
	if riteWarned[path] {
		return
	}
	riteWarned[path] = true
	fmt.Fprintf(os.Stderr, "metacog: skipping rite %s: %v\n", path, err)
}

// loadRiteFrom loads one named rite from one directory. found is false when
// the file is absent or unreadable; an invalid file warns and is not found.
func loadRiteFrom(dir, name string) (StratagemDef, bool) {
	path := filepath.Join(dir, name+".json")
	data, err := readRiteFile(path)
	if err != nil {
		return StratagemDef{}, false
	}
	def, err := ParseRite(data, name)
	if err != nil {
		riteWarn(path, err)
		return StratagemDef{}, false
	}
	return def, true
}

// LoadRite finds the first valid rite with this name along the search path.
func LoadRite(name string) (StratagemDef, bool) {
	if !riteNameRe.MatchString(name) {
		return StratagemDef{}, false
	}
	for _, dir := range RiteDirs() {
		if def, ok := loadRiteFrom(dir, name); ok {
			return def, true
		}
	}
	return StratagemDef{}, false
}

// LoadRites returns every loadable rite keyed by name. Earlier directories in
// the search path win; unreadable directories are skipped silently.
func LoadRites() map[string]StratagemDef {
	rites := map[string]StratagemDef{}
	for _, dir := range RiteDirs() {
		entries, err := os.ReadDir(dir)
		if err != nil {
			continue
		}
		for _, e := range entries {
			fn := e.Name()
			if e.IsDir() || !strings.HasSuffix(fn, ".json") || strings.HasPrefix(fn, ".") {
				continue
			}
			stem := strings.TrimSuffix(fn, ".json")
			if _, seen := rites[stem]; seen {
				continue
			}
			if def, ok := loadRiteFrom(dir, stem); ok {
				rites[stem] = def
			}
		}
	}
	return rites
}

// riteNames returns the sorted names of a rite map.
func riteNames(rites map[string]StratagemDef) []string {
	names := make([]string, 0, len(rites))
	for name := range rites {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}
