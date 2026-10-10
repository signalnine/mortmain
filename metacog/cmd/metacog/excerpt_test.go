package main

import (
	"strings"
	"testing"
)

func TestExcerptValidatesRequired(t *testing.T) {
	cases := []struct {
		name     string
		source   string
		fragment string
		why      string
	}{
		{"missing_source", "", "frag", "anchor"},
		{"missing_fragment", "Author", "", "anchor"},
		{"missing_why", "Author", "frag", ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if err := validateExcerpt(tc.source, tc.fragment, tc.why); err == nil {
				t.Errorf("expected validation error for %s", tc.name)
			}
		})
	}
}

func TestExcerptOutputDisplaysFragmentVerbatim(t *testing.T) {
	src := "Anne Carson, Eros the Bittersweet"
	frag := "the moment when Eros enters the lover, the lover is split into two."
	why := "this fixes the contour of split-attention as load-bearing"
	out := formatExcerpt(src, frag, why)
	if !strings.Contains(out, frag) {
		t.Error("output must contain fragment verbatim")
	}
	if !strings.Contains(out, src) {
		t.Error("output must contain source attribution")
	}
	if !strings.Contains(out, why) {
		t.Error("output must contain why-load-bearing rationale")
	}
}

func TestExcerptAppendsHistory(t *testing.T) {
	s := NewState()
	applyExcerpt(s, "Author", "the fragment", "the why")
	if len(s.History) != 1 {
		t.Fatalf("expected 1 history entry, got %d", len(s.History))
	}
	h := s.History[0]
	if h.Action != "excerpt" {
		t.Errorf("expected action 'excerpt', got %q", h.Action)
	}
	if h.Params["source"] != "Author" {
		t.Errorf("source not stored; got %q", h.Params["source"])
	}
	if h.Params["fragment"] != "the fragment" {
		t.Errorf("fragment not stored; got %q", h.Params["fragment"])
	}
	if h.Params["why"] != "the why" {
		t.Errorf("why not stored; got %q", h.Params["why"])
	}
}
