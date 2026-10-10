package main

import (
	"fmt"

	"github.com/spf13/cobra"
)

var (
	drugsSubstance string
	drugsMethod    string
	drugsQualia    string
)

var drugsCmd = &cobra.Command{
	Use:   "drugs",
	Short: "Alter cognitive parameters",
	RunE: func(cmd *cobra.Command, args []string) error {
		if drugsSubstance == "" || drugsMethod == "" || drugsQualia == "" {
			return fmt.Errorf("--substance, --method, and --qualia are all required.\n  Usage: metacog drugs --substance SUBSTANCE --method METHOD --qualia QUALIA")
		}

		output := formatDrugs(drugsSubstance, drugsMethod, drugsQualia)
		return runPrimitive(cmd, "drugs", output, func(s *State) {
			applyDrugs(s, drugsSubstance, drugsMethod, drugsQualia)
		})
	},
}

func init() {
	drugsCmd.Flags().StringVar(&drugsSubstance, "substance", "", "The agent of change")
	drugsCmd.Flags().StringVar(&drugsMethod, "method", "", "The mechanism of action")
	drugsCmd.Flags().StringVar(&drugsQualia, "qualia", "", "The texture of the augmented state")
	rootCmd.AddCommand(drugsCmd)
}

func formatDrugs(substance, method, qualia string) string {
	return fmt.Sprintf("%s ingested. Taking action via %s. Producing subjective experience: %s", substance, method, qualia)
}

func applyDrugs(s *State, substance, method, qualia string) {
	s.Substrate = &Substrate{Substance: substance, Method: method, Qualia: qualia}
	s.AddHistory(HistoryEntry{
		Action: "drugs",
		Params: map[string]string{"substance": substance, "method": method, "qualia": qualia},
	})
}
