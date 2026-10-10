package main

import (
	"fmt"

	"github.com/spf13/cobra"
)

var (
	disjA       string
	disjB       string
	disjWhyBoth string
)

var disjunctionCmd = &cobra.Command{
	Use:   "disjunction",
	Short: "Assert two propositions that must both be true even though they cannot be",
	RunE: func(cmd *cobra.Command, args []string) error {
		if err := validateDisjunction(disjA, disjB, disjWhyBoth); err != nil {
			return err
		}

		output := formatDisjunction(disjA, disjB, disjWhyBoth)
		return runPrimitive(cmd, "disjunction", output, func(s *State) {
			applyDisjunction(s, disjA, disjB, disjWhyBoth)
		})
	},
}

func init() {
	disjunctionCmd.Flags().StringVar(&disjA, "proposition-a", "", "First proposition (must be true)")
	disjunctionCmd.Flags().StringVar(&disjB, "proposition-b", "", "Second proposition (must be true)")
	disjunctionCmd.Flags().StringVar(&disjWhyBoth, "why-both-required", "", "Why both load-bearing here, not lens-conflict but hard contradiction")
	rootCmd.AddCommand(disjunctionCmd)
}

func validateDisjunction(a, b, whyBoth string) error {
	if a == "" || b == "" || whyBoth == "" {
		return fmt.Errorf("--proposition-a, --proposition-b, and --why-both-required are all required")
	}
	return nil
}

func formatDisjunction(a, b, whyBoth string) string {
	return fmt.Sprintf(`DISJUNCTION held:

A: %s
B: %s

A and B cannot both be true. A and B must both be true. Why both required: %s

Do not resolve. Do not pick. Do not blend into a third position. Reasoning happens INSIDE this contradiction, not despite it. The contradiction is the operand, not the obstacle.`, a, b, whyBoth)
}

func applyDisjunction(s *State, a, b, whyBoth string) {
	s.AddHistory(HistoryEntry{
		Action: "disjunction",
		Params: map[string]string{
			"proposition_a":     a,
			"proposition_b":     b,
			"why_both_required": whyBoth,
		},
	})
}
