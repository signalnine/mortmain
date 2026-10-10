package main

import (
	"fmt"
	"github.com/spf13/pflag"
	"os"
	"strings"

	"github.com/spf13/cobra"
)

var Version = "6.12.0-mortmain"
var StateSchemaVersion = 1

var rootCmd = &cobra.Command{
	Use:               "metacog",
	Short:             "Metacognitive compositional engine",
	SilenceUsage:      true,
	PersistentPreRunE: rejectBlankStringFlags,
}

func cobraTraverseRunHooksEnabled() bool { return cobra.EnableTraverseRunHooks }

// rejectBlankStringFlags fails any string flag that was set to whitespace
// only ("--name '  '"). Values are never altered: an explicit empty string
// (meditate --focus "") stays legal, and inner/leading whitespace in a real
// value (an excerpt fragment) is preserved verbatim.
func rejectBlankStringFlags(cmd *cobra.Command, args []string) error {
	var blank []string
	cmd.Flags().VisitAll(func(f *pflag.Flag) {
		if f.Changed && f.Value.Type() == "string" {
			v := f.Value.String()
			if v != "" && strings.TrimSpace(v) == "" {
				blank = append(blank, "--"+f.Name)
			}
		}
	})
	if len(blank) > 0 {
		return fmt.Errorf("%s must not be blank (whitespace only)", strings.Join(blank, ", "))
	}
	return nil
}

var jsonOutput bool

// formatVersion derives the primitive list from the registry so it cannot
// drift from what the binary ships (registry_test.go). Stratagems are not
// compiled in and so are not listed; see 'metacog stratagem list'.
func formatVersion() string {
	return fmt.Sprintf("metacog %s\nstate schema: v%d\nprimitives: %s",
		Version, StateSchemaVersion,
		strings.Join(PrimitiveNames(), " "))
}

var versionCmd = &cobra.Command{
	Use:   "version",
	Short: "Print version information",
	Run: func(cmd *cobra.Command, args []string) {
		fmt.Println(FormatStructured(jsonOutput, formatVersion(), map[string]any{
			"version": Version, "schema_version": StateSchemaVersion,
			"primitives": PrimitiveNames(),
		}))
	},
}

func init() {
	// Run root's PersistentPreRunE even if a subcommand later defines its own
	// hook (cobra otherwise runs only the nearest one). main_test.go guards this.
	cobra.EnableTraverseRunHooks = true
	// The default completion command's help names shells and operating
	// systems; its text would land in an agent's context. Not shipped.
	rootCmd.CompletionOptions.DisableDefaultCmd = true
	rootCmd.PersistentFlags().BoolVar(&jsonOutput, "json", false, "Output in JSON format")
	rootCmd.AddCommand(versionCmd)
}

// exitCode lets a command request a specific non-zero exit without cobra
// printing an error (inspire --save relays the host's own error text).
var exitCode int

func main() {
	monastery := MonasteryMode()
	var before *ActiveStratagem
	if monastery {
		before = peekStratagem()
	}
	code := 0
	if err := rootCmd.Execute(); err != nil {
		code = 1
	} else if exitCode != 0 {
		code = exitCode
	}
	if monastery {
		writeEvent(os.Args[1:], code, before)
	}
	os.Exit(code)
}
