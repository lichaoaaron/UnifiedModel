package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestRunDevExCommandsRouteToPublicContracts(t *testing.T) {
	tests := []struct {
		name   string
		args   []string
		method string
		path   string
		check  func(t *testing.T, body map[string]any)
	}{
		{
			name:   "workspace update",
			args:   []string{"workspace", "update", "demo", `{"name":"Demo"}`},
			method: http.MethodPut,
			path:   "/api/v1/workspaces/demo",
			check: func(t *testing.T, body map[string]any) {
				t.Helper()
				if body["name"] != "Demo" {
					t.Fatalf("unexpected workspace update body: %+v", body)
				}
			},
		},
		{
			name:   "mmodel put wraps single element",
			args:   []string{"mmodel", "put", "demo", `{"kind":"entity_set","domain":"devops","name":"devops.service"}`},
			method: http.MethodPost,
			path:   "/api/v1/mmodel/demo/elements",
			check:  assertArrayField("elements", "name", "devops.service"),
		},
		{
			name:   "mmodel import routes to import contract",
			args:   []string{"mmodel", "import", "demo", "/tmp/mmodel"},
			method: http.MethodPost,
			path:   "/api/v1/mmodel/demo/import",
			check: func(t *testing.T, body map[string]any) {
				t.Helper()
				if body["path"] != "/tmp/mmodel" {
					t.Fatalf("unexpected import body: %+v", body)
				}
			},
		},
		{
			name:   "mmodel delete sends ids",
			args:   []string{"mmodel", "delete", "demo", "devops.service"},
			method: http.MethodDelete,
			path:   "/api/v1/mmodel/demo/elements",
			check:  assertIDs("devops.service"),
		},
		{
			name:   "entity write wraps single record",
			args:   []string{"entity", "write", "demo", `{"__entity_id__": "54013ba69c196820e56801f1ef5aad54"}`},
			method: http.MethodPost,
			path:   "/api/v1/entitystore/demo/entities:write",
			check:  assertArrayField("entities", "__entity_id__", "54013ba69c196820e56801f1ef5aad54"),
		},
		{
			name:   "entity expire sends ids",
			args:   []string{"entity", "expire", "demo", "devops/devops.service/10000000000000000000000000000101,devops/devops.service/10000000000000000000000000000102"},
			method: http.MethodPost,
			path:   "/api/v1/entitystore/demo/entities:expire",
			check:  assertIDs("devops/devops.service/10000000000000000000000000000101", "devops/devops.service/10000000000000000000000000000102"),
		},
		{
			name:   "topo write wraps single relation",
			args:   []string{"topo", "write", "demo", `{"__relation_type__":"calls"}`},
			method: http.MethodPost,
			path:   "/api/v1/entitystore/demo/relations:write",
			check:  assertArrayField("relations", "__relation_type__", "calls"),
		},
		{
			name:   "topo delete uses expire route",
			args:   []string{"topo", "delete", "demo", "devops/devops.service/10000000000000000000000000000101/calls/devops/devops.service/10000000000000000000000000000102"},
			method: http.MethodPost,
			path:   "/api/v1/entitystore/demo/relations:expire",
			check: func(t *testing.T, body map[string]any) {
				t.Helper()
				assertIDs("devops/devops.service/10000000000000000000000000000101/calls/devops/devops.service/10000000000000000000000000000102")(t, body)
				if reason, _ := body["reason"].(string); !strings.Contains(reason, "delete") {
					t.Fatalf("expected delete reason, got %+v", body)
				}
			},
		},
		{
			name:   "query explain",
			args:   []string{"query", "explain", "demo", ".mmodel", "|", "limit", "1"},
			method: http.MethodPost,
			path:   "/api/v1/query/demo/explain",
			check: func(t *testing.T, body map[string]any) {
				t.Helper()
				if body["query"] != ".mmodel | limit 1" {
					t.Fatalf("unexpected query body: %+v", body)
				}
			},
		},
		{
			name:   "agent discover",
			args:   []string{"agent", "discover", "demo"},
			method: http.MethodGet,
			path:   "/api/v1/agent/demo/discover",
		},
		{
			name:   "agent tool execute",
			args:   []string{"agent", "tool", "demo", "query_spl_execute", `{"query":".mmodel | limit 1"}`},
			method: http.MethodPost,
			path:   "/api/v1/agent/demo/tools:execute",
			check: func(t *testing.T, body map[string]any) {
				t.Helper()
				if body["name"] != "query_spl_execute" {
					t.Fatalf("unexpected tool body: %+v", body)
				}
				args, ok := body["arguments"].(map[string]any)
				if !ok || args["query"] != ".mmodel | limit 1" {
					t.Fatalf("unexpected tool arguments: %+v", body)
				}
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Method != tt.method || r.URL.Path != tt.path {
					t.Fatalf("unexpected request %s %s", r.Method, r.URL.Path)
				}
				var body map[string]any
				if r.Body != nil && r.ContentLength != 0 {
					if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
						t.Fatalf("decode request body: %v", err)
					}
				}
				if tt.check != nil {
					tt.check(t, body)
				}
				w.Header().Set("content-type", "application/json")
				_, _ = w.Write([]byte(`{"ok":true}`))
			}))
			defer server.Close()

			var out, errOut bytes.Buffer
			args := append([]string{"--addr", server.URL}, tt.args...)
			if err := run(args, &out, &errOut); err != nil {
				t.Fatalf("run failed: %v\nstderr=%s", err, errOut.String())
			}
			if !strings.Contains(out.String(), `"ok":true`) {
				t.Fatalf("unexpected output: %s", out.String())
			}
		})
	}
}

func TestRunRejectsBadArgsInvalidJSONAndServerErrors(t *testing.T) {
	cases := []struct {
		name string
		args []string
		want string
	}{
		{
			name: "missing query spl",
			args: []string{"query", "run", "demo"},
			want: "usage: query run",
		},
		{
			name: "invalid inline json",
			args: []string{"mmodel", "put", "demo", "{"},
			want: "unexpected end of JSON input",
		},
		{
			name: "invalid ids json",
			args: []string{"entity", "expire", "demo", `["cart", 1]`},
			want: "cannot unmarshal number",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			var out, errOut bytes.Buffer
			err := run(tc.args, &out, &errOut)
			if err == nil {
				t.Fatalf("expected command to fail, stdout=%s stderr=%s", out.String(), errOut.String())
			}
			if !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("expected error to contain %q, got %v", tc.want, err)
			}
		})
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, `{"error":{"code":"INTERNAL","message":"boom"}}`, http.StatusInternalServerError)
	}))
	defer server.Close()

	var out, errOut bytes.Buffer
	err := run([]string{"--addr", server.URL, "query", "run", "demo", ".mmodel", "|", "limit", "1"}, &out, &errOut)
	if err == nil {
		t.Fatalf("expected server error, stdout=%s stderr=%s", out.String(), errOut.String())
	}
	if !strings.Contains(err.Error(), "server returned 500 Internal Server Error") || !strings.Contains(err.Error(), "boom") {
		t.Fatalf("expected HTTP error context, got %v", err)
	}
}

func assertArrayField(field, key, want string) func(t *testing.T, body map[string]any) {
	return func(t *testing.T, body map[string]any) {
		t.Helper()
		values, ok := body[field].([]any)
		if !ok || len(values) != 1 {
			t.Fatalf("expected one %s item, got %+v", field, body)
		}
		item, ok := values[0].(map[string]any)
		if !ok || item[key] != want {
			t.Fatalf("unexpected %s item: %+v", field, values[0])
		}
	}
}

func assertIDs(want ...string) func(t *testing.T, body map[string]any) {
	return func(t *testing.T, body map[string]any) {
		t.Helper()
		raw, ok := body["ids"].([]any)
		if !ok {
			t.Fatalf("expected ids array, got %+v", body)
		}
		got := make([]string, 0, len(raw))
		for _, value := range raw {
			got = append(got, value.(string))
		}
		if strings.Join(got, ",") != strings.Join(want, ",") {
			t.Fatalf("unexpected ids: got %v want %v", got, want)
		}
	}
}
