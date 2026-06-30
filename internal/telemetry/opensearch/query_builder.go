package opensearch

import (
	"fmt"

	"github.com/alibaba/UnifiedModel/internal/telemetry"
	apperrors "github.com/alibaba/UnifiedModel/pkg/errors"
)

type kindConfig struct {
	indexKey            string
	timeFieldKey        string
	serviceFieldKey     string
	defaultTimeField    string
	defaultServiceField string
}

func configForKind(kind telemetry.Kind) (kindConfig, error) {
	switch kind {
	case telemetry.KindLogSet:
		return kindConfig{
			indexKey:            "log_index",
			timeFieldKey:        "time_field_log",
			serviceFieldKey:     "service_name_field_log",
			defaultTimeField:    "time",
			defaultServiceField: "serviceName",
		}, nil
	case telemetry.KindMetricSet:
		return kindConfig{
			indexKey:            "metric_index",
			timeFieldKey:        "time_field_metric",
			serviceFieldKey:     "service_name_field_metric",
			defaultTimeField:    "time",
			defaultServiceField: "serviceName",
		}, nil
	case telemetry.KindTraceSet:
		return kindConfig{
			indexKey:            "trace_index",
			timeFieldKey:        "time_field_trace",
			serviceFieldKey:     "service_name_field_trace",
			defaultTimeField:    "startTime",
			defaultServiceField: "serviceName",
		}, nil
	default:
		return kindConfig{}, apperrors.WithDetails(apperrors.CodeQueryPlanError, "unsupported evidence kind", map[string]string{"kind": string(kind)})
	}
}

func resolveKindConfig(req telemetry.QueryRequest) (indexName, timeField, serviceField string, err error) {
	cfg, err := configForKind(req.Kind)
	if err != nil {
		return "", "", "", err
	}

	indexName = req.StorageProperties[cfg.indexKey]
	if indexName == "" {
		return "", "", "", apperrors.WithDetails(apperrors.CodeProviderUnavailable, "storage property missing", map[string]string{"key": cfg.indexKey})
	}

	timeField = req.StorageProperties[cfg.timeFieldKey]
	if timeField == "" {
		timeField = cfg.defaultTimeField
	}

	serviceField = req.StorageProperties[cfg.serviceFieldKey]
	if serviceField == "" {
		serviceField = cfg.defaultServiceField
	}
	return indexName, timeField, serviceField, nil
}

func buildSearchBody(req telemetry.QueryRequest, serviceField, timeField string) map[string]any {
	limit := req.Limit
	if limit <= 0 {
		limit = 100
	}

	filters := []any{
		map[string]any{"term": map[string]any{serviceField: req.ServiceName}},
	}

	rangeSpec := map[string]any{}
	if req.TimeFrom != "" {
		rangeSpec["gte"] = req.TimeFrom
	}
	if req.TimeTo != "" {
		rangeSpec["lte"] = req.TimeTo
	}
	if len(rangeSpec) > 0 {
		filters = append(filters, map[string]any{"range": map[string]any{timeField: rangeSpec}})
	}

	return map[string]any{
		"size": limit,
		"query": map[string]any{
			"bool": map[string]any{
				"filter": filters,
			},
		},
		"sort": []any{
			map[string]any{timeField: map[string]any{"order": "asc"}},
			map[string]any{"_doc": map[string]any{"order": "asc"}},
		},
	}
}

func sanitizeEndpoint(raw string) (string, error) {
	u, err := parseURL(raw)
	if err != nil {
		return "", err
	}
	if u.Scheme == "" || u.Host == "" {
		return "", apperrors.WithDetails(apperrors.CodeInvalidArgument, "invalid opensearch endpoint", map[string]string{"endpoint": raw})
	}
	u.User = nil
	u.RawQuery = ""
	u.Fragment = ""
	return u.String(), nil
}

func parseRequestTimeoutMs(props map[string]string) (int, error) {
	v := props["request_timeout_ms"]
	if v == "" {
		return 10000, nil
	}
	var n int
	_, err := fmt.Sscanf(v, "%d", &n)
	if err != nil || n <= 0 {
		return 0, apperrors.WithDetails(apperrors.CodeInvalidArgument, "invalid request_timeout_ms", map[string]string{"value": v})
	}
	return n, nil
}

func parseVerifyTLS(props map[string]string) bool {
	v := props["verify_tls"]
	return !(v == "false" || v == "0")
}
