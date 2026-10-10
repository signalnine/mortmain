package main

import (
	"encoding/json"
	"testing"
)

func TestJSONSuccess(t *testing.T) {
	output := FormatOutput(true, "test output", nil)
	var parsed map[string]any
	if err := json.Unmarshal([]byte(output), &parsed); err != nil {
		t.Fatalf("not valid JSON: %v", err)
	}
	if parsed["output"] != "test output" {
		t.Errorf("expected 'test output', got %v", parsed["output"])
	}
}

func TestJSONError(t *testing.T) {
	output := FormatOutput(true, "", &OutputError{Message: "bad", Code: 1, Suggestion: "fix it"})
	var parsed map[string]any
	if err := json.Unmarshal([]byte(output), &parsed); err != nil {
		t.Fatalf("not valid JSON: %v", err)
	}
	if parsed["error"] != "bad" {
		t.Errorf("expected 'bad', got %v", parsed["error"])
	}
}

func TestPlainOutput(t *testing.T) {
	output := FormatOutput(false, "test output", nil)
	if output != "test output" {
		t.Errorf("expected plain output, got %q", output)
	}
}

func TestFormatStructured(t *testing.T) {
	v := map[string]int{"a": 1}
	if got := FormatStructured(false, "text", v); got != "text" {
		t.Errorf("plain mode should return text, got %q", got)
	}
	if got := FormatStructured(true, "text", v); got != `{"a":1}` {
		t.Errorf("json mode should marshal v, got %q", got)
	}
}
