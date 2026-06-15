package query

import (
	"context"
	"fmt"

	"github.com/alibaba/UnifiedModel/internal/telemetry"
	apperrors "github.com/alibaba/UnifiedModel/pkg/errors"
	"github.com/alibaba/UnifiedModel/pkg/model"
)

// evidenceExecutor resolves the evidence() operator chain and queries a TelemetryProvider.
type evidenceExecutor struct {
	graph     graphStore
	providers map[string]telemetry.Provider
}

func newEvidenceExecutor(graph graphStore, providers []telemetry.Provider) *evidenceExecutor {
	m := make(map[string]telemetry.Provider, len(providers))
	for _, p := range providers {
		m[p.StorageType()] = p
	}
	return &evidenceExecutor{graph: graph, providers: m}
}

// executeEvidence runs the evidence pipeline operator against a set of entity rows.
// The entity rows must contain exactly one row (validated here).
// It resolves DataLink → DataSet → StorageLink → Storage → Provider and streams results.
func (e *evidenceExecutor) executeEvidence(
	ctx context.Context,
	workspace string,
	entityRows []map[string]any,
	op model.QueryPipelineOperator,
	limit int,
) (model.QueryResult, *model.EvidenceExplain, error) {
	plan := op.Evidence
	if plan == nil {
		return model.QueryResult{}, nil, apperrors.New(apperrors.CodeQueryPlanError, "evidence operator missing plan")
	}

	if len(entityRows) == 0 {
		return model.QueryResult{}, nil, apperrors.WithDetails(
			apperrors.CodeInvalidArgument, "evidence requires exactly one entity, got 0",
			map[string]string{"got": "0"},
		)
	}
	if len(entityRows) > 1 {
		return model.QueryResult{}, nil, apperrors.WithDetails(
			apperrors.CodeInvalidArgument, "evidence requires exactly one entity",
			map[string]string{"got": fmt.Sprint(len(entityRows))},
		)
	}

	entity := entityRows[0]
	entityID := stringValue(entity["__entity_id__"])
	entityType := stringValue(entity["__entity_type__"])
	entityDomain := stringValue(entity["__domain__"])

	// Load UModel snapshot to resolve links
	snapshot, err := e.graph.GetUModelSnapshot(ctx, model.UModelSnapshotRequest{Workspace: workspace})
	if err != nil {
		return model.QueryResult{}, nil, fmt.Errorf("load umodel snapshot: %w", err)
	}

	// Find DataLink: src.domain=entityDomain, src.name=entityType, dest.kind=plan.Kind
	dataLink, err := findDataLink(snapshot.Elements, entityDomain, entityType, plan.Kind)
	if err != nil {
		return model.QueryResult{}, nil, err
	}

	dataLinkSpec := specMap(dataLink.Spec)
	destSpec := mapValue(dataLinkSpec, "dest")
	destKind := stringFromMap(destSpec, "kind")
	destName := stringFromMap(destSpec, "name")
	fieldsMapping := stringMapValue(dataLinkSpec, "fields_mapping")

	// Resolve entity field value via fields_mapping.
	// The mapping is entity_field -> dataset_field.
	// We need to find the entity field name from the mapping and get its value.
	entityFieldName, serviceNameField := resolveServiceMapping(fieldsMapping)
	entityFieldValue := ""
	if entityFieldName != "" {
		entityFieldValue = stringValue(entity[entityFieldName])
	}
	if entityFieldValue == "" {
		return model.QueryResult{}, nil, apperrors.WithDetails(
			apperrors.CodeInvalidArgument,
			"evidence: entity field value is empty, cannot filter telemetry",
			map[string]string{"entity_field": entityFieldName, "entity_id": entityID},
		)
	}
	_ = serviceNameField // used in provider query below

	// Find StorageLink: src.kind=destKind, src.name=destName
	storageLink, err := findStorageLink(snapshot.Elements, destKind, destName)
	if err != nil {
		return model.QueryResult{}, nil, err
	}

	storageLinkSpec := specMap(storageLink.Spec)
	storageDestSpec := mapValue(storageLinkSpec, "dest")
	storageName := stringFromMap(storageDestSpec, "name")

	// Find Storage element
	storage, err := findStorage(snapshot.Elements, storageName)
	if err != nil {
		return model.QueryResult{}, nil, err
	}

	storageSpec := specMap(storage.Spec)
	storageType := stringFromMap(storageSpec, "type")
	storageProperties := stringMapValue(storageSpec, "properties")

	// Select provider
	provider, ok := e.providers[storageType]
	if !ok {
		return model.QueryResult{}, nil, apperrors.WithDetails(
			apperrors.CodeProviderUnsupported,
			"no telemetry provider registered for storage type",
			map[string]string{"storage_type": storageType},
		)
	}

	timeFrom := ""
	timeTo := ""
	if plan.From != nil {
		timeFrom = *plan.From
	}
	if plan.To != nil {
		timeTo = *plan.To
	}

	qr, err := provider.Query(ctx, telemetry.QueryRequest{
		Kind:              telemetry.Kind(plan.Kind),
		ServiceName:       entityFieldValue,
		TimeFrom:          timeFrom,
		TimeTo:            timeTo,
		Limit:             limit,
		StorageProperties: storageProperties,
	})
	if err != nil {
		return model.QueryResult{}, nil, err
	}

	evExplain := &model.EvidenceExplain{
		EntityID:         entityID,
		EntityType:       entityType,
		EntityFieldValue: entityFieldValue,
		DataLinkName:     dataLink.Name,
		DataSetKind:      destKind,
		DataSetName:      destName,
		StorageLinkName:  storageLink.Name,
		StorageName:      storageName,
		StorageType:      storageType,
		Provider:         provider.StorageType(),
		FieldsMapping:    fieldsMapping,
		TimeFrom:         timeFrom,
		TimeTo:           timeTo,
		ScannedFiles:     qr.ScannedFiles,
		ReturnedRows:     len(qr.Rows),
	}

	result := model.QueryResult{
		Columns: evidenceColumns(plan.Kind),
		Rows:    qr.Rows,
		Page:    model.PageRequest{Limit: limit},
	}

	return result, evExplain, nil
}

// resolveEvidenceExplain resolves the evidence chain (DataLink → DataSet →
// StorageLink → Storage → Provider) for a single entity without streaming any
// telemetry data. It is used by Explain() to return the full evidence chain.
// entityRows must contain exactly one row.
func (e *evidenceExecutor) resolveEvidenceExplain(
	ctx context.Context,
	workspace string,
	entityRows []map[string]any,
	op model.QueryPipelineOperator,
) (*model.EvidenceExplain, error) {
	plan := op.Evidence
	if plan == nil {
		return nil, apperrors.New(apperrors.CodeQueryPlanError, "evidence operator missing plan")
	}

	if len(entityRows) == 0 {
		return nil, apperrors.WithDetails(
			apperrors.CodeInvalidArgument, "evidence requires exactly one entity, got 0",
			map[string]string{"got": "0"},
		)
	}
	if len(entityRows) > 1 {
		return nil, apperrors.WithDetails(
			apperrors.CodeInvalidArgument, "evidence requires exactly one entity",
			map[string]string{"got": fmt.Sprint(len(entityRows))},
		)
	}

	entity := entityRows[0]
	entityID := stringValue(entity["__entity_id__"])
	entityType := stringValue(entity["__entity_type__"])
	entityDomain := stringValue(entity["__domain__"])

	snapshot, err := e.graph.GetUModelSnapshot(ctx, model.UModelSnapshotRequest{Workspace: workspace})
	if err != nil {
		return nil, fmt.Errorf("load umodel snapshot: %w", err)
	}

	dataLink, err := findDataLink(snapshot.Elements, entityDomain, entityType, plan.Kind)
	if err != nil {
		return nil, err
	}

	dataLinkSpec := specMap(dataLink.Spec)
	destSpec := mapValue(dataLinkSpec, "dest")
	destKind := stringFromMap(destSpec, "kind")
	destName := stringFromMap(destSpec, "name")
	fieldsMapping := stringMapValue(dataLinkSpec, "fields_mapping")

	entityFieldName, _ := resolveServiceMapping(fieldsMapping)
	entityFieldValue := ""
	if entityFieldName != "" {
		entityFieldValue = stringValue(entity[entityFieldName])
	}

	storageLink, err := findStorageLink(snapshot.Elements, destKind, destName)
	if err != nil {
		return nil, err
	}

	storageLinkSpec := specMap(storageLink.Spec)
	storageDestSpec := mapValue(storageLinkSpec, "dest")
	storageName := stringFromMap(storageDestSpec, "name")

	storage, err := findStorage(snapshot.Elements, storageName)
	if err != nil {
		return nil, err
	}

	storageSpec := specMap(storage.Spec)
	storageType := stringFromMap(storageSpec, "type")

	providerName := storageType // provider name equals storage type when registered
	if _, ok := e.providers[storageType]; !ok {
		providerName = "(unregistered: " + storageType + ")"
	}

	timeFrom, timeTo := "", ""
	if plan.From != nil {
		timeFrom = *plan.From
	}
	if plan.To != nil {
		timeTo = *plan.To
	}

	return &model.EvidenceExplain{
		EntityID:         entityID,
		EntityType:       entityType,
		EntityFieldValue: entityFieldValue,
		DataLinkName:     dataLink.Name,
		DataSetKind:      destKind,
		DataSetName:      destName,
		StorageLinkName:  storageLink.Name,
		StorageName:      storageName,
		StorageType:      storageType,
		Provider:         providerName,
		FieldsMapping:    fieldsMapping,
		TimeFrom:         timeFrom,
		TimeTo:           timeTo,
		// ScannedFiles and ReturnedRows are not populated for explain-only paths.
	}, nil
}

// evidenceColumns returns a default column set for a telemetry kind.
func evidenceColumns(kind string) []string {
	switch kind {
	case "metric_set":
		return []string{"serviceName", "name", "kind", "value", "time"}
	case "log_set":
		return []string{"serviceName", "time", "severityText", "body"}
	case "trace_set":
		return []string{"serviceName", "traceId", "spanId", "name", "startTime", "endTime"}
	default:
		return []string{"serviceName", "time"}
	}
}

// findDataLink locates the DataLink that connects an entity_set (by domain+name) to a
// DataSet of the requested kind.
func findDataLink(elements []model.UModelElement, entityDomain, entityType, datasetKind string) (model.UModelElement, error) {
	for _, el := range elements {
		if el.Kind != "data_link" {
			continue
		}
		spec := specMap(el.Spec)
		src := mapValue(spec, "src")
		dest := mapValue(spec, "dest")
		if stringFromMap(src, "domain") == entityDomain &&
			stringFromMap(src, "name") == entityType &&
			stringFromMap(dest, "kind") == datasetKind {
			return el, nil
		}
	}
	return model.UModelElement{}, apperrors.WithDetails(
		apperrors.CodeNotFound,
		"no DataLink found for entity type and dataset kind",
		map[string]string{"entity_domain": entityDomain, "entity_type": entityType, "dataset_kind": datasetKind},
	)
}

// findStorageLink locates the StorageLink that connects a DataSet (by kind+name) to a Storage.
func findStorageLink(elements []model.UModelElement, datasetKind, datasetName string) (model.UModelElement, error) {
	for _, el := range elements {
		if el.Kind != "storage_link" {
			continue
		}
		spec := specMap(el.Spec)
		src := mapValue(spec, "src")
		if stringFromMap(src, "kind") == datasetKind && stringFromMap(src, "name") == datasetName {
			return el, nil
		}
	}
	return model.UModelElement{}, apperrors.WithDetails(
		apperrors.CodeNotFound,
		"no StorageLink found for dataset",
		map[string]string{"dataset_kind": datasetKind, "dataset_name": datasetName},
	)
}

// findStorage locates a Storage element by name.
func findStorage(elements []model.UModelElement, storageName string) (model.UModelElement, error) {
	for _, el := range elements {
		switch el.Kind {
		case "external_storage", "sls_logstore", "sls_metricstore", "sls_entitystore", "aliyun_prometheus":
			if el.Name == storageName {
				return el, nil
			}
		}
	}
	return model.UModelElement{}, apperrors.WithDetails(
		apperrors.CodeNotFound,
		"no Storage element found",
		map[string]string{"name": storageName},
	)
}

// resolveServiceMapping extracts the entity field name and dataset field name
// from the DataLink fields_mapping that maps to "serviceName".
// Convention: the mapping key is the entity field, the value is the dataset field.
// We look for any mapping that points to "serviceName".
func resolveServiceMapping(fieldsMapping map[string]string) (entityField, datasetField string) {
	// Prefer explicit mapping to serviceName
	for k, v := range fieldsMapping {
		if v == "serviceName" {
			return k, v
		}
	}
	// Fallback: use first mapping
	for k, v := range fieldsMapping {
		return k, v
	}
	return "", ""
}

// specMap safely converts a UModelElement.Spec (map[string]any) nested field.
func specMap(spec map[string]any) map[string]any {
	if spec == nil {
		return map[string]any{}
	}
	return spec
}

func mapValue(m map[string]any, key string) map[string]any {
	if m == nil {
		return map[string]any{}
	}
	v, ok := m[key]
	if !ok {
		return map[string]any{}
	}
	switch typed := v.(type) {
	case map[string]any:
		return typed
	case map[any]any:
		out := make(map[string]any, len(typed))
		for k, val := range typed {
			out[fmt.Sprint(k)] = val
		}
		return out
	default:
		return map[string]any{}
	}
}

func stringFromMap(m map[string]any, key string) string {
	if m == nil {
		return ""
	}
	v, ok := m[key]
	if !ok {
		return ""
	}
	s, _ := v.(string)
	return s
}

func stringMapValue(m map[string]any, key string) map[string]string {
	v, ok := m[key]
	if !ok {
		return map[string]string{}
	}
	switch typed := v.(type) {
	case map[string]string:
		return typed
	case map[string]any:
		out := make(map[string]string, len(typed))
		for k, val := range typed {
			s, _ := val.(string)
			out[k] = s
		}
		return out
	case map[any]any:
		out := make(map[string]string, len(typed))
		for k, val := range typed {
			s, _ := val.(string)
			out[fmt.Sprint(k)] = s
		}
		return out
	default:
		return map[string]string{}
	}
}
