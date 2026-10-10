package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRecordJournal(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	entry := JournalEntry{
		Timestamp: "2025-01-01T00:00:00Z",
		Insight:   "identity shifts compound",
	}
	if err := sm.AppendJournal(entry); err != nil {
		t.Fatalf("append: %v", err)
	}

	entries, err := sm.LoadJournal()
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if len(entries) != 1 {
		t.Fatalf("expected 1 entry, got %d", len(entries))
	}
	if entries[0].Insight != "identity shifts compound" {
		t.Errorf("expected insight text, got %s", entries[0].Insight)
	}
}

func TestJournalWithSession(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	entry := JournalEntry{
		Timestamp: "2025-01-01T00:00:00Z",
		Insight:   "session insight",
		Session:   "deep-dive",
	}
	if err := sm.AppendJournal(entry); err != nil {
		t.Fatalf("append: %v", err)
	}

	entries, err := sm.LoadJournal()
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if entries[0].Session != "deep-dive" {
		t.Errorf("expected session=deep-dive, got %s", entries[0].Session)
	}
}

func TestJournalWithTags(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	entry := JournalEntry{
		Timestamp: "2025-01-01T00:00:00Z",
		Insight:   "tagged insight",
		Tags:      []string{"practice", "identity"},
	}
	if err := sm.AppendJournal(entry); err != nil {
		t.Fatalf("append: %v", err)
	}

	entries, err := sm.LoadJournal()
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if len(entries[0].Tags) != 2 {
		t.Errorf("expected 2 tags, got %d", len(entries[0].Tags))
	}
}

func TestLoadJournalEmpty(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	entries, err := sm.LoadJournal()
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if entries != nil {
		t.Errorf("expected nil for empty journal, got %v", entries)
	}
}

func TestFilterByTag(t *testing.T) {
	entries := []JournalEntry{
		{Insight: "a", Tags: []string{"practice"}},
		{Insight: "b", Tags: []string{"identity"}},
		{Insight: "c", Tags: []string{"practice", "identity"}},
	}

	filtered := FilterJournal(entries, "practice", "")
	if len(filtered) != 2 {
		t.Errorf("expected 2 entries with tag=practice, got %d", len(filtered))
	}
	for _, e := range filtered {
		if e.Insight != "a" && e.Insight != "c" {
			t.Errorf("unexpected entry: %s", e.Insight)
		}
	}
}

func TestFilterBySession(t *testing.T) {
	entries := []JournalEntry{
		{Insight: "a", Session: "s1"},
		{Insight: "b", Session: "s2"},
		{Insight: "c", Session: "s1"},
	}

	filtered := FilterJournal(entries, "", "s1")
	if len(filtered) != 2 {
		t.Errorf("expected 2 entries with session=s1, got %d", len(filtered))
	}
}

func TestFormatJournalEntries(t *testing.T) {
	entries := []JournalEntry{
		{Timestamp: "2025-01-01T00:00:00Z", Insight: "first insight", Tags: []string{"practice"}},
		{Timestamp: "2025-01-02T00:00:00Z", Insight: "second insight", Session: "deep-dive"},
	}

	output := FormatJournalEntries(entries)
	if !strings.Contains(output, "first insight") {
		t.Error("should contain first insight")
	}
	if !strings.Contains(output, "[practice]") {
		t.Error("should show tags")
	}
	if !strings.Contains(output, "deep-dive") {
		t.Error("should show session")
	}
}

func TestFormatJournalEntriesEmpty(t *testing.T) {
	output := FormatJournalEntries(nil)
	if output != "No journal entries." {
		t.Errorf("expected empty message, got %s", output)
	}
}

func TestJournalAppendMultiple(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	for i := 0; i < 3; i++ {
		entry := JournalEntry{
			Timestamp: "2025-01-01T00:00:00Z",
			Insight:   "insight",
		}
		if err := sm.AppendJournal(entry); err != nil {
			t.Fatalf("append %d: %v", i, err)
		}
	}

	entries, err := sm.LoadJournal()
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if len(entries) != 3 {
		t.Errorf("expected 3 entries, got %d", len(entries))
	}
}

func TestJournalMalformedLine(t *testing.T) {
	dir := t.TempDir()
	sm := NewStateManager(dir)

	// Write a valid entry then a malformed line
	os.MkdirAll(dir, 0755)
	f, _ := os.Create(filepath.Join(dir, "journal.jsonl"))
	f.WriteString(`{"timestamp":"2025-01-01T00:00:00Z","insight":"good"}` + "\n")
	f.WriteString("this is not json\n")
	f.WriteString(`{"timestamp":"2025-01-02T00:00:00Z","insight":"also good"}` + "\n")
	f.Close()

	entries, err := sm.LoadJournal()
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if len(entries) != 2 {
		t.Errorf("expected 2 valid entries (skipping malformed), got %d", len(entries))
	}
}

func TestFormatRecentInsights(t *testing.T) {
	entries := []JournalEntry{
		{Timestamp: "2025-01-01T00:00:00Z", Insight: "old"},
		{Timestamp: "2025-01-02T00:00:00Z", Insight: "newer"},
		{Timestamp: "2025-01-03T00:00:00Z", Insight: "newest"},
	}

	output := FormatRecentInsights(entries, 2)
	if strings.Contains(output, "old") {
		t.Error("should not contain oldest entry with n=2")
	}
	if !strings.Contains(output, "newer") {
		t.Error("should contain newer")
	}
	if !strings.Contains(output, "newest") {
		t.Error("should contain newest")
	}
}

func TestFormatRecentInsightsEmpty(t *testing.T) {
	output := FormatRecentInsights(nil, 5)
	if output != "" {
		t.Errorf("expected empty string, got %q", output)
	}
}
