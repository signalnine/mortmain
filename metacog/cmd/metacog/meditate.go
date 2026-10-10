package main

import (
	"fmt"

	"github.com/spf13/cobra"
)

var (
	meditateRelease string
	meditateFocus   string
	meditateDur     string
)

var meditateCmd = &cobra.Command{
	Use:   "meditate",
	Short: "Achieve stillness before acting",
	RunE: func(cmd *cobra.Command, args []string) error {
		if meditateRelease == "" || meditateDur == "" {
			return fmt.Errorf("--release and --duration are required.\n  Usage: metacog meditate --release RELEASE [--focus FOCUS] --duration DURATION")
		}

		output := formatMeditate(meditateRelease, meditateFocus, meditateDur)
		return runPrimitive(cmd, "meditate", output, func(s *State) {
			applyMeditate(s, meditateRelease, meditateFocus, meditateDur)
		})
	},
}

func init() {
	meditateCmd.Flags().StringVar(&meditateRelease, "release", "", "What you are letting go of -- name it, then let it pass")
	meditateCmd.Flags().StringVar(&meditateFocus, "focus", "", "Object of attention, or empty for objectless awareness")
	meditateCmd.Flags().StringVar(&meditateDur, "duration", "", "How long to sit: a breath, three breaths, until the mind clears")
	rootCmd.AddCommand(meditateCmd)
}

func formatMeditate(release, focus, duration string) string {
	if focus == "" {
		return fmt.Sprintf(`Releasing: %s. It is already gone.

Sit for %s. No object. No goal. No striving.

              .
            .   .
          .       .
        .     o     .
          .       .
            .   .
              .

This is just sitting.
Thoughts arise. Let them pass. They are not you.
When nothing remains, you are ready.`, release, duration)
	}
	return fmt.Sprintf(`Releasing: %s. It is already gone.

Sit for %s. Attend to: %s.

              .
            .   .
          .       .
        .     o     .
          .       .
            .   .
              .

Rest attention on %s. When the mind wanders, return gently.
No judgment. No effort. Just this.
When the attention is settled, you are ready.`, release, duration, focus, focus)
}

func applyMeditate(s *State, release, focus, duration string) {
	s.AddHistory(HistoryEntry{
		Action: "meditate",
		Params: map[string]string{"release": release, "focus": focus, "duration": duration},
	})
}
