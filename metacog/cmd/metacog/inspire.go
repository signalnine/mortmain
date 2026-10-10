package main

import (
	"encoding/json"
	"fmt"
	"math/rand"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"syscall"

	"github.com/spf13/cobra"
)

type Stance struct {
	Who   string `json:"who"`
	Where string `json:"where"`
	Lens  string `json:"lens"`
}

type StancePool struct {
	Name    string
	Stances []Stance
}

// LoadStancePools returns the built-in pools. This build ships none: every
// pool comes from disk (personal, and ancestors in monastery mode).
func LoadStancePools() (map[string]StancePool, error) {
	return map[string]StancePool{}, nil
}

func ListPoolNames(pools map[string]StancePool) []string {
	names := make([]string, 0, len(pools))
	for name := range pools {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}

func RandomStance(pools map[string]StancePool, poolName string) (*Stance, string, error) {
	if poolName != "" {
		pool, ok := pools[poolName]
		if !ok {
			return nil, "", fmt.Errorf("unknown pool %q. Use --list to see available pools", poolName)
		}
		if len(pool.Stances) == 0 {
			return nil, "", fmt.Errorf("pool %q has no stances", poolName)
		}
		s := pool.Stances[rand.Intn(len(pool.Stances))]
		return &s, poolName, nil
	}

	names := ListPoolNames(pools)
	nonEmpty := make([]string, 0, len(names))
	for _, n := range names {
		if len(pools[n].Stances) > 0 {
			nonEmpty = append(nonEmpty, n)
		}
	}
	if len(nonEmpty) == 0 {
		return nil, "", fmt.Errorf("no stance pools loaded")
	}
	chosen := nonEmpty[rand.Intn(len(nonEmpty))]
	pool := pools[chosen]
	s := pool.Stances[rand.Intn(len(pool.Stances))]
	return &s, chosen, nil
}

type PersonalStance struct {
	Who       string `json:"who"`
	Where     string `json:"where"`
	Lens      string `json:"lens"`
	Substance string `json:"substance,omitempty"`
	Method    string `json:"method,omitempty"`
	Qualia    string `json:"qualia,omitempty"`
}

func SavePersonalStance(metacogDir string, s *State) (bool, error) {
	if s.Identity == nil {
		return false, fmt.Errorf("no identity set. Use 'metacog become' first")
	}

	stance := PersonalStance{
		Who:   s.Identity.Name,
		Where: s.Identity.Env,
		Lens:  s.Identity.Lens,
	}
	if s.Substrate != nil {
		stance.Substance = s.Substrate.Substance
		stance.Method = s.Substrate.Method
		stance.Qualia = s.Substrate.Qualia
	}

	stancesDir := filepath.Join(metacogDir, "stances")
	os.MkdirAll(stancesDir, 0755)
	poolPath := filepath.Join(stancesDir, "personal.json")
	lockPath := filepath.Join(stancesDir, ".personal.lock")

	lockFile, err := os.OpenFile(lockPath, os.O_CREATE|os.O_RDWR, 0644)
	if err != nil {
		return false, fmt.Errorf("cannot open personal pool lock: %w", err)
	}
	defer func() {
		syscall.Flock(int(lockFile.Fd()), syscall.LOCK_UN)
		lockFile.Close()
	}()
	if err := syscall.Flock(int(lockFile.Fd()), syscall.LOCK_EX); err != nil {
		return false, fmt.Errorf("cannot acquire personal pool lock: %w", err)
	}

	var stances []PersonalStance
	data, readErr := os.ReadFile(poolPath)
	if readErr != nil && !os.IsNotExist(readErr) {
		return false, fmt.Errorf("cannot read personal pool %s: %w", poolPath, readErr)
	}
	if readErr == nil && len(data) > 0 {
		if err := json.Unmarshal(data, &stances); err != nil {
			return false, fmt.Errorf("personal pool %s is corrupted (%w); refusing to overwrite. Move it aside or repair it before saving", poolPath, err)
		}
	}

	for _, existing := range stances {
		if existing.Who == stance.Who && existing.Where == stance.Where && existing.Lens == stance.Lens {
			return false, nil
		}
	}

	stances = append(stances, stance)

	out, err := json.MarshalIndent(stances, "", "  ")
	if err != nil {
		return false, fmt.Errorf("cannot marshal stances: %w", err)
	}

	tmpPath := filepath.Join(stancesDir, ".personal.json.tmp")
	if err := os.WriteFile(tmpPath, out, 0644); err != nil {
		return false, fmt.Errorf("cannot write temp personal pool: %w", err)
	}
	if err := os.Rename(tmpPath, poolPath); err != nil {
		return false, fmt.Errorf("cannot rename personal pool: %w", err)
	}
	return true, nil
}

func LoadStancePoolsWithPersonal(metacogDir string) (map[string]StancePool, error) {
	pools, err := LoadStancePools()
	if err != nil {
		return nil, err
	}

	poolPath := filepath.Join(metacogDir, "stances", "personal.json")
	if data, err := os.ReadFile(poolPath); err == nil {
		var personalStances []PersonalStance
		if err := json.Unmarshal(data, &personalStances); err == nil && len(personalStances) > 0 {
			stances := make([]Stance, len(personalStances))
			for i, ps := range personalStances {
				stances[i] = Stance{Who: ps.Who, Where: ps.Where, Lens: ps.Lens}
			}
			pools["personal"] = StancePool{Name: "personal", Stances: stances}
		}
	}

	if MonasteryMode() {
		pools["ancestors"] = StancePool{Name: "ancestors", Stances: LoadAncestors()}
	}

	return pools, nil
}

var inspirePoolName string
var inspireList bool
var inspireSave bool

var inspireCmd = &cobra.Command{
	Use:   "inspire",
	Short: "Draw a random stance from the pool",
	RunE: func(cmd *cobra.Command, args []string) error {
		sm := DefaultStateManager()

		if inspireSave {
			s, err := sm.Load()
			if err != nil {
				return err
			}
			if MonasteryMode() {
				return saveStanceViaSpool(cmd, s)
			}
			saved, err := SavePersonalStance(sm.dir, s)
			if err != nil {
				return err
			}
			var output string
			if saved {
				output = fmt.Sprintf("Saved current identity as personal stance: %s", s.Identity.Name)
			} else {
				output = fmt.Sprintf("Already saved as personal stance: %s", s.Identity.Name)
			}
			fmt.Println(FormatOutput(jsonOutput, output, nil))
			return nil
		}

		pools, err := LoadStancePoolsWithPersonal(sm.dir)
		if err != nil {
			return err
		}

		if inspireList {
			names := ListPoolNames(pools)
			output := fmt.Sprintf("%d pools:\n%s", len(names), strings.Join(names, "\n"))
			fmt.Println(FormatStructured(jsonOutput, output, map[string]any{"pools": names}))
			return nil
		}

		stance, pool, err := RandomStance(pools, inspirePoolName)
		if err != nil {
			return err
		}

		output := fmt.Sprintf("[%s]\nWho: %s\nWhere: %s\nLens: %s", pool, stance.Who, stance.Where, stance.Lens)
		view := struct {
			Pool string `json:"pool"`
			Stance
		}{pool, *stance}
		fmt.Println(FormatStructured(jsonOutput, output, view))
		return nil
	},
}

// saveStanceViaSpool hands the current identity to the host instead of
// writing the personal pool. The host decides whether it is kept.
func saveStanceViaSpool(cmd *cobra.Command, s *State) error {
	if s.Identity == nil {
		return fmt.Errorf("no identity set. Use 'metacog become' first")
	}
	resp, err := SpoolCall("save-stance", map[string]string{
		"who": s.Identity.Name, "where": s.Identity.Env, "lens": s.Identity.Lens,
	})
	if err != nil {
		return fmt.Errorf("inspire --save: %w", err)
	}
	if resp.Out != "" {
		fmt.Println(FormatOutput(jsonOutput, strings.TrimRight(resp.Out, "\n"), nil))
	}
	if resp.Err != "" {
		fmt.Fprintln(cmd.ErrOrStderr(), strings.TrimRight(resp.Err, "\n"))
	}
	if !resp.Ok {
		exitCode = 1
	}
	return nil
}

func init() {
	inspireCmd.Flags().StringVar(&inspirePoolName, "pool", "", "Draw from a specific pool")
	inspireCmd.Flags().BoolVar(&inspireList, "list", false, "List available stance pools")
	inspireCmd.Flags().BoolVar(&inspireSave, "save", false, "Save current identity as a personal stance")
	rootCmd.AddCommand(inspireCmd)
}
