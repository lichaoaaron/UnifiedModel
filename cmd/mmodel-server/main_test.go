package main

import (
	"testing"

	"github.com/alibaba/MModel/internal/graphstore"
)

func TestResolveProviderForQuickStartDefaultsToMemory(t *testing.T) {
	got := resolveProviderForQuickStart(graphstore.DefaultProviderType, true, false)
	if got != graphstore.ProviderTypeMemory {
		t.Fatalf("quickstart should default to memory graphstore, got %q", got)
	}
}

func TestResolveProviderForQuickStartHonorsExplicitGraphStore(t *testing.T) {
	got := resolveProviderForQuickStart(graphstore.ProviderTypeFileMemory, true, true)
	if got != graphstore.ProviderTypeFileMemory {
		t.Fatalf("explicit graphstore should be honored, got %q", got)
	}
}
