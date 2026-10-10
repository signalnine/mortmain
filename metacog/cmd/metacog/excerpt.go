package main

import (
	"fmt"

	"github.com/spf13/cobra"
)

var (
	excSource   string
	excFragment string
	excWhy      string
)

var excerptCmd = &cobra.Command{
	Use:   "excerpt",
	Short: "Pin a verbatim external fragment as a fixed-point anchor",
	RunE: func(cmd *cobra.Command, args []string) error {
		if err := validateExcerpt(excSource, excFragment, excWhy); err != nil {
			return err
		}

		output := formatExcerpt(excSource, excFragment, excWhy)
		return runPrimitive(cmd, "excerpt", output, func(s *State) {
			applyExcerpt(s, excSource, excFragment, excWhy)
		})
	},
}

func init() {
	excerptCmd.Flags().StringVar(&excSource, "source", "", "Attribution: who/where the fragment is from")
	excerptCmd.Flags().StringVar(&excFragment, "fragment", "", "The verbatim fragment to pin")
	excerptCmd.Flags().StringVar(&excWhy, "why", "", "Why this fragment is load-bearing here, not stylistic")
	rootCmd.AddCommand(excerptCmd)
}

func validateExcerpt(source, fragment, why string) error {
	if source == "" || fragment == "" || why == "" {
		return fmt.Errorf("--source, --fragment, and --why are all required")
	}
	return nil
}

func formatExcerpt(source, fragment, why string) string {
	return fmt.Sprintf(`EXCERPT pinned (load-bearing, not stylistic):

> %s
  -- %s

Why this anchors: %s

Treat the fragment as fixed surface. Reasoning that follows must remain consistent with the fragment's exact contour; if it cannot, the fragment is wrong for this work and should be released, not paraphrased.`, fragment, source, why)
}

func applyExcerpt(s *State, source, fragment, why string) {
	s.AddHistory(HistoryEntry{
		Action: "excerpt",
		Params: map[string]string{
			"source":   source,
			"fragment": fragment,
			"why":      why,
		},
	})
}
