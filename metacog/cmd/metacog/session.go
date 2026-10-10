package main

import (
	"fmt"
	"strings"

	"github.com/spf13/cobra"
)

func StartSession(s *State, name string) error {
	name = strings.TrimSpace(name)
	if name == "" {
		return fmt.Errorf("session name cannot be empty")
	}
	if s.Session != "" {
		return fmt.Errorf("session %q is already active. End it first with 'metacog session end'", s.Session)
	}
	s.Session = name
	s.AddHistory(HistoryEntry{
		Action: "session",
		Params: map[string]string{"name": name, "event": "started"},
	})
	return nil
}

func EndSession(s *State) error {
	if s.Session == "" {
		return fmt.Errorf("no active session")
	}
	name := s.Session
	s.AddHistory(HistoryEntry{
		Action: "session",
		Params: map[string]string{"name": name, "event": "ended"},
	})
	s.Session = ""
	return nil
}

func ListSessions(s *State) []string {
	seen := map[string]bool{}
	var names []string
	for _, h := range s.History {
		if h.Action == "session" && h.Params["event"] == "started" {
			name := h.Params["name"]
			if !seen[name] {
				seen[name] = true
				names = append(names, name)
			}
		}
	}
	return names
}

// filterHistoryBySession returns the entries tagged with session (never nil).
func filterHistoryBySession(entries []HistoryEntry, session string) []HistoryEntry {
	filtered := []HistoryEntry{}
	for _, h := range entries {
		if h.Session == session {
			filtered = append(filtered, h)
		}
	}
	return filtered
}

func FormatHistoryFiltered(s *State, session string) string {
	if len(s.History) == 0 {
		return "No history."
	}
	filtered := filterHistoryBySession(s.History, session)
	if len(filtered) == 0 {
		return fmt.Sprintf("No history for session %q.", session)
	}
	return FormatHistory(&State{History: filtered})
}

var sessionCmd = &cobra.Command{
	Use:   "session",
	Short: "Manage named sessions",
}

var sessionStartCmd = &cobra.Command{
	Use:   "start [name]",
	Short: "Start a named session",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		sm := DefaultStateManager()
		var output string
		err := sm.SaveWithLock(func(s *State) error {
			err := StartSession(s, args[0])
			if err != nil {
				return err
			}
			output = fmt.Sprintf("Session %q started.", args[0])
			return nil
		})
		if err != nil {
			return err
		}
		fmt.Println(FormatOutput(jsonOutput, output, nil))
		return nil
	},
}

var sessionEndCmd = &cobra.Command{
	Use:   "end",
	Short: "End the active session",
	RunE: func(cmd *cobra.Command, args []string) error {
		sm := DefaultStateManager()
		var output string
		err := sm.SaveWithLock(func(s *State) error {
			name := s.Session
			err := EndSession(s)
			if err != nil {
				return err
			}
			output = fmt.Sprintf("Session %q ended.", name)
			return nil
		})
		if err != nil {
			return err
		}
		fmt.Println(FormatOutput(jsonOutput, output, nil))
		return nil
	},
}

var sessionListCmd = &cobra.Command{
	Use:   "list",
	Short: "List all sessions from history",
	RunE: func(cmd *cobra.Command, args []string) error {
		sm := DefaultStateManager()
		s, err := sm.Load()
		if err != nil {
			return err
		}
		names := ListSessions(s)
		if len(names) == 0 {
			fmt.Println(FormatOutput(jsonOutput, "No sessions recorded.", nil))
			return nil
		}
		output := fmt.Sprintf("%d sessions:\n", len(names))
		for _, name := range names {
			output += fmt.Sprintf("  %s\n", name)
		}
		fmt.Println(FormatOutput(jsonOutput, output, nil))
		return nil
	},
}

func init() {
	sessionCmd.AddCommand(sessionStartCmd)
	sessionCmd.AddCommand(sessionEndCmd)
	sessionCmd.AddCommand(sessionListCmd)
	rootCmd.AddCommand(sessionCmd)
}
