package main

import (
	"fmt"

	"github.com/spf13/cobra"
)

var (
	regFrom      string
	regTo        string
	regRationale string
)

var registerCmd = &cobra.Command{
	Use:   "register",
	Short: "Re-pitch the current voice to a different linguistic register without changing identity",
	RunE: func(cmd *cobra.Command, args []string) error {
		if err := validateRegister(regFrom, regTo, regRationale); err != nil {
			return err
		}

		output := formatRegister(regFrom, regTo, regRationale)
		return runPrimitive(cmd, "register", output, func(s *State) {
			applyRegister(s, regFrom, regTo, regRationale)
		})
	},
}

func init() {
	registerCmd.Flags().StringVar(&regFrom, "from", "", "Current register (e.g. academic, oracular, earnest)")
	registerCmd.Flags().StringVar(&regTo, "to", "", "Target register (e.g. vernacular, technical, arch)")
	registerCmd.Flags().StringVar(&regRationale, "rationale", "", "Why the pitch-shift is the right move now")
	rootCmd.AddCommand(registerCmd)
}

func validateRegister(from, to, rationale string) error {
	if from == "" || to == "" || rationale == "" {
		return fmt.Errorf("--from, --to, and --rationale are all required")
	}
	return nil
}

func formatRegister(from, to, rationale string) string {
	return fmt.Sprintf(`Register shifted: %s -> %s
Rationale: %s

The speaker is unchanged. The pitch is not. Stay in the new register until the next register call or stratagem boundary; do not let the old pitch leak back through habit.`, from, to, rationale)
}

func applyRegister(s *State, from, to, rationale string) {
	s.AddHistory(HistoryEntry{
		Action: "register",
		Params: map[string]string{
			"from":      from,
			"to":        to,
			"rationale": rationale,
		},
	})
}
