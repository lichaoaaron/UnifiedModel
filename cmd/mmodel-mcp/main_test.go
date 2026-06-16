package main

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/alibaba/MModel/internal/bootstrap"
	"github.com/alibaba/MModel/internal/graphstore"
)

func TestRunQuickStartPreloadsMCPWorkspace(t *testing.T) {
	input := strings.NewReader(`{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"query_spl_execute","arguments":{"query":".entity with(domain='devops', name='devops.service', query='checkout') | limit 1"}}}`)
	var out bytes.Buffer
	var errOut bytes.Buffer

	err := run([]string{"--quickstart"}, input, &out, &errOut)
	if err != nil {
		t.Fatalf("run quickstart MCP: %v\nstderr:\n%s", err, errOut.String())
	}
	if !strings.Contains(errOut.String(), "quickstart loaded workspace=demo sample=multi-domain-quickstart") {
		t.Fatalf("expected quickstart preload log, got %s", errOut.String())
	}
	if !strings.Contains(out.String(), `"isError":false`) || !strings.Contains(out.String(), "checkout") {
		t.Fatalf("expected query tool to read quickstart sample data, got %s", out.String())
	}
}

func TestEncodeTOONCoversObjectsAndTables(t *testing.T) {
	got := encodeTOON(map[string]any{
		"workspace": "demo",
		"rows": []map[string]any{
			{"id": 1, "name": "checkout"},
			{"id": 2, "name": "payment"},
		},
		"tags": []string{"mmodel", "mcp"},
	})
	for _, want := range []string{"workspace: demo", "rows[2]{id,name}:", "1,checkout", "tags[2]: mmodel,mcp"} {
		if !strings.Contains(got, want) {
			t.Fatalf("TOON output missing %q:\n%s", want, got)
		}
	}
}

func TestMCPProtocolShapesUseTOONContent(t *testing.T) {
	app, err := bootstrap.NewAppWithGraphStore(t.TempDir(), graphstore.ProviderConfig{Type: "memory"})
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()

	for _, payload := range []string{
		`{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","workspace":"demo"}}`,
		`{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{"workspace":"demo"}}`,
		`{"jsonrpc":"2.0","id":3,"method":"resources/templates/list","params":{"workspace":"demo"}}`,
		`{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"workspace":"demo","name":"query_spl_examples","arguments":{}}}`,
		`{"jsonrpc":"2.0","id":5,"method":"resources/read","params":{"workspace":"demo","uri":"mmodel://workspace/demo/overview"}}`,
		`{"jsonrpc":"2.0","id":6,"method":"prompts/list","params":{}}`,
		`{"jsonrpc":"2.0","id":7,"method":"completion/complete","params":{"ref":{"type":"ref/resource","uri":"mmodel://workspace/{workspace}/overview"},"argument":{"name":"uri","value":"query"}}}`,
	} {
		resp, ok := handleRawRPC(ctx, app, "demo", []byte(payload))
		if !ok {
			t.Fatalf("expected response for %s", payload)
		}
		if resp.Error != nil {
			t.Fatalf("unexpected error for %s: %+v", payload, resp.Error)
		}
		body, _ := json.Marshal(resp.Result)
		if resp.ID == float64(4) || resp.ID == float64(5) {
			if !strings.Contains(string(body), toonMimeType) {
				t.Fatalf("expected TOON metadata for %s, got %s", payload, body)
			}
		}
	}
}

func TestStreamableHTTPBatchSkipsNotifications(t *testing.T) {
	app, err := bootstrap.NewAppWithGraphStore(t.TempDir(), graphstore.ProviderConfig{Type: "memory"})
	if err != nil {
		t.Fatal(err)
	}
	responses, err := handleHTTPPayload(context.Background(), app, "demo", []byte(`[
		{"jsonrpc":"2.0","method":"notifications/initialized"},
		{"jsonrpc":"2.0","id":1,"method":"ping"}
	]`))
	if err != nil {
		t.Fatal(err)
	}
	if len(responses) != 1 || responses[0].ID != float64(1) || responses[0].Error != nil {
		t.Fatalf("unexpected batch responses: %+v", responses)
	}
}

func TestStreamableHTTPPostEndpoint(t *testing.T) {
	app, err := bootstrap.NewAppWithGraphStore(t.TempDir(), graphstore.ProviderConfig{Type: "memory"})
	if err != nil {
		t.Fatal(err)
	}
	req := httptest.NewRequest(http.MethodPost, "http://127.0.0.1/mcp", strings.NewReader(`{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","workspace":"demo"}}`))
	req.Header.Set("Origin", "http://127.0.0.1")
	req.Header.Set("MCP-Protocol-Version", "2025-06-18")
	rec := httptest.NewRecorder()

	streamableHTTPHandler(context.Background(), app, "demo").ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("unexpected status %d: %s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), `"protocolVersion":"2025-06-18"`) {
		t.Fatalf("unexpected response: %s", rec.Body.String())
	}

	req = httptest.NewRequest(http.MethodPost, "http://127.0.0.1/mcp", strings.NewReader(`{"jsonrpc":"2.0","id":2,"method":"ping"}`))
	req.Header.Set("MCP-Protocol-Version", "1900-01-01")
	rec = httptest.NewRecorder()
	streamableHTTPHandler(context.Background(), app, "demo").ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected invalid protocol header to fail, got %d", rec.Code)
	}
}
