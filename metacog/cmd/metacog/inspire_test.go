package main

import (
	"strings"
	"testing"
)

// This build ships no stance pools: nothing named is compiled into the binary.
func TestNoBuiltInStancePools(t *testing.T) {
	pools, err := LoadStancePools()
	if err != nil {
		t.Fatalf("LoadStancePools failed: %v", err)
	}
	if len(pools) != 0 {
		t.Errorf("expected zero built-in pools, got %v", ListPoolNames(pools))
	}
}

func TestListPoolsSorted(t *testing.T) {
	pools := map[string]StancePool{"b": {Name: "b"}, "a": {Name: "a"}, "c": {Name: "c"}}
	names := ListPoolNames(pools)
	if strings.Join(names, ",") != "a,b,c" {
		t.Errorf("pool names not sorted: %v", names)
	}
}

func TestRandomStanceNoPools(t *testing.T) {
	pools, _ := LoadStancePools()
	if _, _, err := RandomStance(pools, ""); err == nil {
		t.Fatal("expected error with no pools")
	}
}

func TestRandomStanceFromNamedPool(t *testing.T) {
	pools := map[string]StancePool{
		"x": {Name: "x", Stances: []Stance{{Who: "w", Where: "h", Lens: "l"}}},
		"y": {Name: "y", Stances: []Stance{{Who: "v", Where: "h", Lens: "l"}}},
	}
	stance, pool, err := RandomStance(pools, "x")
	if err != nil {
		t.Fatalf("RandomStance from pool failed: %v", err)
	}
	if pool != "x" || stance.Who != "w" {
		t.Errorf("got pool %q stance %+v", pool, stance)
	}
}

func TestRandomStanceUnknownPool(t *testing.T) {
	pools, _ := LoadStancePools()
	_, _, err := RandomStance(pools, "nonexistent-pool-xyz")
	if err == nil {
		t.Fatal("expected error for unknown pool, got nil")
	}
}

func TestRandomStanceEmptyNamedPool(t *testing.T) {
	pools := map[string]StancePool{
		"empty": {Name: "empty", Stances: []Stance{}},
	}
	_, _, err := RandomStance(pools, "empty")
	if err == nil {
		t.Fatal("expected error for empty named pool, got nil")
	}
	if !strings.Contains(err.Error(), "no stances") {
		t.Errorf("expected error mentioning 'no stances', got: %v", err)
	}
}

func TestRandomStanceAllPoolsEmpty(t *testing.T) {
	pools := map[string]StancePool{
		"a": {Name: "a", Stances: []Stance{}},
		"b": {Name: "b", Stances: []Stance{}},
	}
	_, _, err := RandomStance(pools, "")
	if err == nil {
		t.Fatal("expected error when all pools empty, got nil")
	}
}

func TestRandomStanceUnnamedSkipsEmptyPools(t *testing.T) {
	pools := map[string]StancePool{
		"empty": {Name: "empty", Stances: []Stance{}},
		"good":  {Name: "good", Stances: []Stance{{Who: "w", Where: "x", Lens: "y"}}},
	}
	for i := 0; i < 50; i++ {
		stance, pool, err := RandomStance(pools, "")
		if err != nil {
			t.Fatalf("RandomStance failed on iteration %d: %v", i, err)
		}
		if pool != "good" {
			t.Errorf("expected pool 'good', got %q", pool)
		}
		if stance == nil || stance.Who != "w" {
			t.Errorf("unexpected stance: %+v", stance)
		}
	}
}
