package query

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/alibaba/MModel/internal/graphstore"
	"github.com/alibaba/MModel/internal/telemetry"
	"github.com/alibaba/MModel/internal/telemetry/opensearch"
	"github.com/alibaba/MModel/pkg/model"
)

func opensearchBackedModelElements(endpoint string) []model.MModelElement {
	elements := platformModelElements()
	for i := range elements {
		if elements[i].Kind == "external_storage" && elements[i].Name == "platform.local_snapshot" {
			elements[i].Spec = map[string]any{
				"type": "opensearch",
				"name": "platform.local_snapshot",
				"properties": map[string]any{
					"endpoint":                  endpoint,
					"username":                  "admin",
					"password":                  "secret",
					"log_index":                 "otel-logs-*",
					"metric_index":              "otel-metrics-*",
					"trace_index":               "otel-traces-*",
					"time_field_log":            "time",
					"time_field_metric":         "time",
					"time_field_trace":          "startTime",
					"service_name_field_log":    "serviceName",
					"service_name_field_metric": "serviceName",
					"service_name_field_trace":  "serviceName",
					"request_timeout_ms":        "2000",
				},
			}
		}
	}
	return elements
}

func newOpenSearchEvidenceService(t *testing.T, endpoint string) *Service {
	t.Helper()
	ctx := context.Background()
	store := graphstore.NewMemoryStore()
	if _, err := store.PutMModelElements(ctx, model.MModelElementBatch{
		Workspace: "test",
		Elements:  opensearchBackedModelElements(endpoint),
	}); err != nil {
		t.Fatalf("put mmodel: %v", err)
	}
	if _, err := store.WriteEntities(ctx, model.EntityWriteBatch{
		Workspace: "test",
		Entities: []model.EntityPayload{{
			"__domain__":              "platform",
			"__entity_type__":         "platform.service",
			"__entity_id__":           "aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001",
			"__method__":              "Update",
			"__first_observed_time__": int64(1748912400),
			"__last_observed_time__":  int64(4102444800),
			"id":                      "aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001",
			"display_name":            "iam-manage",
		}},
	}); err != nil {
		t.Fatalf("write entities: %v", err)
	}
	providers := []telemetry.Provider{opensearch.New()}
	return NewServiceWithProviders(store, providers)
}

func TestEvidenceExplainContainsOpenSearchProviderInfo(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"hits":{"hits":[{"_source":{"serviceName":"iam-manage","time":"2026-06-03T01:00:10Z","severityText":"INFO","body":"ok"}}]}}`))
	}))
	defer srv.Close()

	svc := newOpenSearchEvidenceService(t, srv.URL)
	result, err := svc.Execute(context.Background(), "test", model.QueryRequest{
		Query: ".entity with(domain='platform', name='platform.service', ids=('aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001')) | evidence(kind='log_set', from='2026-06-03T01:00:00Z', to='2026-06-03T01:02:00Z') | limit 5",
	})
	if err != nil {
		t.Fatalf("execute: %v", err)
	}
	if result.Explain == nil || result.Explain.Evidence == nil {
		t.Fatal("expected evidence explain")
	}
	ev := result.Explain.Evidence
	if ev.StorageType != "opensearch" || ev.Provider != "opensearch" {
		t.Fatalf("unexpected provider info: storage_type=%s provider=%s", ev.StorageType, ev.Provider)
	}
	if ev.IndexName != "otel-logs-*" {
		t.Fatalf("unexpected index name: %s", ev.IndexName)
	}
	if ev.ServiceField != "serviceName" {
		t.Fatalf("unexpected service field: %s", ev.ServiceField)
	}
	if ev.TimeField != "time" {
		t.Fatalf("unexpected time field: %s", ev.TimeField)
	}
	if ev.Endpoint == "" {
		t.Fatal("endpoint must be populated")
	}
	if ev.ReturnedRows != 1 {
		t.Fatalf("unexpected returned rows: %d", ev.ReturnedRows)
	}
}

func TestExplainAPIContainsOpenSearchProviderInfo(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"hits":{"hits":[]}}`))
	}))
	defer srv.Close()

	svc := newOpenSearchEvidenceService(t, srv.URL)
	explain, err := svc.Explain(context.Background(), "test", model.QueryRequest{
		Query: ".entity with(domain='platform', name='platform.service', ids=('aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001')) | evidence(kind='trace_set') | limit 5",
	})
	if err != nil {
		t.Fatalf("explain: %v", err)
	}
	if explain.Evidence == nil {
		t.Fatal("expected evidence section in explain")
	}
	ev := explain.Evidence
	if ev.StorageType != "opensearch" || ev.Provider != "opensearch" {
		t.Fatalf("unexpected provider info: storage_type=%s provider=%s", ev.StorageType, ev.Provider)
	}
	if ev.IndexName != "otel-traces-*" {
		t.Fatalf("unexpected trace index: %s", ev.IndexName)
	}
	if ev.ServiceField != "serviceName" {
		t.Fatalf("unexpected service field: %s", ev.ServiceField)
	}
	if ev.TimeField != "startTime" {
		t.Fatalf("unexpected time field: %s", ev.TimeField)
	}
	if ev.Endpoint == "" {
		t.Fatal("endpoint must be populated")
	}
}
