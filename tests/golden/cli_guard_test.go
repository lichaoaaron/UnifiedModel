package golden_test

import (
	"bytes"
	"os/exec"
	"path/filepath"
	"testing"
)

func TestCLIRejectsDomainReadCommands(t *testing.T) {
	root := filepath.Join("..", "..")
	cases := [][]string{
		{"entity", "get", "demo", "cart"},
		{"entity", "list", "demo"},
		{"entity", "search", "demo", "cart"},
		{"topo", "neighbors", "demo", "cart"},
		{"topo", "subgraph", "demo", "cart"},
		{"topo", "path", "demo", "cart", "checkout"},
		{"mmodel", "get", "demo", "apm.service"},
		{"mmodel", "list", "demo"},
		{"mmodel", "graph", "demo"},
		{"workspace", "start", "demo"},
		{"workspace", "backup", "demo"},
	}
	for _, args := range cases {
		cmdArgs := append([]string{"run", "./cmd/mmctl"}, args...)
		cmd := exec.Command("go", cmdArgs...)
		cmd.Dir = root
		out, err := cmd.CombinedOutput()
		if err == nil {
			t.Fatalf("expected command %v to fail, output=%s", args, out)
		}
		if !bytes.Contains(out, []byte("forbidden")) {
			t.Fatalf("expected forbidden message for %v, got %s", args, out)
		}
	}
}
