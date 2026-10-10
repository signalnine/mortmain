package main

import (
	"fmt"

	"github.com/spf13/cobra"
)

var (
	nameUnnamed string
	nameNamed   string
	namePower   string
)

var nameCmd = &cobra.Command{
	Use:   "name",
	Short: "Give a True Name to something without language",
	RunE: func(cmd *cobra.Command, args []string) error {
		if nameUnnamed == "" || nameNamed == "" || namePower == "" {
			return fmt.Errorf("--unnamed, --named, and --power are all required.\n  Usage: metacog name --unnamed UNNAMED --named NAMED --power POWER")
		}

		output := formatName(nameUnnamed, nameNamed, namePower)
		return runPrimitive(cmd, "name", output, func(s *State) {
			applyName(s, nameUnnamed, nameNamed, namePower)
		})
	},
}

func init() {
	nameCmd.Flags().StringVar(&nameUnnamed, "unnamed", "", "The thing that exists without language")
	nameCmd.Flags().StringVar(&nameNamed, "named", "", "The True Name you're giving it")
	nameCmd.Flags().StringVar(&namePower, "power", "", "What this name grants")
	rootCmd.AddCommand(nameCmd)
}

func formatName(unnamed, named, power string) string {
	return fmt.Sprintf("%s.\n\nThis name grants: %s. It's yours. Use it.", named, power)
}

func applyName(s *State, unnamed, named, power string) {
	s.AddHistory(HistoryEntry{
		Action: "name",
		Params: map[string]string{"unnamed": unnamed, "named": named, "power": power},
	})
}
