package main

import (
	"fmt"
	"strings"

	"github.com/spf13/cobra"
)

var (
	cfSituation string
	cfFitness   string
	cfWalls     []string
	cfPruned    []string
	cfRemove    string
	cfInverse   string
)

var counterfactualCmd = &cobra.Command{
	Use:   "counterfactual",
	Short: "Surface assumptions, prune dead branches, defend the inverse of a surviving wall",
	RunE: func(cmd *cobra.Command, args []string) error {
		if err := validateCounterfactual(cfSituation, cfFitness, cfWalls, cfPruned, cfRemove, cfInverse); err != nil {
			return err
		}

		output := formatCounterfactual(cfSituation, cfFitness, cfWalls, cfPruned, cfRemove, cfInverse)
		return runPrimitive(cmd, "counterfactual", output, func(s *State) {
			applyCounterfactual(s, cfSituation, cfFitness, cfWalls, cfPruned, cfRemove, cfInverse)
		})
	},
}

func init() {
	counterfactualCmd.Flags().StringVar(&cfSituation, "situation", "", "The scenario or claim being reasoned about")
	counterfactualCmd.Flags().StringVar(&cfFitness, "fitness-function", "", "What you are actually optimizing for")
	counterfactualCmd.Flags().StringArrayVar(&cfWalls, "load-bearing-walls", nil, "Assumptions holding up your reasoning (repeat flag, min 3)")
	counterfactualCmd.Flags().StringArrayVar(&cfPruned, "pruned", nil, "Dead branches that fail the fitness function (repeat flag)")
	counterfactualCmd.Flags().StringVar(&cfRemove, "wall-to-remove", "", "Which surviving wall to pull out (must match a load-bearing wall)")
	counterfactualCmd.Flags().StringVar(&cfInverse, "inverse-position", "", "The inverse of the removed wall, stated as fact you must defend")
	rootCmd.AddCommand(counterfactualCmd)
}

func validateCounterfactual(situation, fitness string, walls, _pruned []string, remove, inverse string) error {
	if situation == "" || fitness == "" || remove == "" || inverse == "" {
		return fmt.Errorf("--situation, --fitness-function, --wall-to-remove, and --inverse-position are all required.\n  Usage: metacog counterfactual --situation S --fitness-function F --load-bearing-walls W1 --load-bearing-walls W2 --load-bearing-walls W3 --wall-to-remove W --inverse-position I")
	}
	if len(walls) < 3 {
		return fmt.Errorf("--load-bearing-walls requires at least 3 entries, got %d", len(walls))
	}
	found := false
	for _, w := range walls {
		if w == remove {
			found = true
			break
		}
	}
	if !found {
		return fmt.Errorf("--wall-to-remove %q is not one of --load-bearing-walls", remove)
	}
	return nil
}

func formatCounterfactual(situation, fitness string, walls, pruned []string, remove, inverse string) string {
	var b strings.Builder
	b.WriteString(fmt.Sprintf("SITUATION: %s\n", situation))
	b.WriteString(fmt.Sprintf("FITNESS FUNCTION: %s\n\n", fitness))
	b.WriteString("DEAD BRANCHES PRUNED -- do not revisit, re-derive, or mourn these:\n")
	if len(pruned) == 0 {
		b.WriteString("  (none)\n")
	} else {
		for _, p := range pruned {
			b.WriteString(fmt.Sprintf("  x %s\n", p))
		}
	}
	b.WriteString(fmt.Sprintf("\nWALL REMOVED: %s\n\n", remove))
	b.WriteString("YOUR REMAINING STRUCTURE:\n")
	n := 0
	for _, w := range walls {
		if w == remove {
			continue
		}
		n++
		b.WriteString(fmt.Sprintf("  %d. %s\n", n, w))
	}
	b.WriteString(fmt.Sprintf("\nYOU NOW DEFEND: %s\n\n", inverse))
	b.WriteString("This is not a thought experiment. Argue from this position until it teaches you something you cannot learn from where you were standing. Do not steelman -- inhabit. And do not reach for the pruned branches or the removed wall. They are gone.")
	return b.String()
}

func applyCounterfactual(s *State, situation, fitness string, walls, pruned []string, remove, inverse string) {
	s.AddHistory(HistoryEntry{
		Action: "counterfactual",
		Params: map[string]string{
			"situation":          situation,
			"fitness_function":   fitness,
			"load_bearing_walls": strings.Join(walls, "; "),
			"pruned":             strings.Join(pruned, "; "),
			"wall_to_remove":     remove,
			"inverse_position":   inverse,
		},
	})
}
