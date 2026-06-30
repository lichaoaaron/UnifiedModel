// Package telemetry defines the provider-neutral interface for querying telemetry data
// (metrics, logs, traces) associated with MModel entities.
//
// The first implementation is the local file provider (localfile sub-package), which
// streams OpenSearch export snapshots from the local filesystem. Future implementations
// can add an OpenSearch provider without changing the Query Service core.
package telemetry

import (
	"context"

	"github.com/alibaba/UnifiedModel/pkg/model"
)

// Kind identifies the telemetry dataset type for a query.
type Kind string

const (
	KindMetricSet Kind = "metric_set"
	KindLogSet    Kind = "log_set"
	KindTraceSet  Kind = "trace_set"
)

// AllowedKinds is the set of valid evidence kinds.
var AllowedKinds = map[Kind]bool{
	KindMetricSet: true,
	KindLogSet:    true,
	KindTraceSet:  true,
}

// QueryRequest describes a telemetry query resolved by the evidence executor.
type QueryRequest struct {
	// Kind is the telemetry dataset type to query.
	Kind Kind

	// ServiceName is the resolved service name filter value, derived from the entity's
	// display_name field via the DataLink fields_mapping.
	ServiceName string

	// TimeFrom is an optional ISO-8601 lower bound for the time range filter.
	TimeFrom string
	// TimeTo is an optional ISO-8601 upper bound for the time range filter.
	TimeTo string

	// Limit is the maximum number of rows to return. Scanning stops once this is reached.
	Limit int

	// StorageProperties are the key-value properties from the Storage element spec,
	// used by the provider to locate data files (e.g. dir paths).
	StorageProperties map[string]string
}

// QueryResult holds the rows returned by a TelemetryProvider along with explain metadata.
type QueryResult struct {
	Rows         []map[string]any
	ScannedFiles []string
	// Metadata contains provider-specific explain-safe values such as endpoint,
	// index, and selected field names. It must not contain secrets.
	Metadata map[string]string
}

// Provider is the provider-neutral interface for querying telemetry evidence.
// Implementations must be safe for concurrent use.
type Provider interface {
	// StorageType returns the storage type string this provider handles
	// (e.g. "local_file"). The evidence executor selects a provider by matching
	// this value against the Storage element's spec.type field.
	StorageType() string

	// Query streams telemetry data matching the request and returns up to Limit rows.
	// Implementations must use streaming / incremental reads; they must not load
	// entire large files into memory at once. Scanning must stop as soon as Limit
	// rows have been collected.
	//
	// Errors should use the project's apperrors package with appropriate codes.
	Query(ctx context.Context, req QueryRequest) (QueryResult, error)
}

// ExplainMetadataProvider is an optional extension implemented by providers that
// can expose explain-safe metadata without performing a full data query.
type ExplainMetadataProvider interface {
	ExplainMetadata(req QueryRequest) (map[string]string, error)
}

// EvidenceRequest is the resolved, ready-to-execute evidence query built by the executor.
type EvidenceRequest struct {
	// Entity is the single entity row resolved from the .entity query.
	Entity map[string]any

	// Plan is the parsed evidence operator parameters.
	Plan model.EvidencePlan

	// DataLinkName is the name of the matched DataLink element.
	DataLinkName string

	// DataSetKind is the kind of the destination DataSet (e.g. "metric_set").
	DataSetKind string

	// DataSetName is the name of the destination DataSet element.
	DataSetName string

	// StorageLinkName is the name of the matched StorageLink element.
	StorageLinkName string

	// StorageName is the name of the matched Storage element.
	StorageName string

	// StorageType is the type string from the Storage element spec.
	StorageType string

	// StorageProperties are the raw key-value properties from the Storage spec.
	StorageProperties map[string]string

	// EntityFieldValue is the value from the entity used for the service name filter,
	// derived via DataLink fields_mapping (display_name -> serviceName).
	EntityFieldValue string

	// FieldsMapping is the fields_mapping from the DataLink.
	FieldsMapping map[string]string
}
