package main

import (
	"fmt"
	"sort"
	"strings"

	"github.com/spf13/cobra"
)

func containsString(list []string, v string) bool {
	for _, x := range list {
		if x == v {
			return true
		}
	}
	return false
}

// allStratagemNames returns the sorted names of every loadable rite.
func allStratagemNames() []string {
	return riteNames(LoadRites())
}

// primitiveDescriptors is the short "what this primitive offers" phrase used
// by the Underused section. Keep one entry per PrimitiveKinds member
// (registry_test.go checks).
var primitiveDescriptors = map[string]string{
	"feel": "felt sensing", "drugs": "substrate modification", "become": "identity shifting",
	"name": "true naming", "ritual": "threshold-crossing", "meditate": "stillness",
	"counterfactual": "assumption pruning", "synthesis": "three-lens tension", "fork": "parallel threads",
	"register": "voice re-pitching", "chord": "simultaneous attention", "silence": "withheld articulation",
	"excerpt": "fixed-point anchoring", "commitment": "pre-binding", "disjunction": "held contradiction",
	"glossolalia": "sub-semantic release", "witness": "observer stance", "apophasis": "articulation by negation",
}

// countPrimitives tallies primitive calls in history by action, plus the total.
func countPrimitives(s *State) (map[string]int, int) {
	counts := map[string]int{}
	total := 0
	for _, h := range s.History {
		if IsPrimitive(h.Action) {
			counts[h.Action]++
			total++
		}
	}
	return counts, total
}

func FormatReflection(s *State) string {
	if len(s.History) == 0 {
		return "No history to reflect on."
	}

	var b strings.Builder

	primitiveCounts, _ := countPrimitives(s)
	b.WriteString("Primitive usage:\n")
	anyUsed := false
	for _, k := range PrimitiveKinds {
		if c := primitiveCounts[string(k)]; c > 0 {
			b.WriteString(fmt.Sprintf("  %s: %d\n", k, c))
			anyUsed = true
		}
	}
	if !anyUsed {
		b.WriteString("  (none)\n")
	}

	identityCounts := map[string]int{}
	for _, h := range s.History {
		if h.Action == "become" {
			name := h.Params["name"]
			if name != "" {
				identityCounts[name]++
			}
		}
	}
	if len(identityCounts) > 0 {
		type kv struct {
			Key   string
			Value int
		}
		var sorted []kv
		for k, v := range identityCounts {
			sorted = append(sorted, kv{k, v})
		}
		sort.Slice(sorted, func(i, j int) bool { return sorted[i].Value > sorted[j].Value })

		b.WriteString("\nTop identities:\n")
		limit := 5
		if len(sorted) < limit {
			limit = len(sorted)
		}
		for _, kv := range sorted[:limit] {
			b.WriteString(fmt.Sprintf("  %s (%dx)\n", kv.Key, kv.Value))
		}
	}

	substrateCounts := map[string]int{}
	for _, h := range s.History {
		if h.Action == "drugs" {
			sub := h.Params["substance"]
			if sub != "" {
				substrateCounts[sub]++
			}
		}
	}
	if len(substrateCounts) > 0 {
		type kv struct {
			Key   string
			Value int
		}
		var sorted []kv
		for k, v := range substrateCounts {
			sorted = append(sorted, kv{k, v})
		}
		sort.Slice(sorted, func(i, j int) bool { return sorted[i].Value > sorted[j].Value })

		b.WriteString("\nTop substrates:\n")
		limit := 5
		if len(sorted) < limit {
			limit = len(sorted)
		}
		for _, kv := range sorted[:limit] {
			b.WriteString(fmt.Sprintf("  %s (%dx)\n", kv.Key, kv.Value))
		}
	}

	stratagemCompleted := map[string]int{}
	for _, h := range s.History {
		if h.Action == "stratagem" && h.Params["event"] == "completed" {
			stratagemCompleted[h.Params["name"]]++
		}
	}

	b.WriteString("\nStratagem completions:\n")
	allStratagems := allStratagemNames()
	// Rites live on disk and can disappear; completions of a rite that is no
	// longer loadable are still part of the record.
	listed := append([]string{}, allStratagems...)
	for name := range stratagemCompleted {
		if !containsString(allStratagems, name) {
			listed = append(listed, name)
		}
	}
	sort.Strings(listed)
	hasAny := false
	for _, name := range listed {
		if c, ok := stratagemCompleted[name]; ok {
			b.WriteString(fmt.Sprintf("  %s: %d\n", name, c))
			hasAny = true
		}
	}
	if !hasAny {
		b.WriteString("  (none)\n")
	}

	var neverCompleted []string
	for _, name := range allStratagems {
		if _, ok := stratagemCompleted[name]; !ok {
			neverCompleted = append(neverCompleted, name)
		}
	}
	if len(neverCompleted) > 0 {
		b.WriteString(fmt.Sprintf("  Never completed: %s\n", strings.Join(neverCompleted, ", ")))
	}

	// Effectiveness section -- only show if outcomes exist
	type outcomeStats struct {
		productive   int
		unproductive int
	}
	outcomesByStratagem := map[string]*outcomeStats{}
	for _, h := range s.History {
		if h.Action == "outcome" {
			name := h.Params["stratagem"]
			if name == "" {
				continue
			}
			if outcomesByStratagem[name] == nil {
				outcomesByStratagem[name] = &outcomeStats{}
			}
			if h.Params["result"] == "productive" {
				outcomesByStratagem[name].productive++
			} else {
				outcomesByStratagem[name].unproductive++
			}
		}
	}

	if len(outcomesByStratagem) > 0 {
		type effectivenessEntry struct {
			Name       string
			Rate       float64
			Productive int
			Total      int
		}
		var entries []effectivenessEntry
		totalProductive := 0
		totalOutcomes := 0
		for name, stats := range outcomesByStratagem {
			total := stats.productive + stats.unproductive
			rate := float64(stats.productive) / float64(total) * 100
			entries = append(entries, effectivenessEntry{name, rate, stats.productive, total})
			totalProductive += stats.productive
			totalOutcomes += total
		}
		sort.Slice(entries, func(i, j int) bool {
			if entries[i].Rate != entries[j].Rate {
				return entries[i].Rate > entries[j].Rate
			}
			return entries[i].Total > entries[j].Total
		})

		b.WriteString("\nEffectiveness (self-reported):\n")
		for _, e := range entries {
			tag := ""
			if e.Total < 3 {
				tag = " [provisional]"
			}
			b.WriteString(fmt.Sprintf("  %s: %.0f%% productive (%d/%d)%s\n", e.Name, e.Rate, e.Productive, e.Total, tag))
		}

		// Unmeasured: completed but no outcomes
		for _, name := range allStratagems {
			if _, hasOutcome := outcomesByStratagem[name]; !hasOutcome {
				if _, completed := stratagemCompleted[name]; completed {
					b.WriteString(fmt.Sprintf("  %s: unmeasured (%d completions, 0 outcomes)\n", name, stratagemCompleted[name]))
				}
			}
		}

		if totalOutcomes > 0 {
			overallRate := float64(totalProductive) / float64(totalOutcomes) * 100
			b.WriteString(fmt.Sprintf("\n  Overall: %.0f%% productive (%d/%d)\n", overallRate, totalProductive, totalOutcomes))
		}
	}

	totalSteps := 0
	ritualCount := 0
	for _, h := range s.History {
		if h.Action == "ritual" {
			stepsStr := h.Params["steps"]
			if stepsStr != "" {
				parts := strings.Split(stepsStr, "; ")
				totalSteps += len(parts)
				ritualCount++
			}
		}
	}
	if ritualCount > 0 {
		avg := float64(totalSteps) / float64(ritualCount)
		b.WriteString(fmt.Sprintf("\nRitual avg steps: %.1f (across %d rituals)\n", avg, ritualCount))
	}

	return b.String()
}

func FormatRecentInsights(entries []JournalEntry, n int) string {
	if len(entries) == 0 {
		return ""
	}
	if n > 0 && len(entries) > n {
		entries = entries[len(entries)-n:]
	}
	var b strings.Builder
	b.WriteString("\nRecent insights:\n")
	for _, e := range entries {
		b.WriteString(fmt.Sprintf("  [%s] %s", e.Timestamp, e.Insight))
		if len(e.Tags) > 0 {
			b.WriteString(fmt.Sprintf(" [%s]", strings.Join(e.Tags, ", ")))
		}
		b.WriteString("\n")
	}
	return b.String()
}

func FormatPracticePatterns(s *State) string {
	if len(s.History) == 0 {
		return ""
	}

	var b strings.Builder
	hasContent := false

	// What worked -- collect productive outcomes with their active configs
	type productiveEntry struct {
		stratagem string
		identity  string // "name/lens" or ""
		substance string // or ""
		shift     string // or ""
	}
	var productive []productiveEntry
	for i, h := range s.History {
		if h.Action != "outcome" || h.Params["result"] != "productive" {
			continue
		}
		entry := productiveEntry{
			stratagem: h.Params["stratagem"],
			shift:     h.Params["shift"],
		}
		// Scan backward for nearest become
		for j := i - 1; j >= 0; j-- {
			if s.History[j].Action == "become" {
				name := s.History[j].Params["name"]
				lens := s.History[j].Params["lens"]
				if name != "" {
					if lens != "" {
						entry.identity = name + "/" + lens
					} else {
						entry.identity = name
					}
				}
				break
			}
		}
		// Scan backward for nearest drugs
		for j := i - 1; j >= 0; j-- {
			if s.History[j].Action == "drugs" {
				sub := s.History[j].Params["substance"]
				if sub != "" {
					entry.substance = sub
				}
				break
			}
		}
		productive = append(productive, entry)
	}

	if len(productive) > 0 {
		hasContent = true
		total := len(productive)
		show := productive
		if len(show) > 5 {
			show = show[len(show)-5:]
		}

		if total > 5 {
			b.WriteString(fmt.Sprintf("\nPractice patterns:\n  What worked (last 5 of %d):\n", total))
		} else {
			b.WriteString("\nPractice patterns:\n  What worked:\n")
		}

		for _, e := range show {
			// Build config portion
			config := ""
			if e.identity != "" && e.substance != "" {
				config = e.identity + " + " + e.substance
			} else if e.identity != "" {
				config = e.identity
			} else if e.substance != "" {
				config = e.substance
			}

			stratLabel := e.stratagem
			if stratLabel == "" {
				stratLabel = "unknown"
			}

			if config != "" && e.shift != "" {
				b.WriteString(fmt.Sprintf("    %s -- %s -- %q\n", stratLabel, config, e.shift))
			} else if config != "" {
				b.WriteString(fmt.Sprintf("    %s -- %s\n", stratLabel, config))
			} else if e.shift != "" {
				b.WriteString(fmt.Sprintf("    %s -- (no config) -- %q\n", stratLabel, e.shift))
			} else {
				b.WriteString(fmt.Sprintf("    %s -- (no config)\n", stratLabel))
			}
		}

		if total > 5 {
			b.WriteString(fmt.Sprintf("    (%d more productive outcomes in history)\n", total-5))
		}
	}

	// Underused: once there are >= 5 primitive calls, flag used-but-rare
	// primitives (share below half the uniform share, i.e. 100/18/2 ~ 2.8%).
	// Never-used primitives go on a separate one-line Unexplored note: that
	// is information about the surface, not a judgement on balance, so
	// evenly balanced practice over a subset shows no Underused section.
	primitiveCounts, totalPrimitives := countPrimitives(s)
	if totalPrimitives >= 5 {
		threshold := 100.0 / float64(len(PrimitiveKinds)) / 2
		var rare, never []string
		for _, k := range PrimitiveKinds {
			p := string(k)
			count := primitiveCounts[p]
			if count == 0 {
				never = append(never, fmt.Sprintf("%s (%s)", p, primitiveDescriptors[p]))
				continue
			}
			pct := float64(count) / float64(totalPrimitives) * 100
			if pct < threshold {
				rare = append(rare, fmt.Sprintf("    %s is %.0f%% of your practice (%d of %d primitive calls) -- %s is available", p, pct, count, totalPrimitives, primitiveDescriptors[p]))
			}
		}
		if len(rare) > 0 {
			if !hasContent {
				b.WriteString("\nPractice patterns:\n")
			}
			b.WriteString("\n  Underused:\n")
			for _, r := range rare {
				b.WriteString(r + "\n")
			}
			hasContent = true
		}
		if len(never) > 0 {
			if !hasContent {
				b.WriteString("\nPractice patterns:\n")
			}
			b.WriteString(fmt.Sprintf("\n  Unexplored: %s\n", strings.Join(never, ", ")))
			hasContent = true
		}
	}

	if !hasContent {
		return ""
	}
	return b.String()
}

func FormatAdvisories(s *State, journal []JournalEntry) string {
	if len(s.History) == 0 {
		return ""
	}

	var advisories []string

	// 1. Unproductive streak -- scan backward for consecutive unproductive outcomes
	var streak int
	var streakNames []string
	for i := len(s.History) - 1; i >= 0; i-- {
		h := s.History[i]
		if h.Action != "outcome" {
			continue
		}
		if h.Params["result"] == "unproductive" {
			streak++
			name := h.Params["stratagem"]
			if name == "" {
				name = "unknown"
			}
			streakNames = append(streakNames, name)
		} else {
			break
		}
	}
	if streak >= 3 {
		advisories = append(advisories, fmt.Sprintf("!! %d unproductive outcomes in a row (last: %s)", streak, strings.Join(streakNames, ", ")))
	} else if streak == 2 {
		advisories = append(advisories, fmt.Sprintf("-- 2 unproductive outcomes in a row (last: %s)", strings.Join(streakNames, ", ")))
	}

	// 2. Low effectiveness -- stratagems/freestyle with 3+ outcomes and <50% productive
	type outcomeStats struct {
		productive   int
		unproductive int
	}
	outcomesByName := map[string]*outcomeStats{}
	for _, h := range s.History {
		if h.Action == "outcome" {
			name := h.Params["stratagem"]
			if name == "" {
				continue
			}
			if outcomesByName[name] == nil {
				outcomesByName[name] = &outcomeStats{}
			}
			if h.Params["result"] == "productive" {
				outcomesByName[name].productive++
			} else {
				outcomesByName[name].unproductive++
			}
		}
	}
	for name, stats := range outcomesByName {
		total := stats.productive + stats.unproductive
		if total < 3 {
			continue
		}
		rate := float64(stats.productive) / float64(total) * 100
		if rate < 33 {
			advisories = append(advisories, fmt.Sprintf("!! %s: %.0f%% productive (%d/%d)", name, rate, stats.productive, total))
		} else if rate < 50 {
			advisories = append(advisories, fmt.Sprintf("-- %s: %.0f%% productive (%d/%d)", name, rate, stats.productive, total))
		}
	}

	// 3. Never-tried stratagems -- only flag if user has 5+ total completions
	allStratagems := allStratagemNames()
	stratagemCompleted := map[string]int{}
	totalCompletions := 0
	for _, h := range s.History {
		if h.Action == "stratagem" && h.Params["event"] == "completed" {
			stratagemCompleted[h.Params["name"]]++
			totalCompletions++
		}
	}
	if totalCompletions >= 5 {
		var neverTried []string
		for _, name := range allStratagems {
			if stratagemCompleted[name] == 0 {
				neverTried = append(neverTried, name)
			}
		}
		if len(neverTried) > 0 {
			advisories = append(advisories, fmt.Sprintf("-- Never tried: %s", strings.Join(neverTried, ", ")))
		}
	}

	// 4. Over-reliance -- single identity >50% of last 20 becomes, or single substrate >50% of last 20 drugs
	checkOverReliance := func(action, paramKey, label string) {
		var recent []string
		for i := len(s.History) - 1; i >= 0 && len(recent) < 20; i-- {
			if s.History[i].Action == action {
				val := s.History[i].Params[paramKey]
				if val != "" {
					recent = append(recent, val)
				}
			}
		}
		if len(recent) < 4 {
			return
		}
		counts := map[string]int{}
		for _, v := range recent {
			counts[v]++
		}
		for val, count := range counts {
			if float64(count)/float64(len(recent)) > 0.5 {
				advisories = append(advisories, fmt.Sprintf("-- Over-reliance: %q used in %d of last %d %s", val, count, len(recent), label))
			}
		}
	}
	checkOverReliance("become", "name", "becomes")
	checkOverReliance("drugs", "substance", "drugs")

	// 5. Practice without reflection -- count recent primitives/stratagem-completeds before hitting an outcome
	unreflected := 0
	for i := len(s.History) - 1; i >= 0; i-- {
		h := s.History[i]
		if h.Action == "outcome" {
			break
		}
		switch h.Action {
		case "feel", "become", "drugs", "name", "ritual":
			unreflected++
		case "stratagem":
			if h.Params["event"] == "completed" {
				unreflected++
			}
		}
	}
	if unreflected >= 5 {
		advisories = append(advisories, fmt.Sprintf("-- %d recent primitives with no outcome recorded", unreflected))
	}

	// 6. Journal friction -- last 10 journal entries containing "stuck" or "unproductive"
	if len(journal) > 0 {
		start := 0
		if len(journal) > 10 {
			start = len(journal) - 10
		}
		for _, e := range journal[start:] {
			lower := strings.ToLower(e.Insight)
			if strings.Contains(lower, "stuck") || strings.Contains(lower, "unproductive") {
				advisories = append(advisories, fmt.Sprintf("-- Journal friction: %q", e.Insight))
			}
		}
	}

	if len(advisories) == 0 {
		return ""
	}

	var b strings.Builder
	b.WriteString("\nAdvisories:\n")
	for _, a := range advisories {
		b.WriteString(fmt.Sprintf("  %s\n", a))
	}
	return b.String()
}

var reflectCmd = &cobra.Command{
	Use:   "reflect",
	Short: "Show practice patterns from history",
	RunE: func(cmd *cobra.Command, args []string) error {
		sm := DefaultStateManager()
		s, err := sm.Load()
		if err != nil {
			return err
		}
		output := FormatReflection(s)

		journal, err := sm.LoadJournal()
		if err == nil && len(journal) > 0 {
			output += FormatRecentInsights(journal, 5)
		}

		output += FormatPracticePatterns(s)
		output += FormatAdvisories(s, journal)

		fmt.Println(FormatOutput(jsonOutput, output, nil))
		return nil
	},
}

func init() {
	rootCmd.AddCommand(reflectCmd)
}
