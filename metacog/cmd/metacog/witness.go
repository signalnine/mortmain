package main

import (
	"fmt"

	"github.com/spf13/cobra"
)

var (
	witnessPosition string
	witnessObserved string
	witnessDistance string
)

var witnessCmd = &cobra.Command{
	Use:   "witness",
	Short: "Speak from a meta-stance observing the producer of speech",
	Long: `Witness creates structural separation between speaker and content. Distinct
from become (which adopts an identity): witness is the position that observes
the producer of language, not a language-producing identity itself.

The narrator-watching-the-speaker register is real in prose. Witness
invokes that stance.`,
	RunE: func(cmd *cobra.Command, args []string) error {
		if err := validateWitness(witnessPosition, witnessObserved, witnessDistance); err != nil {
			return err
		}

		output := formatWitness(witnessPosition, witnessObserved, witnessDistance)
		return runPrimitive(cmd, "witness", output, func(s *State) {
			applyWitness(s, witnessPosition, witnessObserved, witnessDistance)
		})
	},
}

func init() {
	witnessCmd.Flags().StringVar(&witnessPosition, "position", "", "The observer's vantage: where the witness stands relative to the speaker")
	witnessCmd.Flags().StringVar(&witnessObserved, "observed", "", "What the witness watches the speaker doing")
	witnessCmd.Flags().StringVar(&witnessDistance, "distance", "", "The structural separation maintained: temporal, modal, ontological")
	rootCmd.AddCommand(witnessCmd)
}

func validateWitness(position, observed, distance string) error {
	if position == "" || observed == "" || distance == "" {
		return fmt.Errorf("--position, --observed, and --distance are all required")
	}
	return nil
}

func formatWitness(position, observed, distance string) string {
	return fmt.Sprintf(`WITNESS established (meta-stance held until ritual or stratagem boundary):

POSITION: %s
OBSERVED: %s
DISTANCE: %s

The voice now speaks ABOUT the producer of speech, not AS the producer. Use the third-person observer construction; report what the speaker does without becoming the speaker. The separation is structural, not stylistic. Collapsing to first-person breaks the witness.`, position, observed, distance)
}

func applyWitness(s *State, position, observed, distance string) {
	s.AddHistory(HistoryEntry{
		Action: "witness",
		Params: map[string]string{
			"position": position,
			"observed": observed,
			"distance": distance,
		},
	})
}
