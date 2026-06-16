package service

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestQuickstartClientUsesPublicRESTContracts(t *testing.T) {
	var seen []string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seen = append(seen, r.Method+" "+r.URL.Path)
		w.Header().Set("content-type", "application/json")

		switch r.URL.Path {
		case "/api/v1/workspaces":
			assertBodyField(t, r, "id", "demo")
			_, _ = w.Write([]byte(`{"id":"demo","name":"Demo","status":"active","resource_version":1}`))
		case "/api/v1/mmodel/demo/elements":
			assertArrayBody(t, r, "elements")
			_, _ = w.Write([]byte(`{"accepted":1,"failed":0}`))
		case "/api/v1/mmodel/demo/validate":
			assertArrayBody(t, r, "elements")
			_, _ = w.Write([]byte(`{"valid":true}`))
		case "/api/v1/mmodel/demo/import":
			assertBodyField(t, r, "path", "/tmp/mmodel")
			_, _ = w.Write([]byte(`{"workspace":"demo","source":"/tmp/mmodel","imported":1,"skipped":0}`))
		case "/api/v1/entitystore/demo/entities:write":
			assertArrayBody(t, r, "entities")
			_, _ = w.Write([]byte(`{"accepted":1,"failed":0}`))
		case "/api/v1/entitystore/demo/entities:expire":
			assertArrayBody(t, r, "ids")
			_, _ = w.Write([]byte(`{"accepted":1,"failed":0}`))
		case "/api/v1/entitystore/demo/relations:write":
			assertArrayBody(t, r, "relations")
			_, _ = w.Write([]byte(`{"accepted":1,"failed":0}`))
		case "/api/v1/entitystore/demo/relations:expire":
			assertArrayBody(t, r, "ids")
			_, _ = w.Write([]byte(`{"accepted":1,"failed":0}`))
		case "/api/v1/query/demo/execute":
			assertBodyField(t, r, "query", ".mmodel | limit 1")
			_, _ = w.Write([]byte(`{"columns":["id"],"rows":[{"id":"apm.service"}],"page":{"limit":1}}`))
		case "/api/v1/query/demo/explain":
			assertBodyField(t, r, "query", ".mmodel | limit 1")
			_, _ = w.Write([]byte(`{"source":".mmodel","provider":"memory","storage_provider":"memory","time_range_applied":false}`))
		case "/api/v1/agent/demo/discover":
			_, _ = w.Write([]byte(`{"workspace":"demo","tools":[{"name":"query_spl_execute","description":"Execute","enabled":true}],"resources":[{"uri":"mmodel://workspace/demo/query-templates","name":"Query templates","kind":"templates","description":"Safe query templates","mime_type":"application/json","read_only":true}],"next_actions":[{"id":"list_mmodel","title":"List MModel","description":"List MModel elements","tool":"query_spl_execute","query_api":{"method":"POST","path":"/api/v1/query/demo/execute","body":{"query":".mmodel | limit 20"}}}]}`))
		default:
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
	}))
	defer server.Close()

	client := NewClient(server.URL)
	ctx := context.Background()
	workspace, err := client.CreateWorkspace(ctx, CreateWorkspaceRequest{ID: "demo", Name: "Demo"})
	if err != nil {
		t.Fatalf("create workspace: %v", err)
	}
	if workspace.ID != "demo" {
		t.Fatalf("unexpected workspace: %+v", workspace)
	}

	elements := []MModelElement{{Kind: "entity_set", Domain: "apm", Name: "apm.service"}}
	if _, err := client.PutMModelElements(ctx, "demo", elements); err != nil {
		t.Fatalf("put mmodel: %v", err)
	}
	if validation, err := client.ValidateMModel(ctx, "demo", elements); err != nil || !validation.Valid {
		t.Fatalf("validate mmodel: %+v %v", validation, err)
	}
	if imported, err := client.ImportMModel(ctx, "demo", MModelImportRequest{Path: "/tmp/mmodel"}); err != nil || imported.Imported != 1 {
		t.Fatalf("import mmodel: %+v %v", imported, err)
	}
	if _, err := client.WriteEntities(ctx, "demo", []map[string]any{{"__entity_id__": "54013ba69c196820e56801f1ef5aad54"}}); err != nil {
		t.Fatalf("write entities: %v", err)
	}
	if _, err := client.ExpireEntities(ctx, "demo", []string{"cart"}, "quickstart cleanup"); err != nil {
		t.Fatalf("expire entities: %v", err)
	}
	if _, err := client.WriteRelations(ctx, "demo", []map[string]any{{"__relation_type__": "calls"}}); err != nil {
		t.Fatalf("write relations: %v", err)
	}
	if _, err := client.ExpireRelations(ctx, "demo", []string{"cart/calls/checkout"}, "quickstart cleanup"); err != nil {
		t.Fatalf("expire relations: %v", err)
	}
	result, err := client.Query(ctx, "demo", QueryRequest{Query: ".mmodel | limit 1"})
	if err != nil {
		t.Fatalf("query: %v", err)
	}
	if len(result.Rows) != 1 {
		t.Fatalf("unexpected query result: %+v", result)
	}
	explain, err := client.Explain(ctx, "demo", QueryRequest{Query: ".mmodel | limit 1"})
	if err != nil {
		t.Fatalf("explain: %v", err)
	}
	if explain.Provider != "memory" || explain.StorageProvider != "memory" {
		t.Fatalf("unexpected explain: %+v", explain)
	}
	discovery, err := client.Discover(ctx, "demo")
	if err != nil {
		t.Fatalf("discover: %v", err)
	}
	if len(discovery.Tools) != 1 || len(discovery.Resources) != 1 || len(discovery.NextActions) != 1 {
		t.Fatalf("unexpected discovery: %+v", discovery)
	}

	if len(seen) != 11 {
		t.Fatalf("unexpected request count: %v", seen)
	}
}

func assertBodyField(t *testing.T, r *http.Request, key, want string) {
	t.Helper()
	var body map[string]any
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		t.Fatalf("decode body: %v", err)
	}
	if body[key] != want {
		t.Fatalf("unexpected %s: %+v", key, body)
	}
}

func assertArrayBody(t *testing.T, r *http.Request, key string) {
	t.Helper()
	var body map[string]any
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		t.Fatalf("decode body: %v", err)
	}
	values, ok := body[key].([]any)
	if !ok || len(values) != 1 {
		t.Fatalf("expected one %s value, got %+v", key, body)
	}
}
