package query

import (
	"context"
	"path/filepath"
	"runtime"
	"testing"

	"github.com/alibaba/MModel/internal/graphstore"
	"github.com/alibaba/MModel/internal/telemetry"
	"github.com/alibaba/MModel/internal/telemetry/localfile"
	apperrors "github.com/alibaba/MModel/pkg/errors"
	"github.com/alibaba/MModel/pkg/model"
)

// --- Test fixture helpers ---

func localfileTestDataRoot() string {
	_, file, _, _ := runtime.Caller(0)
	// testdata is in internal/telemetry/localfile/testdata
	return filepath.Join(filepath.Dir(file), "..", "telemetry", "localfile", "testdata")
}

// platformModelElements returns a minimal model pack for testing evidence() queries.
func platformModelElements() []model.MModelElement {
	return []model.MModelElement{
		{
			Kind:   "entity_set",
			Domain: "platform",
			Name:   "platform.service",
			Spec: map[string]any{
				"fields": []any{
					map[string]any{"name": "id", "type": "string"},
					map[string]any{"name": "display_name", "type": "string"},
				},
			},
		},
		{Kind: "log_set", Domain: "platform", Name: "platform.service_logs", Spec: map[string]any{}},
		{Kind: "metric_set", Domain: "platform", Name: "platform.service_metrics", Spec: map[string]any{}},
		{Kind: "trace_set", Domain: "platform", Name: "platform.service_traces", Spec: map[string]any{}},
		// DataLinks
		{
			Kind: "data_link", Domain: "platform",
			Name: "platform.service_produces_platform.service_logs",
			Spec: map[string]any{
				"src":            map[string]any{"domain": "platform", "kind": "entity_set", "name": "platform.service"},
				"dest":           map[string]any{"domain": "platform", "kind": "log_set", "name": "platform.service_logs"},
				"data_link_type": "produce",
				"fields_mapping": map[string]any{"display_name": "serviceName"},
			},
		},
		{
			Kind: "data_link", Domain: "platform",
			Name: "platform.service_produces_platform.service_metrics",
			Spec: map[string]any{
				"src":            map[string]any{"domain": "platform", "kind": "entity_set", "name": "platform.service"},
				"dest":           map[string]any{"domain": "platform", "kind": "metric_set", "name": "platform.service_metrics"},
				"data_link_type": "produce",
				"fields_mapping": map[string]any{"display_name": "serviceName"},
			},
		},
		{
			Kind: "data_link", Domain: "platform",
			Name: "platform.service_produces_platform.service_traces",
			Spec: map[string]any{
				"src":            map[string]any{"domain": "platform", "kind": "entity_set", "name": "platform.service"},
				"dest":           map[string]any{"domain": "platform", "kind": "trace_set", "name": "platform.service_traces"},
				"data_link_type": "produce",
				"fields_mapping": map[string]any{"display_name": "serviceName"},
			},
		},
		// Storage
		{
			Kind: "external_storage", Domain: "platform", Name: "platform.local_snapshot",
			Spec: map[string]any{
				"type": "local_file",
				"name": "platform.local_snapshot",
				"properties": map[string]any{
					"metric_dir": "metrics",
					"log_dir":    "logs",
					"trace_dir":  "traces",
				},
			},
		},
		// StorageLinks
		{
			Kind: "storage_link", Domain: "platform",
			Name: "platform.service_logs_stored_in_platform.local_snapshot",
			Spec: map[string]any{
				"src":            map[string]any{"domain": "platform", "kind": "log_set", "name": "platform.service_logs"},
				"dest":           map[string]any{"domain": "platform", "kind": "external_storage", "name": "platform.local_snapshot"},
				"fields_mapping": map[string]any{"serviceName": "serviceName", "time": "time"},
			},
		},
		{
			Kind: "storage_link", Domain: "platform",
			Name: "platform.service_metrics_stored_in_platform.local_snapshot",
			Spec: map[string]any{
				"src":            map[string]any{"domain": "platform", "kind": "metric_set", "name": "platform.service_metrics"},
				"dest":           map[string]any{"domain": "platform", "kind": "external_storage", "name": "platform.local_snapshot"},
				"fields_mapping": map[string]any{"serviceName": "serviceName", "time": "time"},
			},
		},
		{
			Kind: "storage_link", Domain: "platform",
			Name: "platform.service_traces_stored_in_platform.local_snapshot",
			Spec: map[string]any{
				"src":            map[string]any{"domain": "platform", "kind": "trace_set", "name": "platform.service_traces"},
				"dest":           map[string]any{"domain": "platform", "kind": "external_storage", "name": "platform.local_snapshot"},
				"fields_mapping": map[string]any{"serviceName": "serviceName", "startTime": "startTime"},
			},
		},
	}
}

func newEvidenceTestService(t *testing.T) *Service {
	t.Helper()
	store := graphstore.NewMemoryStore()
	ctx := context.Background()

	if _, err := store.PutMModelElements(ctx, model.MModelElementBatch{
		Workspace: "test",
		Elements:  platformModelElements(),
	}); err != nil {
		t.Fatalf("put model elements: %v", err)
	}

	if _, err := store.WriteEntities(ctx, model.EntityWriteBatch{
		Workspace: "test",
		Entities: []model.EntityPayload{
			{
				"__domain__": "platform", "__entity_type__": "platform.service",
				"__entity_id__":           "aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001",
				"__method__":              "Update",
				"__first_observed_time__": int64(1748912400),
				"__last_observed_time__":  int64(4102444800),
				"id":                      "aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001", "display_name": "iam-manage", "status": "active",
			},
			{
				"__domain__": "platform", "__entity_type__": "platform.service",
				"__entity_id__":           "aaaaaaaaaaaaaaaaaaaaaaaaaaaa0002",
				"__method__":              "Update",
				"__first_observed_time__": int64(1748912400),
				"__last_observed_time__":  int64(4102444800),
				"id":                      "aaaaaaaaaaaaaaaaaaaaaaaaaaaa0002", "display_name": "ais-consumer", "status": "active",
			},
		},
	}); err != nil {
		t.Fatalf("write entities: %v", err)
	}

	providers := []telemetry.Provider{localfile.New(localfileTestDataRoot())}
	return NewServiceWithProviders(store, providers)
}

// --- Parser tests ---

func TestParseEvidenceOperator(t *testing.T) {
	ast, err := ParseAST(".entity with(domain='platform') | evidence(kind='log_set') | limit 10")
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}
	var evOp *model.EvidencePlan
	for _, op := range ast.Operators {
		if op.Name == "evidence" {
			evOp = op.Evidence
		}
	}
	if evOp == nil {
		t.Fatal("expected evidence operator in AST")
	}
	if evOp.Kind != "log_set" {
		t.Errorf("expected kind=log_set, got %q", evOp.Kind)
	}
}

func TestParseEvidenceWithTimeRange(t *testing.T) {
	ast, err := ParseAST(".entity | evidence(kind='trace_set', from='2026-06-03T01:00:00Z', to='2026-06-03T01:02:00Z')")
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}
	var evOp *model.EvidencePlan
	for _, op := range ast.Operators {
		if op.Name == "evidence" {
			evOp = op.Evidence
		}
	}
	if evOp == nil {
		t.Fatal("expected evidence operator")
	}
	if evOp.From == nil || *evOp.From != "2026-06-03T01:00:00Z" {
		t.Errorf("unexpected from: %v", evOp.From)
	}
	if evOp.To == nil || *evOp.To != "2026-06-03T01:02:00Z" {
		t.Errorf("unexpected to: %v", evOp.To)
	}
}

func TestParseEvidenceInvalidKind(t *testing.T) {
	_, err := ParseAST(".entity | evidence(kind='entity_set')")
	if !apperrors.IsCode(err, apperrors.CodeQueryParseError) {
		t.Fatalf("expected parse error for invalid kind, got %v", err)
	}
}

func TestParseEvidenceMissingKind(t *testing.T) {
	_, err := ParseAST(".entity | evidence(from='2026-06-03T01:00:00Z')")
	if !apperrors.IsCode(err, apperrors.CodeQueryParseError) {
		t.Fatalf("expected parse error for missing kind, got %v", err)
	}
}

func TestParseEvidenceOnlyForEntitySource(t *testing.T) {
	_, err := ParseAST(".mmodel | evidence(kind='log_set')")
	if !apperrors.IsCode(err, apperrors.CodeQueryParseError) {
		t.Fatalf("expected parse error for evidence on .mmodel, got %v", err)
	}
}

// --- Evidence execution tests ---

// TestIAMManageLogsOnlyReturnsIAMManageLogs verifies entity isolation for logs.
func TestIAMManageLogsOnlyReturnsIAMManageLogs(t *testing.T) {
	svc := newEvidenceTestService(t)
	result, err := svc.Execute(context.Background(), "test", model.QueryRequest{
		Query: ".entity with(domain='platform', name='platform.service', ids=('aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001')) | evidence(kind='log_set') | limit 50",
	})
	if err != nil {
		t.Fatalf("execute: %v", err)
	}
	if len(result.Rows) == 0 {
		t.Fatal("expected log rows, got none")
	}
	for _, row := range result.Rows {
		svcName, _ := row["serviceName"].(string)
		if svcName != "iam-manage" {
			t.Errorf("got row from wrong service: %q", svcName)
		}
	}
}

// TestIAMManageTracesOnlyReturnsIAMManageTraces verifies entity isolation for traces.
func TestIAMManageTracesOnlyReturnsIAMManageTraces(t *testing.T) {
	svc := newEvidenceTestService(t)
	result, err := svc.Execute(context.Background(), "test", model.QueryRequest{
		Query: ".entity with(domain='platform', name='platform.service', ids=('aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001')) | evidence(kind='trace_set') | limit 50",
	})
	if err != nil {
		t.Fatalf("execute: %v", err)
	}
	if len(result.Rows) == 0 {
		t.Fatal("expected trace rows, got none")
	}
	for _, row := range result.Rows {
		svcName, _ := row["serviceName"].(string)
		if svcName != "iam-manage" {
			t.Errorf("got trace from wrong service: %q", svcName)
		}
	}
}

// TestServiceMetricsOnlyReturnsOwnMetrics verifies entity isolation for metrics.
func TestServiceMetricsOnlyReturnsOwnMetrics(t *testing.T) {
	svc := newEvidenceTestService(t)
	result, err := svc.Execute(context.Background(), "test", model.QueryRequest{
		Query: ".entity with(domain='platform', name='platform.service', ids=('aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001')) | evidence(kind='metric_set') | limit 50",
	})
	if err != nil {
		t.Fatalf("execute: %v", err)
	}
	if len(result.Rows) == 0 {
		t.Fatal("expected metric rows, got none")
	}
	for _, row := range result.Rows {
		svcName, _ := row["serviceName"].(string)
		if svcName != "iam-manage" {
			t.Errorf("got metric from wrong service: %q", svcName)
		}
	}
}

// TestDoesNotReturnOtherServiceLogs verifies ais-consumer data is not in iam-manage results.
func TestDoesNotReturnOtherServiceLogs(t *testing.T) {
	svc := newEvidenceTestService(t)
	result, err := svc.Execute(context.Background(), "test", model.QueryRequest{
		Query: ".entity with(domain='platform', name='platform.service', ids=('aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001')) | evidence(kind='log_set') | limit 100",
	})
	if err != nil {
		t.Fatalf("execute: %v", err)
	}
	for _, row := range result.Rows {
		if row["serviceName"] == "ais-consumer" {
			t.Errorf("ais-consumer row leaked into iam-manage logs result: %v", row)
		}
	}
}

// TestEvidenceTimeRangeFilterWorks verifies the from/to time filter.
func TestEvidenceTimeRangeFilterWorks(t *testing.T) {
	svc := newEvidenceTestService(t)
	result, err := svc.Execute(context.Background(), "test", model.QueryRequest{
		Query: ".entity with(domain='platform', name='platform.service', ids=('aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001')) | evidence(kind='log_set', from='2026-06-03T01:00:00Z', to='2026-06-03T01:00:59Z') | limit 100",
	})
	if err != nil {
		t.Fatalf("execute: %v", err)
	}
	for _, row := range result.Rows {
		ts, _ := row["time"].(string)
		if ts >= "2026-06-03T01:01:00Z" {
			t.Errorf("row outside time window returned: time=%q", ts)
		}
	}
	if len(result.Rows) == 0 {
		t.Fatal("expected rows in time window, got none")
	}
}

// TestEvidenceLimitIsRespected verifies that limit stops scanning.
func TestEvidenceLimitIsRespected(t *testing.T) {
	svc := newEvidenceTestService(t)
	result, err := svc.Execute(context.Background(), "test", model.QueryRequest{
		Query: ".entity with(domain='platform', name='platform.service', ids=('aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001')) | evidence(kind='log_set') | limit 2",
	})
	if err != nil {
		t.Fatalf("execute: %v", err)
	}
	if len(result.Rows) > 2 {
		t.Errorf("limit not respected: got %d rows", len(result.Rows))
	}
}

// TestEvidenceZeroEntitiesReturnsError verifies the zero-entity error.
func TestEvidenceZeroEntitiesReturnsError(t *testing.T) {
	svc := newEvidenceTestService(t)
	_, err := svc.Execute(context.Background(), "test", model.QueryRequest{
		// Non-existent entity ID
		Query: ".entity with(domain='platform', name='platform.service', ids=('ffffffffffffffffffffffffffffffff')) | evidence(kind='log_set') | limit 10",
	})
	if err == nil {
		t.Fatal("expected error for zero entities, got nil")
	}
	if !apperrors.IsCode(err, apperrors.CodeInvalidArgument) {
		t.Errorf("expected INVALID_ARGUMENT, got %v", err)
	}
}

// TestEvidenceMultipleEntitiesReturnsError verifies the multiple-entity error.
func TestEvidenceMultipleEntitiesReturnsError(t *testing.T) {
	svc := newEvidenceTestService(t)
	// Query without ID filter returns both entities
	_, err := svc.Execute(context.Background(), "test", model.QueryRequest{
		Query: ".entity with(domain='platform', name='platform.service') | evidence(kind='log_set') | limit 10",
	})
	if err == nil {
		t.Fatal("expected error for multiple entities, got nil")
	}
	if !apperrors.IsCode(err, apperrors.CodeInvalidArgument) {
		t.Errorf("expected INVALID_ARGUMENT, got %v", err)
	}
}

// TestEvidenceNoDataLinkReturnsError verifies a clear error when DataLink is missing.
func TestEvidenceNoDataLinkReturnsError(t *testing.T) {
	store := graphstore.NewMemoryStore()
	ctx := context.Background()
	elements := []model.MModelElement{
		{Kind: "entity_set", Domain: "platform", Name: "platform.service",
			Spec: map[string]any{"fields": []any{map[string]any{"name": "display_name"}}}},
		// NO data_link elements
	}
	if _, err := store.PutMModelElements(ctx, model.MModelElementBatch{Workspace: "test", Elements: elements}); err != nil {
		t.Fatalf("put elements: %v", err)
	}
	if _, err := store.WriteEntities(ctx, model.EntityWriteBatch{
		Workspace: "test",
		Entities: []model.EntityPayload{{
			"__domain__": "platform", "__entity_type__": "platform.service",
			"__entity_id__":           "aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001",
			"__method__":              "Update",
			"__first_observed_time__": int64(1748912400),
			"__last_observed_time__":  int64(4102444800),
			"display_name":            "iam-manage",
		}},
	}); err != nil {
		t.Fatalf("write entities: %v", err)
	}
	providers := []telemetry.Provider{localfile.New(localfileTestDataRoot())}
	svc := NewServiceWithProviders(store, providers)
	_, err := svc.Execute(ctx, "test", model.QueryRequest{
		Query: ".entity with(domain='platform', name='platform.service', ids=('aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001')) | evidence(kind='log_set') | limit 10",
	})
	if !apperrors.IsCode(err, apperrors.CodeNotFound) {
		t.Errorf("expected NOT_FOUND for missing DataLink, got %v", err)
	}
}

// TestEvidenceExplainContainsChain verifies explain includes full resolution chain.
func TestEvidenceExplainContainsChain(t *testing.T) {
	svc := newEvidenceTestService(t)
	result, err := svc.Execute(context.Background(), "test", model.QueryRequest{
		Query: ".entity with(domain='platform', name='platform.service', ids=('aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001')) | evidence(kind='log_set') | limit 10",
	})
	if err != nil {
		t.Fatalf("execute: %v", err)
	}
	if result.Explain == nil {
		t.Fatal("expected explain, got nil")
	}
	ev := result.Explain.Evidence
	if ev == nil {
		t.Fatal("expected evidence explain, got nil")
	}
	if ev.EntityID != "aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001" {
		t.Errorf("wrong entity ID in explain: %q", ev.EntityID)
	}
	if ev.EntityType != "platform.service" {
		t.Errorf("wrong entity type in explain: %q", ev.EntityType)
	}
	if ev.EntityFieldValue != "iam-manage" {
		t.Errorf("wrong entity field value in explain: %q", ev.EntityFieldValue)
	}
	if ev.DataLinkName == "" {
		t.Error("missing DataLink name in explain")
	}
	if ev.DataSetKind != "log_set" {
		t.Errorf("wrong dataset kind in explain: %q", ev.DataSetKind)
	}
	if ev.StorageLinkName == "" {
		t.Error("missing StorageLink name in explain")
	}
	if ev.StorageName == "" {
		t.Error("missing storage name in explain")
	}
	if ev.Provider != "local_file" {
		t.Errorf("wrong provider in explain: %q", ev.Provider)
	}
	if len(ev.ScannedFiles) == 0 {
		t.Error("expected scanned files in explain")
	}
}

// TestExistingEntityQueryNotBroken verifies the original .entity behavior is intact.
func TestExistingEntityQueryNotBroken(t *testing.T) {
	svc := newEvidenceTestService(t)
	result, err := svc.Execute(context.Background(), "test", model.QueryRequest{
		Query: ".entity with(domain='platform', name='platform.service') | limit 10",
	})
	if err != nil {
		t.Fatalf("execute existing entity query: %v", err)
	}
	if len(result.Rows) == 0 {
		t.Fatal("expected entity rows from plain .entity query")
	}
	// Ensure no evidence explain is set for plain queries
	if result.Explain != nil && result.Explain.Evidence != nil {
		t.Error("plain .entity query should not have evidence explain")
	}
}

// TestEvidenceWithProjectReturnsRows verifies that project after evidence() works
// and does not cause a DataLink-not-found error (Problem 1 regression guard).
func TestEvidenceWithProjectReturnsRows(t *testing.T) {
	svc := newEvidenceTestService(t)
	result, err := svc.Execute(context.Background(), "test", model.QueryRequest{
		Query: ".entity with(domain='platform', name='platform.service', ids=('aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001')) | evidence(kind='log_set') | project serviceName,time,severityText | limit 5",
	})
	if err != nil {
		t.Fatalf("execute with project: %v", err)
	}
	if len(result.Rows) == 0 {
		t.Fatal("expected rows after project, got none")
	}
	// After project, only the projected columns should remain.
	for _, row := range result.Rows {
		if _, hasServiceName := row["serviceName"]; !hasServiceName {
			t.Errorf("projected column serviceName missing from row: %v", row)
		}
		// Entity context fields must NOT appear in projected rows.
		if _, hasDomain := row["__domain__"]; hasDomain {
			t.Errorf("__domain__ leaked into projected telemetry row: %v", row)
		}
	}
}

// TestEvidenceProjectDoesNotStripEntityContext verifies that project only affects
// the telemetry rows returned by evidence, not the entity rows used for evidence
// resolution. This is the core correctness invariant for Problem 1.
func TestEvidenceProjectDoesNotStripEntityContext(t *testing.T) {
	svc := newEvidenceTestService(t)
	// Without project: should return rows with all telemetry fields.
	without, err := svc.Execute(context.Background(), "test", model.QueryRequest{
		Query: ".entity with(domain='platform', name='platform.service', ids=('aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001')) | evidence(kind='log_set') | limit 10",
	})
	if err != nil {
		t.Fatalf("without project: %v", err)
	}
	// With project targeting a subset of telemetry fields.
	with, err := svc.Execute(context.Background(), "test", model.QueryRequest{
		Query: ".entity with(domain='platform', name='platform.service', ids=('aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001')) | evidence(kind='log_set') | project serviceName,body | limit 10",
	})
	if err != nil {
		t.Fatalf("with project: %v", err)
	}
	// Both should return the same number of matching rows.
	if len(with.Rows) != len(without.Rows) {
		t.Errorf("project changed row count: without=%d, with=%d", len(without.Rows), len(with.Rows))
	}
	// Projected rows should only have projected columns.
	for _, row := range with.Rows {
		if _, ok := row["serviceName"]; !ok {
			t.Errorf("serviceName missing after project")
		}
		if _, ok := row["body"]; !ok {
			t.Errorf("body missing after project")
		}
		if _, ok := row["severityText"]; ok {
			t.Errorf("severityText should have been projected away")
		}
	}
}

// TestEvidenceExplainViaExplainAPI verifies that query explain returns the full
// evidence chain (Problem 2 regression guard).
func TestEvidenceExplainViaExplainAPI(t *testing.T) {
	svc := newEvidenceTestService(t)
	explain, err := svc.Explain(context.Background(), "test", model.QueryRequest{
		Query: ".entity with(domain='platform', name='platform.service', ids=('aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001')) | evidence(kind='log_set') | limit 10",
	})
	if err != nil {
		t.Fatalf("explain: %v", err)
	}
	if explain.Evidence == nil {
		t.Fatal("query explain did not return evidence section")
	}
	ev := explain.Evidence
	if ev.EntityID != "aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001" {
		t.Errorf("wrong entity ID: %q", ev.EntityID)
	}
	if ev.EntityType != "platform.service" {
		t.Errorf("wrong entity type: %q", ev.EntityType)
	}
	if ev.EntityFieldValue != "iam-manage" {
		t.Errorf("wrong entity field value: %q", ev.EntityFieldValue)
	}
	if ev.DataLinkName == "" {
		t.Error("missing DataLink name in explain")
	}
	if ev.DataSetKind != "log_set" {
		t.Errorf("wrong dataset kind: %q", ev.DataSetKind)
	}
	if ev.StorageLinkName == "" {
		t.Error("missing StorageLink name in explain")
	}
	if ev.StorageName == "" {
		t.Error("missing storage name in explain")
	}
	if ev.Provider == "" {
		t.Error("missing provider in explain")
	}
	if len(ev.FieldsMapping) == 0 {
		t.Error("missing fields_mapping in explain")
	}
}

// TestEvidenceExplainAPIDoesNotPopulateScannedFiles verifies that explain-only path
// does not stream files (scanned_files and returned_rows should be zero/empty).
func TestEvidenceExplainAPIDoesNotPopulateScannedFiles(t *testing.T) {
	svc := newEvidenceTestService(t)
	explain, err := svc.Explain(context.Background(), "test", model.QueryRequest{
		Query: ".entity with(domain='platform', name='platform.service', ids=('aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001')) | evidence(kind='log_set') | limit 10",
	})
	if err != nil {
		t.Fatalf("explain: %v", err)
	}
	if explain.Evidence == nil {
		t.Skip("evidence explain not populated")
	}
	// Explain-only path must NOT stream files.
	if len(explain.Evidence.ScannedFiles) > 0 {
		t.Errorf("explain should not populate scanned_files, got %v", explain.Evidence.ScannedFiles)
	}
	if explain.Evidence.ReturnedRows != 0 {
		t.Errorf("explain should not populate returned_rows, got %d", explain.Evidence.ReturnedRows)
	}
}

// TestEvidenceLimitAppliedAfterProject verifies that limit correctly applies after
// project in post-evidence pipeline.
func TestEvidenceLimitAppliedAfterProject(t *testing.T) {
	svc := newEvidenceTestService(t)
	result, err := svc.Execute(context.Background(), "test", model.QueryRequest{
		Query: ".entity with(domain='platform', name='platform.service', ids=('aaaaaaaaaaaaaaaaaaaaaaaaaaaa0001')) | evidence(kind='log_set') | project serviceName,time | limit 1",
	})
	if err != nil {
		t.Fatalf("execute: %v", err)
	}
	if len(result.Rows) > 1 {
		t.Errorf("limit 1 not respected after project: got %d rows", len(result.Rows))
	}
}
