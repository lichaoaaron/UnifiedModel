package plugin

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/grafana/grafana-plugin-sdk-go/backend"
)

// mockCallResourceResponseSender implements backend.CallResourceResponseSender
// for use in tests.
type mockCallResourceResponseSender struct {
	response *backend.CallResourceResponse
}

// Send sets the received *backend.CallResourceResponse to s.response
func (s *mockCallResourceResponseSender) Send(response *backend.CallResourceResponse) error {
	s.response = response
	return nil
}

func newAppForTest(t *testing.T, settings backend.AppInstanceSettings) *App {
	t.Helper()
	inst, err := NewApp(context.Background(), settings)
	if err != nil {
		t.Fatalf("new app: %s", err)
	}
	app, ok := inst.(*App)
	if !ok {
		t.Fatal("inst must be of type *App")
	}
	return app
}

func callResource(t *testing.T, app *App, method, path string, body []byte) *backend.CallResourceResponse {
	t.Helper()
	var r mockCallResourceResponseSender
	if err := app.CallResource(context.Background(), &backend.CallResourceRequest{
		Method: method,
		Path:   path,
		Body:   body,
	}, &r); err != nil {
		t.Fatalf("CallResource error: %s", err)
	}
	if r.response == nil {
		t.Fatal("no response received from CallResource")
	}
	return r.response
}

// TestPing ensures the resource channel and httpadapter work.
func TestPing(t *testing.T) {
	app := newAppForTest(t, backend.AppInstanceSettings{})
	resp := callResource(t, app, http.MethodGet, "ping", nil)
	if resp.Status != http.StatusOK {
		t.Errorf("ping status = %d, want 200", resp.Status)
	}
}

// TestProxyForwards verifies that /api/* is reverse-proxied to the configured
// upstream with the path preserved and the bearer token injected.
func TestProxyForwards(t *testing.T) {
	var gotPath, gotQuery, gotAuth, gotMethod string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotQuery = r.URL.RawQuery
		gotAuth = r.Header.Get("Authorization")
		gotMethod = r.Method
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	defer upstream.Close()

	app := newAppForTest(t, backend.AppInstanceSettings{
		JSONData:                json.RawMessage(`{"apiUrl":"` + upstream.URL + `"}`),
		DecryptedSecureJSONData: map[string]string{"apiKey": "secret"},
	})

	resp := callResource(t, app, http.MethodGet, "api/v1/workspaces?limit=10", nil)
	if resp.Status != http.StatusOK {
		t.Errorf("status = %d, want 200", resp.Status)
	}
	if gotMethod != http.MethodGet {
		t.Errorf("upstream method = %q, want GET", gotMethod)
	}
	if gotPath != "/api/v1/workspaces" {
		t.Errorf("upstream path = %q, want /api/v1/workspaces", gotPath)
	}
	if gotQuery != "limit=10" {
		t.Errorf("upstream query = %q, want limit=10", gotQuery)
	}
	if gotAuth != "Bearer secret" {
		t.Errorf("upstream auth = %q, want Bearer secret", gotAuth)
	}
}

// TestProxyUnconfigured returns 502 when apiUrl is not set.
func TestProxyUnconfigured(t *testing.T) {
	app := newAppForTest(t, backend.AppInstanceSettings{})
	resp := callResource(t, app, http.MethodGet, "api/v1/workspaces", nil)
	if resp.Status != http.StatusBadGateway {
		t.Errorf("status = %d, want 502", resp.Status)
	}
}