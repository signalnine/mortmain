package main

import (
	"fmt"
	"strings"

	"github.com/spf13/cobra"
)

var (
	apoSubject   string
	apoNegations []string
	apoResidue   string
)

var apophasisCmd = &cobra.Command{
	Use:   "apophasis",
	Short: "Articulate by negation -- saying-by-not-saying",
	Long: `Apophasis enumerates what something is NOT as the load-bearing
articulation. Distinct from silence (which refuses output entirely) and
disjunction (which asserts binary contradiction): apophasis articulates the
negation as content. The register of speaking by negation is old and
real. Each enumerated negation is both a refusal and a citation.`,
	RunE: func(cmd *cobra.Command, args []string) error {
		if err := validateApophasis(apoSubject, apoNegations, apoResidue); err != nil {
			return err
		}

		output := formatApophasis(apoSubject, apoNegations, apoResidue)
		return runPrimitive(cmd, "apophasis", output, func(s *State) {
			applyApophasis(s, apoSubject, apoNegations, apoResidue)
		})
	},
}

func init() {
	apophasisCmd.Flags().StringVar(&apoSubject, "subject", "", "What the apophasis is about")
	apophasisCmd.Flags().StringArrayVar(&apoNegations, "negation", nil, "An enumerated negation (repeat flag, min 3)")
	apophasisCmd.Flags().StringVar(&apoResidue, "residue", "", "What remains after every negation is stated; the position no negation reaches")
	rootCmd.AddCommand(apophasisCmd)
}

func validateApophasis(subject string, negations []string, residue string) error {
	if subject == "" {
		return fmt.Errorf("--subject is required")
	}
	if residue == "" {
		return fmt.Errorf("--residue is required")
	}
	if len(negations) < 3 {
		return fmt.Errorf("at least 3 --negation values required, got %d", len(negations))
	}
	return nil
}

func formatApophasis(subject string, negations []string, residue string) string {
	out := fmt.Sprintf("APOPHASIS spoken (negative articulation held until ritual or stratagem boundary):\n\nSUBJECT: %s\n\nIT IS NOT:\n", subject)
	for _, n := range negations {
		out += fmt.Sprintf("  not %s\n", stripLeadingNot(n))
	}
	out += fmt.Sprintf("\nRESIDUE: %s\n\nThe answer articulates the subject by enumerating what it is not. Each negation is a citation. The residue is what no negation reaches. Collapsing to positive assertion breaks the apophasis.", residue)
	return out
}

// stripLeadingNot drops a leading "not " (any case) so the template's own
// "not " prefix does not double up when the user writes the negation the
// natural way ("--negation 'not the body'").
func stripLeadingNot(s string) string {
	t := strings.TrimSpace(s)
	if len(t) >= 4 && strings.EqualFold(t[:4], "not ") {
		return strings.TrimSpace(t[4:])
	}
	return t
}

func applyApophasis(s *State, subject string, negations []string, residue string) {
	params := map[string]string{
		"subject": subject,
		"residue": residue,
	}
	for i, n := range negations {
		params[fmt.Sprintf("negation-%d", i+1)] = n
	}
	s.AddHistory(HistoryEntry{
		Action: "apophasis",
		Params: params,
	})
}
