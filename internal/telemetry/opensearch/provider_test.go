package opensearch

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/alibaba/MModel/internal/telemetry"
	apperrors "github.com/alibaba/MModel/pkg/errors"
)

func baseProps(endpoint string) map[string]string {
	return map[string]string{
		"endpoint":                  endpoint,
		"username":                  "admin",
		"password":                  "secret",
		"log_index":                 "logs-index",
		"metric_index":              "metrics-index",
		"trace_index":               "traces-index",
		"time_field_log":            "time",
		"time_field_metric":         "time",
		"time_field_trace":          "startTime",
		"service_name_field_log":    "serviceName",
		"service_name_field_metric": "serviceName",
		"service_name_field_trace":  "serviceName",
	}
}

func TestBuildSearchBodyIncludesServiceTimeAndLimit(t *testing.T) {
	body := buildSearchBody(telemetry.QueryRequest{
		ServiceName: "iam-manage",
		TimeFrom:    "2026-06-03T01:00:00Z",
		TimeTo:      "2026-06-03T01:02:00Z",
		Limit:       5,
	}, "serviceName", "time")

	if body["size"].(int) != 5 {
		t.Fatalf("size mismatch: %v", body["size"])
	}
	query := body["query"].(map[string]any)
	filters := query["bool"].(map[string]any)["filter"].([]any)
	if len(filters) != 2 {
		t.Fatalf("expected 2 filters, got %d", len(filters))
	}
}

func TestResolveKindConfigUsesKindSpecificIndexAndFields(t *testing.T) {
	props := baseProps("http://localhost:9200")

	idx, tf, sf, err := resolveKindConfig(telemetry.QueryRequest{Kind: telemetry.KindLogSet, StorageProperties: props})
	if err != nil {
		t.Fatalf("log resolve failed: %v", err)
	}
	if idx != "logs-index" || tf != "time" || sf != "serviceName" {
		t.Fatalf("unexpected log config: %s %s %s", idx, tf, sf)
	}

	idx, tf, sf, err = resolveKindConfig(telemetry.QueryRequest{Kind: telemetry.KindTraceSet, StorageProperties: props})
	if err != nil {
		t.Fatalf("trace resolve failed: %v", err)
	}
	if idx != "traces-index" || tf != "startTime" || sf != "serviceName" {
		t.Fatalf("unexpected trace config: %s %s %s", idx, tf, sf)
	}

	idx, tf, sf, err = resolveKindConfig(telemetry.QueryRequest{Kind: telemetry.KindMetricSet, StorageProperties: props})
	if err != nil {
		t.Fatalf("metric resolve failed: %v", err)
	}
	if idx != "metrics-index" || tf != "time" || sf != "serviceName" {
		t.Fatalf("unexpected metric config: %s %s %s", idx, tf, sf)
	}
}

func TestQueryUsesLogIndexAndFields(t *testing.T) {
	var capturedPath string
	var capturedBody map[string]any

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedPath = r.URL.Path
		defer r.Body.Close()
		if err := json.NewDecoder(r.Body).Decode(&capturedBody); err != nil {
			t.Fatalf("decode body: %v", err)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"hits":{"hits":[{"_source":{"serviceName":"iam-manage","time":"2026-06-03T01:00:10Z","severityText":"INFO"}}]}}`))
	}))
	defer srv.Close()

	p := New()
	res, err := p.Query(context.Background(), telemetry.QueryRequest{
		Kind:              telemetry.KindLogSet,
		ServiceName:       "iam-manage",
		TimeFrom:          "2026-06-03T01:00:00Z",
		TimeTo:            "2026-06-03T01:02:00Z",
		Limit:             5,
		StorageProperties: baseProps(srv.URL),
	})
	if err != nil {
		t.Fatalf("query failed: %v", err)
	}
	if capturedPath != "/logs-index/_search" {
		t.Fatalf("unexpected path: %s", capturedPath)
	}
	if len(res.Rows) != 1 {
		t.Fatalf("unexpected row count: %d", len(res.Rows))
	}
	if capturedBody["size"].(float64) != 5 {
		t.Fatalf("size mismatch in body: %v", capturedBody["size"])
	}
	filters := capturedBody["query"].(map[string]any)["bool"].(map[string]any)["filter"].([]any)
	if len(filters) != 2 {
		t.Fatalf("expected 2 filters, got %d", len(filters))
	}
	term := filters[0].(map[string]any)["term"].(map[string]any)
	if term["serviceName"].(string) != "iam-manage" {
		t.Fatalf("service filter mismatch: %#v", term)
	}
	rangeFilter := filters[1].(map[string]any)["range"].(map[string]any)["time"].(map[string]any)
	if rangeFilter["gte"].(string) != "2026-06-03T01:00:00Z" {
		t.Fatalf("time gte mismatch: %#v", rangeFilter)
	}
	if rangeFilter["lte"].(string) != "2026-06-03T01:02:00Z" {
		t.Fatalf("time lte mismatch: %#v", rangeFilter)
	}
	meta := res.Metadata
	if meta["index"] != "logs-index" || meta["service_field"] != "serviceName" || meta["time_field"] != "time" {
		t.Fatalf("metadata mismatch: %#v", meta)
	}
}

func TestQueryUsesTraceIndexAndMetricIndex(t *testing.T) {
	var paths []string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		paths = append(paths, r.URL.Path)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"hits":{"hits":[]}}`))
	}))
	defer srv.Close()

	p := New()
	props := baseProps(srv.URL)
	_, err := p.Query(context.Background(), telemetry.QueryRequest{Kind: telemetry.KindTraceSet, ServiceName: "iam-manage", Limit: 3, StorageProperties: props})
	if err != nil {
		t.Fatalf("trace query failed: %v", err)
	}
	_, err = p.Query(context.Background(), telemetry.QueryRequest{Kind: telemetry.KindMetricSet, ServiceName: "iam-manage", Limit: 2, StorageProperties: props})
	if err != nil {
		t.Fatalf("metric query failed: %v", err)
	}
	if len(paths) != 2 {
		t.Fatalf("expected 2 requests, got %d", len(paths))
	}
	if paths[0] != "/traces-index/_search" {
		t.Fatalf("unexpected trace path: %s", paths[0])
	}
	if paths[1] != "/metrics-index/_search" {
		t.Fatalf("unexpected metric path: %s", paths[1])
	}
}

func TestQueryMapsHTTPStatusToStableErrors(t *testing.T) {
	cases := []struct {
		name string
		code int
		err  apperrors.Code
	}{
		{name: "401", code: http.StatusUnauthorized, err: apperrors.CodeProviderUnavailable},
		{name: "403", code: http.StatusForbidden, err: apperrors.CodeProviderUnavailable},
		{name: "404", code: http.StatusNotFound, err: apperrors.CodeNotFound},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(tc.code)
				_, _ = w.Write([]byte(`{"error":"x"}`))
			}))
			defer srv.Close()

			_, err := New().Query(context.Background(), telemetry.QueryRequest{
				Kind:              telemetry.KindLogSet,
				ServiceName:       "iam-manage",
				Limit:             1,
				StorageProperties: baseProps(srv.URL),
			})
			if !apperrors.IsCode(err, tc.err) {
				t.Fatalf("expected %s, got %v", tc.err, err)
			}
		})
	}
}

func TestQueryTimeoutMappedToStableError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(60 * time.Millisecond)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"hits":{"hits":[]}}`))
	}))
	defer srv.Close()

	props := baseProps(srv.URL)
	props["request_timeout_ms"] = "10"

	_, err := New().Query(context.Background(), telemetry.QueryRequest{
		Kind:              telemetry.KindLogSet,
		ServiceName:       "iam-manage",
		Limit:             1,
		StorageProperties: props,
	})
	if !apperrors.IsCode(err, apperrors.CodeTimeout) {
		t.Fatalf("expected timeout, got %v", err)
	}
}

func TestExplainMetadataSanitizesEndpoint(t *testing.T) {
	props := baseProps("http://user:pass@localhost:9200?token=abc")
	meta, err := New().ExplainMetadata(telemetry.QueryRequest{Kind: telemetry.KindLogSet, StorageProperties: props})
	if err != nil {
		t.Fatalf("ExplainMetadata error: %v", err)
	}
	if meta["endpoint"] != "http://localhost:9200" {
		t.Fatalf("endpoint was not sanitized: %s", meta["endpoint"])
	}
}
