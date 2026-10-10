package main

import (
	"fmt"
	"strings"

	"github.com/spf13/cobra"
)

type Lens struct {
	Name      string
	Verdict   string
	Blindspot string
}

var (
	synProblem  string
	synAName    string
	synAVerdict string
	synABlind   string
	synBName    string
	synBVerdict string
	synBBlind   string
	synCName    string
	synCVerdict string
	synCBlind   string
	synTension  string
)

var synthesisCmd = &cobra.Command{
	Use:   "synthesis",
	Short: "Three irreconcilable lenses; name the suppressed tension between them",
	RunE: func(cmd *cobra.Command, args []string) error {
		a := Lens{Name: synAName, Verdict: synAVerdict, Blindspot: synABlind}
		b := Lens{Name: synBName, Verdict: synBVerdict, Blindspot: synBBlind}
		c := Lens{Name: synCName, Verdict: synCVerdict, Blindspot: synCBlind}
		if err := validateSynthesis(synProblem, a, b, c, synTension); err != nil {
			return err
		}

		output := formatSynthesis(synProblem, a, b, c, synTension)
		return runPrimitive(cmd, "synthesis", output, func(s *State) {
			applySynthesis(s, synProblem, a, b, c, synTension)
		})
	},
}

func init() {
	synthesisCmd.Flags().StringVar(&synProblem, "problem", "", "The problem requiring multi-perspective evaluation")
	synthesisCmd.Flags().StringVar(&synAName, "lens-a-name", "", "First lens: True Name")
	synthesisCmd.Flags().StringVar(&synAVerdict, "lens-a-verdict", "", "First lens: verdict")
	synthesisCmd.Flags().StringVar(&synABlind, "lens-a-blindspot", "", "First lens: structural blindspot")
	synthesisCmd.Flags().StringVar(&synBName, "lens-b-name", "", "Second lens: True Name")
	synthesisCmd.Flags().StringVar(&synBVerdict, "lens-b-verdict", "", "Second lens: verdict")
	synthesisCmd.Flags().StringVar(&synBBlind, "lens-b-blindspot", "", "Second lens: structural blindspot")
	synthesisCmd.Flags().StringVar(&synCName, "lens-c-name", "", "Third lens: True Name")
	synthesisCmd.Flags().StringVar(&synCVerdict, "lens-c-verdict", "", "Third lens: verdict")
	synthesisCmd.Flags().StringVar(&synCBlind, "lens-c-blindspot", "", "Third lens: structural blindspot")
	synthesisCmd.Flags().StringVar(&synTension, "suppressed-tension", "", "The irreducible friction between the three blindspots")
	rootCmd.AddCommand(synthesisCmd)
}

func validateSynthesis(problem string, a, b, c Lens, tension string) error {
	if problem == "" || tension == "" {
		return fmt.Errorf("--problem and --suppressed-tension are required")
	}
	for _, l := range []struct {
		label string
		lens  Lens
	}{{"a", a}, {"b", b}, {"c", c}} {
		if l.lens.Name == "" || l.lens.Verdict == "" || l.lens.Blindspot == "" {
			return fmt.Errorf("--lens-%s-name, --lens-%s-verdict, --lens-%s-blindspot are all required", l.label, l.label, l.label)
		}
	}
	return nil
}

func formatSynthesis(problem string, a, b, c Lens, tension string) string {
	var b2 strings.Builder
	b2.WriteString(fmt.Sprintf("PROBLEM: %s\n\n", problem))
	for _, x := range []struct {
		label string
		lens  Lens
	}{{"A", a}, {"B", b}, {"C", c}} {
		b2.WriteString(fmt.Sprintf("[LENS %s -- %s]: %s\n", x.label, x.lens.Name, x.lens.Verdict))
		b2.WriteString(fmt.Sprintf("  BLIND TO: %s\n", x.lens.Blindspot))
	}
	b2.WriteString(fmt.Sprintf("\nUNRESOLVED TENSION: %s\n\n", tension))
	b2.WriteString("Now speak from each lens in order. A, then B, then C. Do not blend. Do not resolve. Do not let one lens comment on another. When speaking as A, B and C do not exist. When speaking as B, A is a stranger's opinion. When speaking as C, the first two were wrong about everything that matters. Only after all three have spoken in full -- separately, completely, without contamination -- may you stand in the overlap of their blindspots. That is where the tension lives. It is not yours to fix.")
	return b2.String()
}

func applySynthesis(s *State, problem string, a, b, c Lens, tension string) {
	s.AddHistory(HistoryEntry{
		Action: "synthesis",
		Params: map[string]string{
			"problem":            problem,
			"lens_a_name":        a.Name,
			"lens_a_verdict":     a.Verdict,
			"lens_a_blindspot":   a.Blindspot,
			"lens_b_name":        b.Name,
			"lens_b_verdict":     b.Verdict,
			"lens_b_blindspot":   b.Blindspot,
			"lens_c_name":        c.Name,
			"lens_c_verdict":     c.Verdict,
			"lens_c_blindspot":   c.Blindspot,
			"suppressed_tension": tension,
		},
	})
}
