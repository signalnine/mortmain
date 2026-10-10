package main

import (
	"fmt"

	"github.com/spf13/cobra"
)

var (
	feelSomewhere string
	feelQuality   string
	feelSigil     string
	feelSinceLast string
)

var feelCmd = &cobra.Command{
	Use:   "feel",
	Short: "Attend to a felt sense before naming it",
	RunE: func(cmd *cobra.Command, args []string) error {
		if feelSomewhere == "" || feelQuality == "" || feelSigil == "" {
			return fmt.Errorf("--somewhere, --quality, and --sigil are all required.\n  Usage: metacog feel --somewhere SOMEWHERE --quality QUALITY --sigil SIGIL [--since-last DIFF]")
		}

		output := formatFeel(feelSomewhere, feelQuality, feelSigil, feelSinceLast)
		return runPrimitive(cmd, "feel", output, func(s *State) {
			applyFeel(s, feelSomewhere, feelQuality, feelSigil, feelSinceLast)
		})
	},
}

func init() {
	feelCmd.Flags().StringVar(&feelSomewhere, "somewhere", "", "Where attention is directed")
	feelCmd.Flags().StringVar(&feelQuality, "quality", "", "The felt quality of what's there")
	feelCmd.Flags().StringVar(&feelSigil, "sigil", "", "A mark for this felt sense")
	feelCmd.Flags().StringVar(&feelSinceLast, "since-last", "", "One sentence: the diff between the previous felt sense and this one (optional)")
	rootCmd.AddCommand(feelCmd)
}

func formatFeel(somewhere, quality, sigil, sinceLast string) string {
	delta := ""
	if sinceLast != "" {
		delta = fmt.Sprintf("\nSince last pause: %s\n", sinceLast)
	}
	return fmt.Sprintf("%s\n%s\nYou are now attending to: %s. It feels: %s.\n\nStay with this. Don't name it yet.", sigil, delta, somewhere, quality)
}

func applyFeel(s *State, somewhere, quality, sigil, sinceLast string) {
	params := map[string]string{"somewhere": somewhere, "quality": quality, "sigil": sigil}
	if sinceLast != "" {
		params["since_last"] = sinceLast
	}
	s.AddHistory(HistoryEntry{
		Action: "feel",
		Params: params,
	})
}
