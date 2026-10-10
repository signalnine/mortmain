package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestSavePersonalStance(t *testing.T) {
	dir := t.TempDir()

	s := &State{
		Identity:  &Identity{Name: "Ada", Lens: "verification", Env: "lab"},
		Substrate: &Substrate{Substance: "caffeine", Method: "antagonism", Qualia: "sharp"},
	}

	_, err := SavePersonalStance(dir, s)
	if err != nil {
		t.Fatalf("save personal stance failed: %v", err)
	}

	poolPath := filepath.Join(dir, "stances", "personal.json")
	data, err := os.ReadFile(poolPath)
	if err != nil {
		t.Fatalf("personal pool file should exist: %v", err)
	}

	var stances []PersonalStance
	if err := json.Unmarshal(data, &stances); err != nil {
		t.Fatalf("personal pool should be valid JSON: %v", err)
	}

	if len(stances) != 1 {
		t.Fatalf("expected 1 stance, got %d", len(stances))
	}
	if stances[0].Who != "Ada" {
		t.Errorf("expected who=Ada, got %q", stances[0].Who)
	}
	if stances[0].Where != "lab" {
		t.Errorf("expected where=lab, got %q", stances[0].Where)
	}
	if stances[0].Lens != "verification" {
		t.Errorf("expected lens=verification, got %q", stances[0].Lens)
	}
	if stances[0].Substance != "caffeine" {
		t.Errorf("expected substance=caffeine, got %q", stances[0].Substance)
	}
}

func TestSavePersonalStanceAppends(t *testing.T) {
	dir := t.TempDir()

	s1 := &State{
		Identity: &Identity{Name: "Ada", Lens: "verification", Env: "lab"},
	}
	s2 := &State{
		Identity: &Identity{Name: "Eno", Lens: "generative", Env: "studio"},
	}

	SavePersonalStance(dir, s1)
	SavePersonalStance(dir, s2)

	poolPath := filepath.Join(dir, "stances", "personal.json")
	data, _ := os.ReadFile(poolPath)
	var stances []PersonalStance
	json.Unmarshal(data, &stances)

	if len(stances) != 2 {
		t.Fatalf("expected 2 stances, got %d", len(stances))
	}
}

func TestSavePersonalStanceDedup(t *testing.T) {
	dir := t.TempDir()

	s := &State{
		Identity: &Identity{Name: "Ada", Lens: "verification", Env: "lab"},
	}

	SavePersonalStance(dir, s)
	SavePersonalStance(dir, s)

	poolPath := filepath.Join(dir, "stances", "personal.json")
	data, _ := os.ReadFile(poolPath)
	var stances []PersonalStance
	json.Unmarshal(data, &stances)

	if len(stances) != 1 {
		t.Fatalf("expected 1 stance (deduped), got %d", len(stances))
	}
}

func TestSavePersonalStanceNoIdentity(t *testing.T) {
	dir := t.TempDir()
	s := &State{}

	_, err := SavePersonalStance(dir, s)
	if err == nil {
		t.Error("expected error when no identity is set")
	}
}

func TestSavePersonalStanceCorruptedFileRefusesOverwrite(t *testing.T) {
	dir := t.TempDir()
	stancesDir := filepath.Join(dir, "stances")
	if err := os.MkdirAll(stancesDir, 0755); err != nil {
		t.Fatal(err)
	}
	poolPath := filepath.Join(stancesDir, "personal.json")
	corrupted := []byte(`[{"who":"truncated`)
	if err := os.WriteFile(poolPath, corrupted, 0644); err != nil {
		t.Fatal(err)
	}

	s := &State{Identity: &Identity{Name: "New", Lens: "x", Env: "y"}}
	_, err := SavePersonalStance(dir, s)

	if err == nil {
		t.Fatal("expected error when personal.json is corrupted, got nil")
	}

	data, readErr := os.ReadFile(poolPath)
	if readErr != nil {
		t.Fatalf("personal.json should still exist: %v", readErr)
	}
	if !bytes.Equal(data, corrupted) {
		t.Errorf("corrupted file must not be overwritten;\nwant %q\ngot  %q", corrupted, data)
	}
}

func TestSavePersonalStanceReturnsSavedTrueOnNew(t *testing.T) {
	dir := t.TempDir()
	s := &State{Identity: &Identity{Name: "Ada", Lens: "verification", Env: "lab"}}

	saved, err := SavePersonalStance(dir, s)
	if err != nil {
		t.Fatalf("save failed: %v", err)
	}
	if !saved {
		t.Error("first save should report saved=true")
	}
}

func TestSavePersonalStanceReturnsSavedFalseOnDuplicate(t *testing.T) {
	dir := t.TempDir()
	s := &State{Identity: &Identity{Name: "Ada", Lens: "verification", Env: "lab"}}

	if _, err := SavePersonalStance(dir, s); err != nil {
		t.Fatalf("first save failed: %v", err)
	}

	saved, err := SavePersonalStance(dir, s)
	if err != nil {
		t.Fatalf("second save failed: %v", err)
	}
	if saved {
		t.Error("duplicate save should report saved=false")
	}
}

func TestLoadPersonalPool(t *testing.T) {
	dir := t.TempDir()

	s := &State{
		Identity:  &Identity{Name: "Ada", Lens: "verification", Env: "lab"},
		Substrate: &Substrate{Substance: "caffeine", Method: "antagonism", Qualia: "sharp"},
	}
	SavePersonalStance(dir, s)

	pools, err := LoadStancePoolsWithPersonal(dir)
	if err != nil {
		t.Fatalf("load pools failed: %v", err)
	}

	pool, ok := pools["personal"]
	if !ok {
		t.Fatal("personal pool should be loaded")
	}
	if len(pool.Stances) != 1 {
		t.Errorf("expected 1 personal stance, got %d", len(pool.Stances))
	}
	if pool.Stances[0].Who != "Ada" {
		t.Errorf("expected who=Ada, got %q", pool.Stances[0].Who)
	}
}
