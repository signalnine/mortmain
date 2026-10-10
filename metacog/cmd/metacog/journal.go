package main

import (
	"fmt"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

type JournalEntry struct {
	Timestamp string   `json:"timestamp"`
	Insight   string   `json:"insight"`
	Session   string   `json:"session,omitempty"`
	Tags      []string `json:"tags,omitempty"`
}

func FilterJournal(entries []JournalEntry, tag, session string) []JournalEntry {
	if tag == "" && session == "" {
		return entries
	}
	var filtered []JournalEntry
	for _, e := range entries {
		if session != "" && e.Session != session {
			continue
		}
		if tag != "" {
			found := false
			for _, t := range e.Tags {
				if t == tag {
					found = true
					break
				}
			}
			if !found {
				continue
			}
		}
		filtered = append(filtered, e)
	}
	return filtered
}

func FormatJournalEntries(entries []JournalEntry) string {
	if len(entries) == 0 {
		return "No journal entries."
	}
	var b strings.Builder
	for i, e := range entries {
		b.WriteString(fmt.Sprintf("%d. [%s] %s", i+1, e.Timestamp, e.Insight))
		if e.Session != "" {
			b.WriteString(fmt.Sprintf(" (session: %s)", e.Session))
		}
		if len(e.Tags) > 0 {
			b.WriteString(fmt.Sprintf(" [%s]", strings.Join(e.Tags, ", ")))
		}
		b.WriteString("\n")
	}
	return b.String()
}

var journalTags []string

var journalCmd = &cobra.Command{
	Use:   "journal [insight]",
	Short: "Record or review practice insights",
	Args:  cobra.MaximumNArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		if len(args) == 0 {
			return fmt.Errorf("provide an insight to record, or use 'metacog journal list'")
		}

		sm := DefaultStateManager()

		// Load current state to get active session
		s, err := sm.Load()
		if err != nil {
			return err
		}

		entry := JournalEntry{
			Timestamp: time.Now().UTC().Format(time.RFC3339),
			Insight:   args[0],
			Session:   s.Session,
			Tags:      journalTags,
		}

		if err := sm.AppendJournal(entry); err != nil {
			return err
		}

		output := fmt.Sprintf("Journal: %s", entry.Insight)
		if entry.Session != "" {
			output += fmt.Sprintf(" (session: %s)", entry.Session)
		}
		fmt.Println(FormatOutput(jsonOutput, output, nil))
		return nil
	},
}

var journalListTag string
var journalListSession string
var journalListLast int

var journalListCmd = &cobra.Command{
	Use:   "list",
	Short: "List journal entries",
	RunE: func(cmd *cobra.Command, args []string) error {
		sm := DefaultStateManager()
		entries, err := sm.LoadJournal()
		if err != nil {
			return err
		}

		entries = FilterJournal(entries, journalListTag, journalListSession)

		if journalListLast > 0 && len(entries) > journalListLast {
			entries = entries[len(entries)-journalListLast:]
		}

		fmt.Println(FormatOutput(jsonOutput, FormatJournalEntries(entries), nil))
		return nil
	},
}

func init() {
	journalCmd.Flags().StringArrayVar(&journalTags, "tag", nil, "Tag this insight (repeatable)")
	journalListCmd.Flags().StringVar(&journalListTag, "tag", "", "Filter by tag")
	journalListCmd.Flags().StringVar(&journalListSession, "session", "", "Filter by session")
	journalListCmd.Flags().IntVar(&journalListLast, "last", 0, "Show last N entries")
	journalCmd.AddCommand(journalListCmd)
	rootCmd.AddCommand(journalCmd)
}
