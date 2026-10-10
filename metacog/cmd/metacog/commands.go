package main

import (
	"fmt"
	"strings"

	"github.com/spf13/cobra"
)

func FormatStatus(s *State) string {
	var b strings.Builder
	b.WriteString(fmt.Sprintf("Session: %s\n", s.SessionID))
	if s.Session != "" {
		b.WriteString(fmt.Sprintf("Active session: %s\n", s.Session))
	}
	b.WriteString("\n")

	if s.Identity != nil {
		b.WriteString(fmt.Sprintf("Identity: %s\n  Lens: %s\n  Environment: %s\n\n", s.Identity.Name, s.Identity.Lens, s.Identity.Env))
	} else {
		b.WriteString("Identity: (none)\n\n")
	}

	if s.Substrate != nil {
		b.WriteString(fmt.Sprintf("Substrate: %s\n  Method: %s\n  Qualia: %s\n\n", s.Substrate.Substance, s.Substrate.Method, s.Substrate.Qualia))
	} else {
		b.WriteString("Substrate: (none)\n\n")
	}

	if s.Stratagem != nil {
		b.WriteString(StratagemStatus(s))
	} else {
		b.WriteString("Stratagem: (none)\n")
	}

	return b.String()
}

func FormatHistory(s *State) string {
	if len(s.History) == 0 {
		return "No history."
	}
	var b strings.Builder
	for i, h := range s.History {
		status := ""
		if h.Status != "" {
			status = fmt.Sprintf(" [%s]", h.Status)
		}
		b.WriteString(fmt.Sprintf("%d. [%s] %s%s", i+1, h.Timestamp, h.Action, status))
		if len(h.Params) > 0 {
			parts := make([]string, 0, len(h.Params))
			for k, v := range h.Params {
				parts = append(parts, fmt.Sprintf("%s=%s", k, v))
			}
			b.WriteString(fmt.Sprintf(" (%s)", strings.Join(parts, ", ")))
		}
		b.WriteString("\n")
	}
	return b.String()
}

// StatusView is the --json shape of `metacog status`.
type StatusView struct {
	SessionID string         `json:"session_id"`
	Session   string         `json:"session,omitempty"`
	Identity  *Identity      `json:"identity"`
	Substrate *Substrate     `json:"substrate"`
	Stratagem *StratagemView `json:"stratagem"`
}

var statusCmd = &cobra.Command{
	Use:   "status",
	Short: "Show current state",
	RunE: func(cmd *cobra.Command, args []string) error {
		sm := DefaultStateManager()
		s, err := sm.Load()
		if err != nil {
			return err
		}
		view := StatusView{SessionID: s.SessionID, Session: s.Session, Identity: s.Identity, Substrate: s.Substrate, Stratagem: StratagemViewOf(s)}
		fmt.Println(FormatStructured(jsonOutput, FormatStatus(s), view))
		return nil
	},
}

var resetCmd = &cobra.Command{
	Use:   "reset",
	Short: "Clear identity, substrate, and stratagem (preserves session and history)",
	RunE: func(cmd *cobra.Command, args []string) error {
		sm := DefaultStateManager()
		err := sm.SaveWithLock(func(s *State) error {
			s.Identity = nil
			s.Substrate = nil
			s.Stratagem = nil
			return nil
		})
		if err != nil {
			return err
		}
		fmt.Println(FormatOutput(jsonOutput, "State reset. Identity, substrate, and stratagem cleared.", nil))
		return nil
	},
}

var historyFull bool
var historySession string

func mergeArchivedHistory(sm *StateManager, s *State) (*State, error) {
	archived, err := sm.LoadHistoryArchive()
	if err != nil {
		return nil, err
	}
	if len(archived) == 0 {
		return s, nil
	}
	merged := *s
	merged.History = append(archived, s.History...)
	return &merged, nil
}

var historyCmd = &cobra.Command{
	Use:   "history",
	Short: "Show transformation history",
	RunE: func(cmd *cobra.Command, args []string) error {
		sm := DefaultStateManager()
		s, err := sm.Load()
		if err != nil {
			return err
		}
		if historyFull {
			s, err = mergeArchivedHistory(sm, s)
			if err != nil {
				return err
			}
		}
		entries := s.History
		var output string
		if historySession != "" {
			entries = filterHistoryBySession(s.History, historySession)
			output = FormatHistoryFiltered(s, historySession)
		} else {
			output = FormatHistory(s)
		}
		if entries == nil {
			entries = []HistoryEntry{} // marshal as [] not null
		}
		fmt.Println(FormatStructured(jsonOutput, output, entries))
		return nil
	},
}

var repairCmd = &cobra.Command{
	Use:   "repair",
	Short: "Validate the state file; back up and replace it only if it is corrupt",
	RunE: func(cmd *cobra.Command, args []string) error {
		sm := DefaultStateManager()
		backup, err := sm.Repair()
		if err != nil {
			return err
		}
		if backup == "" {
			fmt.Println(FormatOutput(jsonOutput, "State file is healthy. Nothing to repair.", nil))
			return nil
		}
		fmt.Println(FormatOutput(jsonOutput, fmt.Sprintf("State file was corrupted. Original preserved at %s; fresh state written.", backup), nil))
		return nil
	},
}

func init() {
	historyCmd.Flags().BoolVar(&historyFull, "full", false, "Show full history from log file")
	historyCmd.Flags().StringVar(&historySession, "session", "", "Filter history by session name")
	rootCmd.AddCommand(statusCmd)
	rootCmd.AddCommand(resetCmd)
	rootCmd.AddCommand(historyCmd)
	rootCmd.AddCommand(repairCmd)
}
