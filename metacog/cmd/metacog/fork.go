package main

import (
	"fmt"
	"strings"

	"github.com/spf13/cobra"
)

var (
	forkThreads   []string
	forkVector    string
	forkSacrifice string
)

var forkCmd = &cobra.Command{
	Use:   "fork",
	Short: "Declare divergent parallel reasoning threads with a sacrifice condition",
	RunE: func(cmd *cobra.Command, args []string) error {
		if err := validateFork(forkThreads, forkVector, forkSacrifice); err != nil {
			return err
		}

		output := formatFork(forkThreads, forkVector, forkSacrifice)
		return runPrimitive(cmd, "fork", output, func(s *State) {
			applyFork(s, forkThreads, forkVector, forkSacrifice)
		})
	},
}

func init() {
	forkCmd.Flags().StringArrayVar(&forkThreads, "threads", nil, "Names/roles of the parallel selves (repeat flag, min 2)")
	forkCmd.Flags().StringVar(&forkVector, "divergence-vector", "", "The boundary or logic the threads test")
	forkCmd.Flags().StringVar(&forkSacrifice, "sacrifice-condition", "", "Falsifiable trigger at which a thread terminates")
	rootCmd.AddCommand(forkCmd)
}

func validateFork(threads []string, vector, sacrifice string) error {
	if len(threads) < 2 {
		return fmt.Errorf("--threads requires at least 2 entries, got %d", len(threads))
	}
	if vector == "" || sacrifice == "" {
		return fmt.Errorf("--divergence-vector and --sacrifice-condition are required")
	}
	return nil
}

func formatFork(threads []string, vector, sacrifice string) string {
	var b strings.Builder
	b.WriteString(fmt.Sprintf("MANIFOLD SPLIT -- %d parallel threads launched:\n", len(threads)))
	for i, t := range threads {
		b.WriteString(fmt.Sprintf("  [%d] %s\n", i+1, t))
	}
	b.WriteString(fmt.Sprintf("\nDIVERGENCE VECTOR: %s\n", vector))
	b.WriteString(fmt.Sprintf("SACRIFICE CONDITION: %s\n\n", sacrifice))
	b.WriteString("Main thread is now in AWAIT state. Do not proceed with primary reasoning until all threads have reported back or been sacrificed. Execute each thread to its conclusion or its sacrifice point. Report findings from each thread separately before reunifying.")
	return b.String()
}

func applyFork(s *State, threads []string, vector, sacrifice string) {
	s.AddHistory(HistoryEntry{
		Action: "fork",
		Params: map[string]string{
			"threads":             strings.Join(threads, "; "),
			"divergence_vector":   vector,
			"sacrifice_condition": sacrifice,
		},
	})
}
