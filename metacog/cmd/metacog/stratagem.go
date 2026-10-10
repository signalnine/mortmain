package main

import (
	"fmt"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

type StepKind string

const (
	StepFeel           StepKind = "feel"
	StepBecome         StepKind = "become"
	StepDrugs          StepKind = "drugs"
	StepName           StepKind = "name"
	StepRitual         StepKind = "ritual"
	StepMeditate       StepKind = "meditate"
	StepCounterfactual StepKind = "counterfactual"
	StepSynthesis      StepKind = "synthesis"
	StepFork           StepKind = "fork"
	StepRegister       StepKind = "register"
	StepChord          StepKind = "chord"
	StepSilence        StepKind = "silence"
	StepExcerpt        StepKind = "excerpt"
	StepCommitment     StepKind = "commitment"
	StepDisjunction    StepKind = "disjunction"
	StepGlossolalia    StepKind = "glossolalia"
	StepWitness        StepKind = "witness"
	StepApophasis      StepKind = "apophasis"
	StepThink          StepKind = "THINK"
	StepAction         StepKind = "ACTION"
)

// PrimitiveKinds is the canonical, ordered list of every primitive. Anything
// that enumerates primitives (version output, reflect, outcome's freestyle
// search, the registry test) derives from this, so adding a primitive means
// adding it here exactly once.
var PrimitiveKinds = []StepKind{
	StepFeel, StepDrugs, StepBecome, StepName, StepRitual, StepMeditate,
	StepCounterfactual, StepSynthesis, StepFork,
	StepRegister, StepChord, StepSilence, StepExcerpt, StepCommitment, StepDisjunction, StepGlossolalia,
	StepWitness, StepApophasis,
}

// IsPrimitive reports whether a history action name is a primitive.
func IsPrimitive(action string) bool {
	for _, k := range PrimitiveKinds {
		if string(k) == action {
			return true
		}
	}
	return false
}

// PrimitiveNames returns PrimitiveKinds as plain strings, in canonical order.
func PrimitiveNames() []string {
	names := make([]string, len(PrimitiveKinds))
	for i, k := range PrimitiveKinds {
		names[i] = string(k)
	}
	return names
}

type Step struct {
	Kind        StepKind `json:"kind"`
	Description string   `json:"text"`
}

type StratagemDef struct {
	Name  string
	Steps []Step
}

// activeDef returns the definition of the active stratagem. The step list
// is captured into state at start time, so a rite that is later burned or
// edited does not break a session in progress. State written by an older
// build carries only the name; for that, fall back to the search path.
func activeDef(s *State) (StratagemDef, bool) {
	if s.Stratagem == nil {
		return StratagemDef{}, false
	}
	if len(s.Stratagem.Steps) > 0 {
		return StratagemDef{Name: s.Stratagem.Title, Steps: s.Stratagem.Steps}, true
	}
	def, ok := LoadRite(s.Stratagem.Name)
	if ok {
		s.Stratagem.Title = def.Name
		s.Stratagem.Steps = def.Steps
	}
	return def, ok
}

func StartStratagem(s *State, name string, force bool) (string, error) {
	def, ok := LoadRite(name)
	if !ok {
		avail := allStratagemNames()
		if len(avail) == 0 {
			return "", fmt.Errorf("unknown stratagem %q. No rites are available", name)
		}
		return "", fmt.Errorf("unknown stratagem %q. Available: %s", name, strings.Join(avail, ", "))
	}

	if s.Stratagem != nil {
		if !force {
			cur, _ := activeDef(s)
			title := cur.Name
			if title == "" {
				title = s.Stratagem.Name
			}
			return "", fmt.Errorf("%s is active (step %d/%d).\n  Use 'metacog stratagem abort' to abandon it, or\n  Use 'metacog stratagem start %s --force' to replace it",
				title, s.Stratagem.Step+1, len(cur.Steps), name)
		}
		// Record abandoned stratagem
		s.AddHistory(HistoryEntry{
			Action: "stratagem",
			Status: "abandoned",
			StepAt: s.Stratagem.Step,
			Params: map[string]string{"name": s.Stratagem.Name},
		})
		s.Stratagem = nil
	}

	s.Stratagem = &ActiveStratagem{
		Name:           name,
		Step:           0,
		StepsCompleted: []string{},
		StartedAt:      time.Now().UTC().Format(time.RFC3339),
		Title:          def.Name,
		Steps:          def.Steps,
	}

	s.AddHistory(HistoryEntry{
		Action: "stratagem",
		Params: map[string]string{"name": name, "event": "started"},
	})

	return formatStepInstructions(def, 0), nil
}

func AdvanceStratagem(s *State) (string, error) {
	if s.Stratagem == nil {
		return "", fmt.Errorf("no active stratagem. Start one with 'metacog stratagem start <name>'")
	}

	def, ok := activeDef(s)
	if !ok || s.Stratagem.Step >= len(def.Steps) {
		return "", fmt.Errorf("the active stratagem %q can no longer be read.\n  Run 'metacog stratagem abort' to clear it", s.Stratagem.Name)
	}
	currentStep := def.Steps[s.Stratagem.Step]

	// THINK and ACTION steps advance freely
	if currentStep.Kind != StepThink && currentStep.Kind != StepAction {
		// Check that the required primitive was called
		expectedPrimitive := string(currentStep.Kind)
		found := false
		for _, completed := range s.Stratagem.StepsCompleted {
			if completed == expectedPrimitive {
				found = true
				break
			}
		}
		if !found {
			return "", fmt.Errorf("expected '%s' call before advancing (step %d of %s).\n  Run 'metacog %s ...' first, then 'metacog stratagem next'",
				expectedPrimitive, s.Stratagem.Step+1, def.Name, expectedPrimitive)
		}
	}

	// Advance
	s.Stratagem.Step++
	s.Stratagem.StepsCompleted = []string{} // Reset for next step

	// Check if stratagem is complete
	if s.Stratagem.Step >= len(def.Steps) {
		s.AddHistory(HistoryEntry{
			Action: "stratagem",
			Params: map[string]string{"name": s.Stratagem.Name, "event": "completed"},
		})
		s.Stratagem = nil
		return fmt.Sprintf("%s complete. Ground: name what shifted, what you're keeping, how it integrates.", def.Name), nil
	}

	return formatStepInstructions(def, s.Stratagem.Step), nil
}

func AbortStratagem(s *State) error {
	if s.Stratagem == nil {
		return fmt.Errorf("no active stratagem to abort")
	}
	s.AddHistory(HistoryEntry{
		Action: "stratagem",
		Status: "aborted",
		StepAt: s.Stratagem.Step,
		Params: map[string]string{"name": s.Stratagem.Name},
	})
	s.Stratagem = nil
	return nil
}

func StratagemStatus(s *State) string {
	if s.Stratagem == nil {
		return "No active stratagem."
	}
	def, _ := activeDef(s)
	var b strings.Builder
	b.WriteString(fmt.Sprintf("%s -- step %d/%d\n", def.Name, s.Stratagem.Step+1, len(def.Steps)))
	b.WriteString(fmt.Sprintf("Started: %s\n\n", s.Stratagem.StartedAt))
	for i, step := range def.Steps {
		marker := "  "
		if i < s.Stratagem.Step {
			marker = "x "
		} else if i == s.Stratagem.Step {
			marker = "> "
		}
		b.WriteString(fmt.Sprintf("%s%d. [%s] %s\n", marker, i+1, step.Kind, step.Description))
	}
	return b.String()
}

type StratagemStepView struct {
	Kind        string `json:"kind"`
	Description string `json:"description"`
	State       string `json:"state"` // done | current | pending
}

type StratagemView struct {
	Name      string              `json:"name"`
	Title     string              `json:"title"`
	Step      int                 `json:"step"` // 1-based
	Total     int                 `json:"total"`
	StartedAt string              `json:"started_at"`
	Steps     []StratagemStepView `json:"steps"`
}

// StratagemViewOf returns the active stratagem as data, or nil.
func StratagemViewOf(s *State) *StratagemView {
	if s.Stratagem == nil {
		return nil
	}
	def, _ := activeDef(s)
	v := &StratagemView{Name: s.Stratagem.Name, Title: def.Name, Step: s.Stratagem.Step + 1, Total: len(def.Steps), StartedAt: s.Stratagem.StartedAt}
	for i, st := range def.Steps {
		state := "pending"
		if i < s.Stratagem.Step {
			state = "done"
		} else if i == s.Stratagem.Step {
			state = "current"
		}
		v.Steps = append(v.Steps, StratagemStepView{Kind: string(st.Kind), Description: st.Description, State: state})
	}
	return v
}

type StratagemListEntry struct {
	Name  string   `json:"name"`
	Title string   `json:"title"`
	Steps []string `json:"steps"`
}

// StratagemListView returns every loadable rite, sorted by name, with its step kinds.
func StratagemListView() []StratagemListEntry {
	out := []StratagemListEntry{}
	rites := LoadRites()
	for _, name := range riteNames(rites) {
		def := rites[name]
		kinds := make([]string, len(def.Steps))
		for i, st := range def.Steps {
			kinds[i] = string(st.Kind)
		}
		out = append(out, StratagemListEntry{Name: name, Title: def.Name, Steps: kinds})
	}
	return out
}

func FormatStratagemList() string {
	entries := StratagemListView()
	nameW, titleW := 0, 0
	for _, e := range entries {
		if len(e.Name) > nameW {
			nameW = len(e.Name)
		}
		if len(e.Title) > titleW {
			titleW = len(e.Title)
		}
	}
	var b strings.Builder
	b.WriteString(fmt.Sprintf("%d stratagems (start one with 'metacog stratagem start <name>'):\n", len(entries)))
	for _, e := range entries {
		b.WriteString(fmt.Sprintf("  %-*s  %-*s  %s\n", nameW, e.Name, titleW, e.Title, strings.Join(e.Steps, " > ")))
	}
	return b.String()
}

func formatStepInstructions(def StratagemDef, step int) string {
	s := def.Steps[step]
	var b strings.Builder
	b.WriteString(fmt.Sprintf("%s -- Step %d/%d\n", def.Name, step+1, len(def.Steps)))
	b.WriteString(fmt.Sprintf("[%s] %s\n", s.Kind, s.Description))

	if s.Kind == StepThink || s.Kind == StepAction {
		b.WriteString("\nThis is a reflection step. When ready, run 'metacog stratagem next' to advance.")
	} else {
		b.WriteString(fmt.Sprintf("\nRun 'metacog %s ...' then 'metacog stratagem next' to advance.", s.Kind))
	}

	if step+1 < len(def.Steps) {
		next := def.Steps[step+1]
		b.WriteString(fmt.Sprintf("\nNext: [%s] %s", next.Kind, next.Description))
	}
	return b.String()
}

// ValidatePrimitiveForStratagem records a primitive call against the active
// stratagem and returns a one-line note for stderr ("" when no stratagem is
// active). Three cases:
//
//   - the call matches the current step: mark it satisfied;
//   - the current step is already satisfied and the NEXT step wants the same
//     primitive (anchor-duo's two excerpts, chorus's three becomes): advance to
//     that step and mark it, so "excerpt, excerpt, next" behaves as written;
//   - the call does not match: the primitive is still recorded as freestyle
//     history, and the note says which primitive the step actually wants.
func ValidatePrimitiveForStratagem(s *State, primitive string) string {
	if s.Stratagem == nil {
		return ""
	}
	def, _ := activeDef(s)
	total := len(def.Steps)
	if s.Stratagem.Step >= total {
		return ""
	}
	current := def.Steps[s.Stratagem.Step]
	stepNo := s.Stratagem.Step + 1

	if string(current.Kind) != primitive {
		return fmt.Sprintf("stratagem: %s step %d/%d expects '%s'; this '%s' was recorded as freestyle",
			def.Name, stepNo, total, current.Kind, primitive)
	}

	alreadySatisfied := false
	for _, done := range s.Stratagem.StepsCompleted {
		if done == primitive {
			alreadySatisfied = true
			break
		}
	}
	if !alreadySatisfied {
		s.Stratagem.StepsCompleted = append(s.Stratagem.StepsCompleted, primitive)
		return fmt.Sprintf("stratagem: %s step %d/%d satisfied; run 'metacog stratagem next'", def.Name, stepNo, total)
	}

	next := s.Stratagem.Step + 1
	if next < total && string(def.Steps[next].Kind) == primitive {
		s.Stratagem.Step = next
		s.Stratagem.StepsCompleted = []string{primitive}
		return fmt.Sprintf("stratagem: %s step %d/%d satisfied (auto-advanced from step %d, same primitive); run 'metacog stratagem next'",
			def.Name, next+1, total, stepNo)
	}
	return fmt.Sprintf("stratagem: %s step %d/%d already satisfied; run 'metacog stratagem next'", def.Name, stepNo, total)
}

// --- Cobra commands ---

var stratagemForce bool

var stratagemCmd = &cobra.Command{
	Use:   "stratagem",
	Short: "Manage transformation stratagems",
}

var stratagemStartCmd = &cobra.Command{
	Use:   "start [name]",
	Short: "Start a stratagem",
	Args:  cobra.ExactArgs(1),
	ValidArgsFunction: func(cmd *cobra.Command, args []string, toComplete string) ([]string, cobra.ShellCompDirective) {
		return allStratagemNames(), cobra.ShellCompDirectiveNoFileComp
	},
	RunE: func(cmd *cobra.Command, args []string) error {
		sm := DefaultStateManager()
		var output string
		err := sm.SaveWithLock(func(s *State) error {
			var err error
			output, err = StartStratagem(s, args[0], stratagemForce)
			return err
		})
		if err != nil {
			return err
		}
		fmt.Println(FormatOutput(jsonOutput, output, nil))
		return nil
	},
}

var stratagemNextCmd = &cobra.Command{
	Use:   "next",
	Short: "Advance to the next step",
	RunE: func(cmd *cobra.Command, args []string) error {
		sm := DefaultStateManager()
		var output string
		err := sm.SaveWithLock(func(s *State) error {
			var err error
			output, err = AdvanceStratagem(s)
			return err
		})
		if err != nil {
			return err
		}
		fmt.Println(FormatOutput(jsonOutput, output, nil))
		return nil
	},
}

var stratagemListCmd = &cobra.Command{
	Use:   "list",
	Short: "List available stratagems with their step sequences",
	RunE: func(cmd *cobra.Command, args []string) error {
		fmt.Println(FormatStructured(jsonOutput, FormatStratagemList(), StratagemListView()))
		return nil
	},
}

var stratagemStatusCmd = &cobra.Command{
	Use:   "status",
	Short: "Show current stratagem position",
	RunE: func(cmd *cobra.Command, args []string) error {
		sm := DefaultStateManager()
		s, err := sm.Load()
		if err != nil {
			return err
		}
		fmt.Println(FormatStructured(jsonOutput, StratagemStatus(s), map[string]any{"stratagem": StratagemViewOf(s)}))
		return nil
	},
}

var stratagemAbortCmd = &cobra.Command{
	Use:   "abort",
	Short: "Abandon active stratagem",
	RunE: func(cmd *cobra.Command, args []string) error {
		sm := DefaultStateManager()
		return sm.SaveWithLock(func(s *State) error {
			return AbortStratagem(s)
		})
	},
}

func init() {
	stratagemStartCmd.Flags().BoolVar(&stratagemForce, "force", false, "Replace active stratagem")
	stratagemCmd.AddCommand(stratagemStartCmd)
	stratagemCmd.AddCommand(stratagemNextCmd)
	stratagemCmd.AddCommand(stratagemStatusCmd)
	stratagemCmd.AddCommand(stratagemListCmd)
	stratagemCmd.AddCommand(stratagemAbortCmd)
	rootCmd.AddCommand(stratagemCmd)
}
