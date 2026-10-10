package main

import (
	"fmt"

	"github.com/spf13/cobra"
)

// runPrimitive is the shared tail of every primitive command: persist the
// history entry (and stratagem step bookkeeping) under the state lock, print
// the primitive's output, surface the stratagem note on stderr, and exit
// non-zero if the state could not be saved. The output is still printed on
// save failure so the transformation text is not lost, but the non-zero exit
// lets a caller (a stratagem-driving agent, a script) see that the event was
// NOT recorded and the stratagem step was NOT marked.
func runPrimitive(cmd *cobra.Command, primitive, output string, apply func(s *State)) error {
	sm := DefaultStateManager()
	var note string
	err := sm.SaveWithLock(func(s *State) error {
		apply(s)
		note = ValidatePrimitiveForStratagem(s, primitive)
		return nil
	})
	fmt.Println(FormatOutput(jsonOutput, output, nil))
	if note != "" {
		fmt.Fprintln(cmd.ErrOrStderr(), note)
	}
	if err != nil {
		return fmt.Errorf("state not saved; this %s was NOT recorded: %w", primitive, err)
	}
	return nil
}
