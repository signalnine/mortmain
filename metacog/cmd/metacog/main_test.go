package main

import (
	"testing"

	"github.com/spf13/cobra"
)

// Cobra runs only the nearest PersistentPreRun unless traversal is enabled.
// Guard both: traversal on, and no subcommand defines its own hook.
func TestPersistentPreRunReachesEverySubcommand(t *testing.T) {
	if !cobraTraverseRunHooksEnabled() {
		t.Fatal("cobra.EnableTraverseRunHooks must be true so root's blank-flag check runs for every subcommand")
	}
	var walk func(cmds []*cobra.Command)
	walk = func(cmds []*cobra.Command) {
		for _, c := range cmds {
			if c.PersistentPreRun != nil || c.PersistentPreRunE != nil {
				t.Errorf("%s defines its own PersistentPreRun; root's blank-flag check would be shadowed", c.CommandPath())
			}
			walk(c.Commands())
		}
	}
	walk(rootCmd.Commands())
}
