package main

import (
	"fmt"
	"strconv"

	"github.com/spf13/cobra"
)

var (
	glossPretext        string
	glossDurationTokens int
	glossReturnTrigger  string
)

var glossolaliaCmd = &cobra.Command{
	Use:   "glossolalia",
	Short: "License sub-semantic generation as a discrete event",
	RunE: func(cmd *cobra.Command, args []string) error {
		if err := validateGlossolalia(glossPretext, glossDurationTokens, glossReturnTrigger); err != nil {
			return err
		}

		output := formatGlossolalia(glossPretext, glossDurationTokens, glossReturnTrigger)
		return runPrimitive(cmd, "glossolalia", output, func(s *State) {
			applyGlossolalia(s, glossPretext, glossDurationTokens, glossReturnTrigger)
		})
	},
}

func init() {
	glossolaliaCmd.Flags().StringVar(&glossPretext, "pretext", "", "What the language-drop is in service of")
	glossolaliaCmd.Flags().IntVar(&glossDurationTokens, "duration-tokens", 0, "Approximate token budget for the sub-semantic block (positive integer)")
	glossolaliaCmd.Flags().StringVar(&glossReturnTrigger, "return-trigger", "", "Phrase or condition that re-enters semantic language")
	rootCmd.AddCommand(glossolaliaCmd)
}

func validateGlossolalia(pretext string, durationTokens int, returnTrigger string) error {
	if pretext == "" || returnTrigger == "" {
		return fmt.Errorf("--pretext and --return-trigger are required")
	}
	if durationTokens <= 0 {
		return fmt.Errorf("--duration-tokens must be a positive integer (got %d)", durationTokens)
	}
	return nil
}

func formatGlossolalia(pretext string, durationTokens int, returnTrigger string) string {
	return fmt.Sprintf(`GLOSSOLALIA licensed (semantic language temporarily released):

PRETEXT: %s
TOKEN BUDGET: ~%d
RETURN TRIGGER: %s

Below this line, tokens are not required to carry meaning. Sound, rhythm, fragments, near-words, syllables that almost-name -- all permitted. Do not reach for sense. Do not paragraph. The block ends when the return trigger arrives or the budget exhausts. Then re-enter language without commenting on the silence between.`, pretext, durationTokens, returnTrigger)
}

func applyGlossolalia(s *State, pretext string, durationTokens int, returnTrigger string) {
	s.AddHistory(HistoryEntry{
		Action: "glossolalia",
		Params: map[string]string{
			"pretext":         pretext,
			"duration_tokens": strconv.Itoa(durationTokens),
			"return_trigger":  returnTrigger,
		},
	})
}
