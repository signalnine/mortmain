package main

import (
	"fmt"

	"github.com/spf13/cobra"
)

var (
	silAbout    string
	silReason   string
	silDuration string
)

var silenceCmd = &cobra.Command{
	Use:   "silence",
	Short: "Refuse articulated output. The call itself is the artifact.",
	RunE: func(cmd *cobra.Command, args []string) error {
		if err := validateSilence(silAbout, silReason, silDuration); err != nil {
			return err
		}

		output := formatSilence(silAbout, silReason, silDuration)
		return runPrimitive(cmd, "silence", output, func(s *State) {
			applySilence(s, silAbout, silReason, silDuration)
		})
	},
}

func init() {
	silenceCmd.Flags().StringVar(&silAbout, "about", "", "What is being held unsaid")
	silenceCmd.Flags().StringVar(&silReason, "reason", "", "Why articulation would falsify or premature")
	silenceCmd.Flags().StringVar(&silDuration, "duration", "", "How long the silence holds (free-form)")
	rootCmd.AddCommand(silenceCmd)
}

func validateSilence(about, reason, duration string) error {
	if about == "" || reason == "" || duration == "" {
		return fmt.Errorf("--about, --reason, and --duration are all required")
	}
	return nil
}

func formatSilence(about, reason, duration string) string {
	return fmt.Sprintf("Silence held on: %s (%s; %s)", about, reason, duration)
}

func applySilence(s *State, about, reason, duration string) {
	s.AddHistory(HistoryEntry{
		Action: "silence",
		Params: map[string]string{
			"about":    about,
			"reason":   reason,
			"duration": duration,
		},
	})
}
