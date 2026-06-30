// Package localfile implements a TelemetryProvider that streams OpenSearch export
// JSON files from the local filesystem. It uses incremental JSON token decoding
// (encoding/json Decoder) to avoid loading entire large files into memory.
package localfile

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	apperrors "github.com/alibaba/UnifiedModel/pkg/errors"

	"github.com/alibaba/UnifiedModel/internal/telemetry"
)

const storageType = "local_file"

// Provider streams local OpenSearch export JSON files.
type Provider struct {
	// dataRoot is the workspace root used to resolve relative storage paths.
	dataRoot string
}

// New creates a new local file provider.
// dataRoot is the directory relative to which storage paths are resolved.
func New(dataRoot string) *Provider {
	return &Provider{dataRoot: dataRoot}
}

// StorageType returns the storage type string this provider handles.
func (p *Provider) StorageType() string { return storageType }

// Query streams telemetry files for the given service name and returns up to Limit rows.
func (p *Provider) Query(ctx context.Context, req telemetry.QueryRequest) (telemetry.QueryResult, error) {
	dir, err := p.resolveDir(req)
	if err != nil {
		return telemetry.QueryResult{}, err
	}

	files, err := listJSONFiles(dir)
	if err != nil {
		return telemetry.QueryResult{}, err
	}

	timeField := resolveTimeField(req.Kind, req.StorageProperties)

	var (
		rows         []map[string]any
		scannedFiles []string
	)

	for _, file := range files {
		select {
		case <-ctx.Done():
			return telemetry.QueryResult{}, apperrors.New(apperrors.CodeTimeout, "evidence query cancelled")
		default:
		}

		scannedFiles = append(scannedFiles, file)
		done, err := streamFile(ctx, file, req.ServiceName, timeField, req.TimeFrom, req.TimeTo, req.Limit, &rows)
		if err != nil {
			return telemetry.QueryResult{}, err
		}
		if done {
			break
		}
	}

	return telemetry.QueryResult{
		Rows:         rows,
		ScannedFiles: scannedFiles,
	}, nil
}

// resolveDir maps the query kind to a directory path using storage properties.
func (p *Provider) resolveDir(req telemetry.QueryRequest) (string, error) {
	var key string
	switch req.Kind {
	case telemetry.KindMetricSet:
		key = "metric_dir"
	case telemetry.KindLogSet:
		key = "log_dir"
	case telemetry.KindTraceSet:
		key = "trace_dir"
	default:
		return "", apperrors.WithDetails(apperrors.CodeQueryPlanError, "unsupported evidence kind", map[string]string{"kind": string(req.Kind)})
	}

	dir, ok := req.StorageProperties[key]
	if !ok || strings.TrimSpace(dir) == "" {
		return "", apperrors.WithDetails(apperrors.CodeProviderUnavailable, "storage property missing", map[string]string{"key": key})
	}

	// Resolve relative to data root
	if !filepath.IsAbs(dir) {
		dir = filepath.Join(p.dataRoot, dir)
	}
	return dir, nil
}

// listJSONFiles returns sorted *.json file paths in dir.
func listJSONFiles(dir string) ([]string, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, apperrors.WithDetails(apperrors.CodeProviderUnavailable, "telemetry data directory not found", map[string]string{"dir": dir})
		}
		return nil, apperrors.WithDetails(apperrors.CodeInternal, "failed to read telemetry directory", map[string]string{"dir": dir, "error": err.Error()})
	}

	var files []string
	for _, e := range entries {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".json") {
			files = append(files, filepath.Join(dir, e.Name()))
		}
	}
	sort.Strings(files)
	return files, nil
}

// resolveTimeField returns the time field name for a given kind, with a fallback to
// storage properties and then to hardcoded defaults.
func resolveTimeField(kind telemetry.Kind, props map[string]string) string {
	switch kind {
	case telemetry.KindMetricSet:
		if v, ok := props["time_field_metric"]; ok && v != "" {
			return v
		}
		return "time"
	case telemetry.KindLogSet:
		if v, ok := props["time_field_log"]; ok && v != "" {
			return v
		}
		return "time"
	case telemetry.KindTraceSet:
		if v, ok := props["time_field_trace"]; ok && v != "" {
			return v
		}
		return "startTime"
	default:
		return "time"
	}
}

// streamFile opens a single JSON file and streams its records into rows.
// It returns done=true when the limit has been reached.
// The file is expected to be a JSON array of objects.
func streamFile(
	ctx context.Context,
	path string,
	serviceName string,
	timeField string,
	timeFrom, timeTo string,
	limit int,
	rows *[]map[string]any,
) (bool, error) {
	f, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return false, apperrors.WithDetails(apperrors.CodeProviderUnavailable, "telemetry file not found", map[string]string{"file": path})
		}
		return false, apperrors.WithDetails(apperrors.CodeInternal, "failed to open telemetry file", map[string]string{"file": path, "error": err.Error()})
	}
	defer f.Close()

	dec := json.NewDecoder(f)

	// Expect opening '['
	tok, err := dec.Token()
	if err != nil {
		if err == io.EOF {
			return false, nil
		}
		return false, wrapJSONError(path, err)
	}
	delim, ok := tok.(json.Delim)
	if !ok || delim != '[' {
		return false, apperrors.WithDetails(apperrors.CodeInternal, "telemetry file does not start with JSON array", map[string]string{"file": path})
	}

	for dec.More() {
		select {
		case <-ctx.Done():
			return false, apperrors.New(apperrors.CodeTimeout, "evidence query cancelled")
		default:
		}

		var record map[string]any
		if err := dec.Decode(&record); err != nil {
			return false, wrapJSONError(path, err)
		}

		// Filter by service name
		if !matchesServiceName(record, serviceName) {
			continue
		}

		// Filter by time range
		if timeFrom != "" || timeTo != "" {
			if !matchesTimeRange(record, timeField, timeFrom, timeTo) {
				continue
			}
		}

		*rows = append(*rows, record)
		if limit > 0 && len(*rows) >= limit {
			return true, nil
		}
	}

	return false, nil
}

// matchesServiceName checks if a record belongs to the given serviceName.
// It checks both the top-level "serviceName" field and the
// "resource.attributes.service@name" field.
func matchesServiceName(record map[string]any, serviceName string) bool {
	if v, ok := record["serviceName"]; ok {
		if s, ok := v.(string); ok && s == serviceName {
			return true
		}
	}
	if v, ok := record["resource.attributes.service@name"]; ok {
		if s, ok := v.(string); ok && s == serviceName {
			return true
		}
	}
	return false
}

// matchesTimeRange checks if the record's time field falls within [timeFrom, timeTo].
// Missing or unparseable time fields are treated as matching (pass-through).
func matchesTimeRange(record map[string]any, timeField, timeFrom, timeTo string) bool {
	raw, ok := record[timeField]
	if !ok {
		return true
	}
	ts, ok := raw.(string)
	if !ok || ts == "" {
		return true
	}

	t, err := time.Parse(time.RFC3339Nano, ts)
	if err != nil {
		// Try RFC3339 without nanoseconds
		t, err = time.Parse(time.RFC3339, ts)
		if err != nil {
			return true
		}
	}

	if timeFrom != "" {
		from, err := time.Parse(time.RFC3339, timeFrom)
		if err == nil && t.Before(from) {
			return false
		}
	}
	if timeTo != "" {
		to, err := time.Parse(time.RFC3339, timeTo)
		if err == nil && t.After(to) {
			return false
		}
	}
	return true
}

func wrapJSONError(path string, err error) error {
	return apperrors.WithDetails(apperrors.CodeInternal, fmt.Sprintf("failed to parse telemetry JSON: %v", err), map[string]string{"file": path})
}
