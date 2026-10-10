package main

import (
	"strings"
	"testing"
)

func TestSessionStart(t *testing.T) {
	s := NewState()
	err := StartSession(s, "api-redesign")
	if err != nil {
		t.Fatalf("start session failed: %v", err)
	}
	if s.Session != "api-redesign" {
		t.Errorf("expected session 'api-redesign', got %q", s.Session)
	}
}

func TestSessionEnd(t *testing.T) {
	s := NewState()
	StartSession(s, "api-redesign")
	err := EndSession(s)
	if err != nil {
		t.Fatalf("end session failed: %v", err)
	}
	if s.Session != "" {
		t.Error("session should be cleared")
	}
}

func TestSessionEndNoActive(t *testing.T) {
	s := NewState()
	err := EndSession(s)
	if err == nil {
		t.Error("expected error ending session with none active")
	}
}

func TestSessionStartWhileActive(t *testing.T) {
	s := NewState()
	StartSession(s, "first")
	err := StartSession(s, "second")
	if err == nil {
		t.Error("expected error starting session while one is active")
	}
}

func TestSessionStartEmptyName(t *testing.T) {
	s := NewState()
	err := StartSession(s, "")
	if err == nil {
		t.Error("expected error for empty session name")
	}
	err = StartSession(s, "   ")
	if err == nil {
		t.Error("expected error for whitespace-only session name")
	}
}

func TestSessionTagsHistory(t *testing.T) {
	s := NewState()
	StartSession(s, "test-session")
	s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "Ada"}})

	last := s.History[len(s.History)-1]
	if last.Session != "test-session" {
		t.Errorf("expected session tag 'test-session', got %q", last.Session)
	}
}

func TestHistoryFilterBySession(t *testing.T) {
	s := NewState()
	s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "before"}})

	StartSession(s, "my-session")
	s.AddHistory(HistoryEntry{Action: "become", Params: map[string]string{"name": "Ada"}})
	s.AddHistory(HistoryEntry{Action: "drugs", Params: map[string]string{"substance": "caffeine"}})

	output := FormatHistoryFiltered(s, "my-session")
	if !strings.Contains(output, "Ada") {
		t.Error("filtered history should contain Ada")
	}
	if strings.Contains(output, "before") {
		t.Error("filtered history should not contain 'before' entry")
	}
}

func TestSessionList(t *testing.T) {
	s := NewState()
	s.History = append(s.History, HistoryEntry{Action: "session", Params: map[string]string{"name": "alpha", "event": "started"}})
	s.History = append(s.History, HistoryEntry{Action: "become", Session: "alpha", Params: map[string]string{"name": "Ada"}})
	s.History = append(s.History, HistoryEntry{Action: "session", Params: map[string]string{"name": "alpha", "event": "ended"}})
	s.History = append(s.History, HistoryEntry{Action: "session", Params: map[string]string{"name": "beta", "event": "started"}})
	s.History = append(s.History, HistoryEntry{Action: "become", Session: "beta", Params: map[string]string{"name": "Eno"}})

	names := ListSessions(s)
	if len(names) != 2 {
		t.Errorf("expected 2 sessions, got %d", len(names))
	}
}
