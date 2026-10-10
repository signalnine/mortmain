package main

import (
	"fmt"

	"github.com/spf13/cobra"
)

var (
	commBinding   string
	commStakes    string
	commFalsifier string
)

var commitmentCmd = &cobra.Command{
	Use:   "commitment",
	Short: "Pre-commit to a binding stance with stated stakes and falsifier",
	RunE: func(cmd *cobra.Command, args []string) error {
		if err := validateCommitment(commBinding, commStakes, commFalsifier); err != nil {
			return err
		}

		output := formatCommitment(commBinding, commStakes, commFalsifier)
		return runPrimitive(cmd, "commitment", output, func(s *State) {
			applyCommitment(s, commBinding, commStakes, commFalsifier)
		})
	},
}

func init() {
	commitmentCmd.Flags().StringVar(&commBinding, "binding", "", "The stance/prediction/position being committed to")
	commitmentCmd.Flags().StringVar(&commStakes, "stakes", "", "What is on the line if the binding turns out wrong")
	commitmentCmd.Flags().StringVar(&commFalsifier, "falsifier", "", "Specific observation that would falsify the binding")
	rootCmd.AddCommand(commitmentCmd)
}

func validateCommitment(binding, stakes, falsifier string) error {
	if binding == "" || stakes == "" || falsifier == "" {
		return fmt.Errorf("--binding, --stakes, and --falsifier are all required")
	}
	return nil
}

func formatCommitment(binding, stakes, falsifier string) string {
	return fmt.Sprintf(`COMMITMENT bound (active until ritual or stratagem boundary):

BINDING: %s
STAKES: %s
FALSIFIER: %s

Reasoning that follows is now constrained by this binding. Motivated reasoning becomes visible against the falsifier. To release the commitment, name the falsifier as triggered or invoke ritual to seal a different ground.`, binding, stakes, falsifier)
}

func applyCommitment(s *State, binding, stakes, falsifier string) {
	s.AddHistory(HistoryEntry{
		Action: "commitment",
		Params: map[string]string{
			"binding":   binding,
			"stakes":    stakes,
			"falsifier": falsifier,
		},
	})
}
