package main

import (
	"fmt"

	"github.com/spf13/cobra"
)

func findLastCompletedStratagem(s *State) (string, int) {
	for i := len(s.History) - 1; i >= 0; i-- {
		h := s.History[i]
		if h.Action == "stratagem" && h.Params["event"] == "completed" {
			return h.Params["name"], i
		}
	}
	return "", -1
}

func hasOutcomeAfter(s *State, afterIdx int) bool {
	for i := afterIdx + 1; i < len(s.History); i++ {
		if s.History[i].Action == "outcome" {
			return true
		}
	}
	return false
}

// findLastPrimitive scans backward for the last primitive entry
// that isn't inside a stratagem span and doesn't already have an outcome after it.
func findLastPrimitive(s *State) int {
	for i := len(s.History) - 1; i >= 0; i-- {
		h := s.History[i]
		if !IsPrimitive(h.Action) {
			continue
		}
		// Check it's not covered by a stratagem span
		if isInsideStratagemSpan(s, i) {
			continue
		}
		// Check no outcome already covers it
		if hasOutcomeAfter(s, i) {
			continue
		}
		return i
	}
	return -1
}

// isInsideStratagemSpan checks if index i falls between a stratagem started
// and its completed/abandoned/aborted event.
func isInsideStratagemSpan(s *State, idx int) bool {
	// Scan backward from idx for the nearest stratagem boundary
	for i := idx - 1; i >= 0; i-- {
		h := s.History[i]
		if h.Action == "stratagem" {
			event := h.Params["event"]
			if event == "started" {
				// We're inside an active stratagem span
				return true
			}
			if event == "completed" || h.Status == "abandoned" || h.Status == "aborted" {
				// The stratagem ended before our index
				return false
			}
		}
	}
	return false
}

func recordOutcomeEntry(s *State, result, shift, stratagemName string) {
	params := map[string]string{
		"result":    result,
		"stratagem": stratagemName,
	}
	if shift != "" {
		params["shift"] = shift
	}
	s.AddHistory(HistoryEntry{
		Action: "outcome",
		Params: params,
	})
}

func RecordOutcome(s *State, result, shift string) error {
	if result != "productive" && result != "unproductive" {
		return fmt.Errorf("result must be 'productive' or 'unproductive', got %q", result)
	}

	// Tier 1: completed stratagem without an outcome
	name, idx := findLastCompletedStratagem(s)
	if idx >= 0 && !hasOutcomeAfter(s, idx) {
		recordOutcomeEntry(s, result, shift, name)
		return nil
	}

	// Tier 2: freestyle primitives without an outcome
	pidx := findLastPrimitive(s)
	if pidx >= 0 {
		recordOutcomeEntry(s, result, shift, "freestyle")
		return nil
	}

	// If tier 1 found a stratagem but it already had an outcome
	if idx >= 0 {
		return fmt.Errorf("outcome already recorded for the last completed stratagem (%s) and no unmarked freestyle primitive follows it. Use --amend to update it", name)
	}

	return fmt.Errorf("no completed stratagem or freestyle primitives found in history")
}

func AmendOutcome(s *State, result, shift string) error {
	if result != "productive" && result != "unproductive" {
		return fmt.Errorf("result must be 'productive' or 'unproductive', got %q", result)
	}

	// Find most recent outcome
	for i := len(s.History) - 1; i >= 0; i-- {
		if s.History[i].Action == "outcome" {
			s.History[i].Params["result"] = result
			if shift != "" {
				s.History[i].Params["shift"] = shift
			} else {
				delete(s.History[i].Params, "shift")
			}
			return nil
		}
	}
	return fmt.Errorf("no outcome to amend")
}

var outcomeResult string
var outcomeShift string
var outcomeAmend bool

var outcomeCmd = &cobra.Command{
	Use:   "outcome",
	Short: "Record effectiveness of stratagem or freestyle practice",
	RunE: func(cmd *cobra.Command, args []string) error {
		sm := DefaultStateManager()
		var output string
		err := sm.SaveWithLock(func(s *State) error {
			if outcomeAmend {
				err := AmendOutcome(s, outcomeResult, outcomeShift)
				if err != nil {
					return err
				}
				output = fmt.Sprintf("Outcome amended to %s.", outcomeResult)
				return nil
			}

			err := RecordOutcome(s, outcomeResult, outcomeShift)
			if err != nil {
				return err
			}
			// Find what was just recorded
			last := s.History[len(s.History)-1]
			output = fmt.Sprintf("Outcome recorded: %s (%s).", outcomeResult, last.Params["stratagem"])
			return nil
		})
		if err != nil {
			return err
		}
		fmt.Println(FormatOutput(jsonOutput, output, nil))
		return nil
	},
}

func init() {
	outcomeCmd.Flags().StringVar(&outcomeResult, "result", "", "Outcome: productive or unproductive (required)")
	outcomeCmd.Flags().StringVar(&outcomeShift, "shift", "", "Description of what changed (optional)")
	outcomeCmd.Flags().BoolVar(&outcomeAmend, "amend", false, "Update most recent outcome instead of creating new")
	outcomeCmd.MarkFlagRequired("result")
	rootCmd.AddCommand(outcomeCmd)
}
