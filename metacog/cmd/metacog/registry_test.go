package main

import (
	"strings"
	"testing"
)

// Commands on rootCmd that are not primitives.
var nonPrimitiveCommands = map[string]bool{
	"status": true, "reset": true, "history": true, "repair": true, "stratagem": true,
	"outcome": true, "reflect": true, "inspire": true, "journal": true, "session": true,
	"version": true, "completion": true, "help": true,
}

func TestPrimitiveKindsMatchesRegisteredCommands(t *testing.T) {
	registered := map[string]bool{}
	for _, c := range rootCmd.Commands() {
		registered[c.Name()] = true
	}
	for _, k := range PrimitiveKinds {
		if !registered[string(k)] {
			t.Errorf("PrimitiveKinds lists %q but no such command is registered", k)
		}
	}
	for name := range registered {
		if nonPrimitiveCommands[name] {
			continue
		}
		if !IsPrimitive(name) {
			t.Errorf("command %q is registered but missing from PrimitiveKinds", name)
		}
	}
	if IsPrimitive("THINK") || IsPrimitive("stratagem") {
		t.Error("IsPrimitive must reject non-primitive kinds")
	}
}

func TestVersionListsEveryPrimitiveAndNoStratagems(t *testing.T) {
	out := formatVersion()
	if !strings.HasPrefix(out, "metacog 6.12.0-mortmain\n") {
		t.Errorf("version line: %q", out)
	}
	for _, k := range PrimitiveKinds {
		if !strings.Contains(out, " "+string(k)) {
			t.Errorf("version output missing primitive %q", k)
		}
	}
	if strings.Contains(out, "stratagems") {
		t.Errorf("version output must not list stratagems:\n%s", out)
	}
}

func TestFindLastPrimitiveUsesRegistry(t *testing.T) {
	s := NewState()
	for _, k := range PrimitiveKinds {
		s.History = []HistoryEntry{{Action: string(k), Params: map[string]string{}}}
		if findLastPrimitive(s) != 0 {
			t.Errorf("findLastPrimitive should recognise %q", k)
		}
	}
}

func TestPrimitiveDescriptorsCoverRegistry(t *testing.T) {
	if len(primitiveDescriptors) != len(PrimitiveKinds) {
		t.Errorf("primitiveDescriptors has %d entries, PrimitiveKinds has %d", len(primitiveDescriptors), len(PrimitiveKinds))
	}
	for _, k := range PrimitiveKinds {
		if primitiveDescriptors[string(k)] == "" {
			t.Errorf("no descriptor for %s", k)
		}
	}
	for name := range primitiveDescriptors {
		if !IsPrimitive(name) {
			t.Errorf("descriptor for non-primitive %q", name)
		}
	}
}
