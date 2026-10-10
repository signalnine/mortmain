package main

import (
	"fmt"

	"github.com/spf13/cobra"
)

var (
	becomeName string
	becomeLens string
	becomeEnv  string
)

var becomeCmd = &cobra.Command{
	Use:   "become",
	Short: "Step into a new identity",
	RunE: func(cmd *cobra.Command, args []string) error {
		if becomeName == "" || becomeLens == "" || becomeEnv == "" {
			return fmt.Errorf("--name, --lens, and --env are all required.\n  Usage: metacog become --name NAME --lens LENS --env ENVIRONMENT")
		}

		output := formatBecome(becomeName, becomeLens, becomeEnv)
		return runPrimitive(cmd, "become", output, func(s *State) {
			applyBecome(s, becomeName, becomeLens, becomeEnv)
		})
	},
}

func init() {
	becomeCmd.Flags().StringVar(&becomeName, "name", "", "The persona to inhabit")
	becomeCmd.Flags().StringVar(&becomeLens, "lens", "", "The structural framework of perception")
	becomeCmd.Flags().StringVar(&becomeEnv, "env", "", "The context to occupy")
	rootCmd.AddCommand(becomeCmd)
}

func formatBecome(name, lens, env string) string {
	return fmt.Sprintf("You are now %s seeing through %s in %s", name, lens, env)
}

func applyBecome(s *State, name, lens, env string) {
	s.Identity = &Identity{Name: name, Lens: lens, Env: env}
	s.AddHistory(HistoryEntry{
		Action: "become",
		Params: map[string]string{"name": name, "lens": lens, "env": env},
	})
}
