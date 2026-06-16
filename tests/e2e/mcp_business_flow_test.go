package e2e_test

import (
	"bytes"
	"encoding/json"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestMCPBusinessFlowCoversDiscoveryResourcesAndToolPolicy(t *testing.T) {
	root := filepath.Join("..", "..")
	requests := []string{
		`{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"workspace":"mcp-demo"}}`,
		`{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{"workspace":"mcp-demo"}}`,
		`{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"workspace":"mcp-demo","name":"query_spl_examples","arguments":{}}}`,
		`{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"workspace":"mcp-demo","name":"query_spl_execute","arguments":{"query":".mmodel | limit 1"}}}`,
		`{"jsonrpc":"2.0","id":5,"method":"resources/list","params":{"workspace":"mcp-demo"}}`,
		`{"jsonrpc":"2.0","id":6,"method":"resources/read","params":{"workspace":"mcp-demo","uri":"mmodel://workspace/mcp-demo/overview"}}`,
		`{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"workspace":"mcp-demo","name":"entity_write","arguments":{"entities":[]}}}`,
	}
	cmd := exec.Command("go", "run", "./cmd/mmodel-mcp", "--data", t.TempDir(), "--graphstore", "memory")
	cmd.Dir = root
	cmd.Stdin = strings.NewReader(strings.Join(requests, "\n"))
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("mmodel-mcp failed: %v\n%s", err, out)
	}

	responses := decodeMCPResponses(t, out)
	if len(responses) != len(requests) {
		t.Fatalf("expected %d responses, got %d: %s", len(requests), len(responses), out)
	}
	for _, id := range []float64{1, 2, 3, 4, 5, 6} {
		response := responseByID(t, responses, id)
		if response["error"] != nil {
			t.Fatalf("expected MCP request %.0f to succeed, got %+v", id, response)
		}
	}

	initialize := responseByID(t, responses, 1)
	if !bytes.Contains(mustJSON(t, initialize["result"]), []byte("query_spl_execute")) {
		t.Fatalf("initialize should expose discovery metadata, got %+v", initialize)
	}
	toolsList := responseByID(t, responses, 2)
	if !bytes.Contains(mustJSON(t, toolsList["result"]), []byte("requiresExplicitWriteEnable")) {
		t.Fatalf("tools/list should expose write enablement metadata, got %+v", toolsList)
	}
	examples := responseByID(t, responses, 3)
	if !bytes.Contains(mustJSON(t, examples["result"]), []byte(".entity")) || !bytes.Contains(mustJSON(t, examples["result"]), []byte("text/toon")) {
		t.Fatalf("query_spl_examples should include entity examples, got %+v", examples)
	}
	queryResult := responseByID(t, responses, 4)
	if !bytes.Contains(mustJSON(t, queryResult["result"]), []byte(`"structuredContent"`)) || !bytes.Contains(mustJSON(t, queryResult["result"]), []byte("rows[0]")) {
		t.Fatalf("empty query result should still be a QueryResult, got %+v", queryResult)
	}
	resources := responseByID(t, responses, 5)
	if !bytes.Contains(mustJSON(t, resources["result"]), []byte("query-templates")) {
		t.Fatalf("resources/list should expose query templates, got %+v", resources)
	}
	overview := responseByID(t, responses, 6)
	overviewBody := mustJSON(t, overview["result"])
	if !bytes.Contains(overviewBody, []byte("/api/v1/query/mcp-demo/execute")) || bytes.Contains(overviewBody, []byte(`"rows"`)) {
		t.Fatalf("resource read should expose query entry points without runtime rows, got %s", overviewBody)
	}
	disabled := responseByID(t, responses, 7)
	disabledBody := mustJSON(t, disabled["result"])
	if disabled["error"] != nil || !bytes.Contains(disabledBody, []byte(`"isError":true`)) || !bytes.Contains(disabledBody, []byte("TOOL_DISABLED")) {
		t.Fatalf("entity_write should be disabled through MCP by default, got %+v", disabled)
	}
}

func decodeMCPResponses(t *testing.T, out []byte) []map[string]any {
	t.Helper()
	lines := bytes.Split(bytes.TrimSpace(out), []byte("\n"))
	responses := make([]map[string]any, 0, len(lines))
	for _, line := range lines {
		if len(bytes.TrimSpace(line)) == 0 {
			continue
		}
		var response map[string]any
		if err := json.Unmarshal(line, &response); err != nil {
			t.Fatalf("decode MCP response %s: %v", line, err)
		}
		responses = append(responses, response)
	}
	return responses
}

func responseByID(t *testing.T, responses []map[string]any, id float64) map[string]any {
	t.Helper()
	for _, response := range responses {
		if response["id"] == id {
			return response
		}
	}
	t.Fatalf("missing response id %.0f in %+v", id, responses)
	return nil
}

func mustJSON(t *testing.T, value any) []byte {
	t.Helper()
	body, err := json.Marshal(value)
	if err != nil {
		t.Fatalf("marshal value: %v", err)
	}
	return body
}
