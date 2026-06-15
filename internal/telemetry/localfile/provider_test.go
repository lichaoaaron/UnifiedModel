package localfile_test

import (
	"context"
	"path/filepath"
	"runtime"
	"testing"

	"github.com/alibaba/UnifiedModel/internal/telemetry"
	"github.com/alibaba/UnifiedModel/internal/telemetry/localfile"
)

func testDataRoot() string {
	_, file, _, _ := runtime.Caller(0)
	return filepath.Join(filepath.Dir(file), "testdata")
}

func storageProps(kind telemetry.Kind) map[string]string {
	switch kind {
	case telemetry.KindLogSet:
		return map[string]string{"log_dir": "logs", "metric_dir": "metrics", "trace_dir": "traces"}
	case telemetry.KindMetricSet:
		return map[string]string{"log_dir": "logs", "metric_dir": "metrics", "trace_dir": "traces"}
	case telemetry.KindTraceSet:
		return map[string]string{"log_dir": "logs", "metric_dir": "metrics", "trace_dir": "traces"}
	default:
		return map[string]string{}
	}
}

// TestIAMManageLogsOnlyReturnsIAMManage verifies that querying logs for iam-manage
// returns only iam-manage log entries, not entries from other services.
func TestIAMManageLogsOnlyReturnsIAMManage(t *testing.T) {
	p := localfile.New(testDataRoot())
	result, err := p.Query(context.Background(), telemetry.QueryRequest{
		Kind:              telemetry.KindLogSet,
		ServiceName:       "iam-manage",
		Limit:             100,
		StorageProperties: storageProps(telemetry.KindLogSet),
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if len(result.Rows) == 0 {
		t.Fatal("expected at least one row, got none")
	}

	for _, row := range result.Rows {
		svc, _ := row["serviceName"].(string)
		if svc != "iam-manage" {
			t.Errorf("got row from wrong service: %q", svc)
		}
	}
}

// TestIAMManageTracesOnlyReturnsIAMManage verifies that querying traces for iam-manage
// returns only iam-manage span entries.
func TestIAMManageTracesOnlyReturnsIAMManage(t *testing.T) {
	p := localfile.New(testDataRoot())
	result, err := p.Query(context.Background(), telemetry.QueryRequest{
		Kind:              telemetry.KindTraceSet,
		ServiceName:       "iam-manage",
		Limit:             100,
		StorageProperties: storageProps(telemetry.KindTraceSet),
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if len(result.Rows) == 0 {
		t.Fatal("expected at least one trace row, got none")
	}
	for _, row := range result.Rows {
		svc, _ := row["serviceName"].(string)
		if svc != "iam-manage" {
			t.Errorf("got trace from wrong service: %q", svc)
		}
	}
}

// TestServiceWithMetricsReturnsOnlyOwnMetrics verifies that iam-manage metrics only
// contain iam-manage entries.
func TestServiceWithMetricsReturnsOnlyOwnMetrics(t *testing.T) {
	p := localfile.New(testDataRoot())
	result, err := p.Query(context.Background(), telemetry.QueryRequest{
		Kind:              telemetry.KindMetricSet,
		ServiceName:       "iam-manage",
		Limit:             100,
		StorageProperties: storageProps(telemetry.KindMetricSet),
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Rows) == 0 {
		t.Fatal("expected at least one metric row")
	}
	for _, row := range result.Rows {
		svc, _ := row["serviceName"].(string)
		if svc != "iam-manage" {
			t.Errorf("got metric from wrong service: %q", svc)
		}
	}
}

// TestDoesNotReturnOtherServiceData verifies that ais-consumer data is not returned
// when querying for iam-manage.
func TestDoesNotReturnOtherServiceData(t *testing.T) {
	p := localfile.New(testDataRoot())
	result, err := p.Query(context.Background(), telemetry.QueryRequest{
		Kind:              telemetry.KindLogSet,
		ServiceName:       "iam-manage",
		Limit:             100,
		StorageProperties: storageProps(telemetry.KindLogSet),
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	for _, row := range result.Rows {
		svc, _ := row["serviceName"].(string)
		if svc == "ais-consumer" {
			t.Errorf("ais-consumer row leaked into iam-manage result: %v", row)
		}
	}
}

// TestTimeRangeFilterIsApplied verifies that the time filter excludes records
// outside the specified window.
func TestTimeRangeFilterIsApplied(t *testing.T) {
	p := localfile.New(testDataRoot())
	// Window: only first minute of data
	result, err := p.Query(context.Background(), telemetry.QueryRequest{
		Kind:              telemetry.KindLogSet,
		ServiceName:       "iam-manage",
		TimeFrom:          "2026-06-03T01:00:00Z",
		TimeTo:            "2026-06-03T01:00:59Z",
		Limit:             100,
		StorageProperties: storageProps(telemetry.KindLogSet),
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	for _, row := range result.Rows {
		ts, _ := row["time"].(string)
		// Should not include the entry at 01:01:00
		if ts >= "2026-06-03T01:01:00Z" {
			t.Errorf("row outside time window returned: time=%q", ts)
		}
	}
	// Should have iam-manage entries from 01:00:10 and 01:00:20
	if len(result.Rows) == 0 {
		t.Fatal("expected at least one row within time window")
	}
}

// TestLimitStopsScanning verifies that scanning stops once limit rows are collected.
func TestLimitStopsScanning(t *testing.T) {
	p := localfile.New(testDataRoot())
	result, err := p.Query(context.Background(), telemetry.QueryRequest{
		Kind:              telemetry.KindLogSet,
		ServiceName:       "iam-manage",
		Limit:             2,
		StorageProperties: storageProps(telemetry.KindLogSet),
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Rows) > 2 {
		t.Errorf("limit not respected: got %d rows, want <= 2", len(result.Rows))
	}
	if len(result.Rows) == 0 {
		t.Fatal("expected rows, got none")
	}
}

// TestScannedFilesReported verifies that scanned file paths are reported in the result.
func TestScannedFilesReported(t *testing.T) {
	p := localfile.New(testDataRoot())
	result, err := p.Query(context.Background(), telemetry.QueryRequest{
		Kind:              telemetry.KindLogSet,
		ServiceName:       "iam-manage",
		Limit:             100,
		StorageProperties: storageProps(telemetry.KindLogSet),
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.ScannedFiles) == 0 {
		t.Error("expected scanned files to be reported")
	}
}

// TestMissingDirectoryReturnsError verifies a clear error when the data directory
// does not exist.
func TestMissingDirectoryReturnsError(t *testing.T) {
	p := localfile.New(testDataRoot())
	_, err := p.Query(context.Background(), telemetry.QueryRequest{
		Kind:              telemetry.KindLogSet,
		ServiceName:       "iam-manage",
		Limit:             10,
		StorageProperties: map[string]string{"log_dir": "nonexistent"},
	})
	if err == nil {
		t.Fatal("expected error for missing directory, got nil")
	}
}
