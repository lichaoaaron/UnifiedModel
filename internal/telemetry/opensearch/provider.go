package opensearch

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/alibaba/MModel/internal/telemetry"
	apperrors "github.com/alibaba/MModel/pkg/errors"
)

const storageType = "opensearch"

// Provider queries telemetry rows from OpenSearch _search API.
type Provider struct{}

func New() *Provider { return &Provider{} }

func (p *Provider) StorageType() string { return storageType }

func (p *Provider) Query(ctx context.Context, req telemetry.QueryRequest) (telemetry.QueryResult, error) {
	opts, err := resolveOptions(req)
	if err != nil {
		return telemetry.QueryResult{}, err
	}

	body := buildSearchBody(req, opts.serviceField, opts.timeField)
	rawBody, err := json.Marshal(body)
	if err != nil {
		return telemetry.QueryResult{}, apperrors.WithDetails(apperrors.CodeInternal, "marshal opensearch query", map[string]string{"error": err.Error()})
	}

	searchURL := strings.TrimRight(opts.endpoint, "/") + "/" + opts.indexName + "/_search"
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, searchURL, bytes.NewReader(rawBody))
	if err != nil {
		return telemetry.QueryResult{}, apperrors.WithDetails(apperrors.CodeInternal, "build opensearch request", map[string]string{"error": err.Error()})
	}
	httpReq.SetBasicAuth(opts.username, opts.password)
	httpReq.Header.Set("Content-Type", "application/json")
	for k, v := range opts.headers {
		httpReq.Header.Set(k, v)
	}

	client := &http.Client{
		Timeout: time.Duration(opts.requestTimeoutMs) * time.Millisecond,
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: !opts.verifyTLS}, //nolint:gosec
		},
	}

	resp, err := client.Do(httpReq)
	if err != nil {
		if isTimeoutError(err) || ctx.Err() == context.DeadlineExceeded {
			return telemetry.QueryResult{}, apperrors.WithDetails(apperrors.CodeTimeout, "opensearch request timeout", map[string]string{"endpoint": opts.safeEndpoint})
		}
		if ctx.Err() == context.Canceled {
			return telemetry.QueryResult{}, apperrors.New(apperrors.CodeTimeout, "evidence query cancelled")
		}
		return telemetry.QueryResult{}, apperrors.WithDetails(apperrors.CodeProviderUnavailable, "opensearch request failed", map[string]string{"endpoint": opts.safeEndpoint, "error": err.Error()})
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return telemetry.QueryResult{}, mapHTTPStatus(resp.StatusCode, opts.safeEndpoint, opts.indexName)
	}

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return telemetry.QueryResult{}, apperrors.WithDetails(apperrors.CodeInternal, "read opensearch response failed", map[string]string{"error": err.Error()})
	}

	var parsed struct {
		Hits struct {
			Hits []struct {
				Source map[string]any `json:"_source"`
			} `json:"hits"`
		} `json:"hits"`
	}
	if err := json.Unmarshal(data, &parsed); err != nil {
		return telemetry.QueryResult{}, apperrors.WithDetails(apperrors.CodeInternal, "parse opensearch response failed", map[string]string{"error": err.Error()})
	}

	rows := make([]map[string]any, 0, len(parsed.Hits.Hits))
	for _, h := range parsed.Hits.Hits {
		if h.Source != nil {
			rows = append(rows, h.Source)
		}
	}

	return telemetry.QueryResult{
		Rows:         rows,
		ScannedFiles: []string{fmt.Sprintf("%s/%s", strings.TrimRight(opts.safeEndpoint, "/"), opts.indexName)},
		Metadata: map[string]string{
			"endpoint":      opts.safeEndpoint,
			"index":         opts.indexName,
			"service_field": opts.serviceField,
			"time_field":    opts.timeField,
		},
	}, nil
}

func (p *Provider) ExplainMetadata(req telemetry.QueryRequest) (map[string]string, error) {
	opts, err := resolveOptions(req)
	if err != nil {
		return nil, err
	}
	return map[string]string{
		"endpoint":      opts.safeEndpoint,
		"index":         opts.indexName,
		"service_field": opts.serviceField,
		"time_field":    opts.timeField,
	}, nil
}

type options struct {
	endpoint         string
	safeEndpoint     string
	username         string
	password         string
	indexName        string
	timeField        string
	serviceField     string
	verifyTLS        bool
	requestTimeoutMs int
	headers          map[string]string
}

func resolveOptions(req telemetry.QueryRequest) (options, error) {
	props := req.StorageProperties
	endpoint := props["endpoint"]
	if strings.TrimSpace(endpoint) == "" {
		return options{}, apperrors.WithDetails(apperrors.CodeProviderUnavailable, "storage property missing", map[string]string{"key": "endpoint"})
	}
	safeEndpoint, err := sanitizeEndpoint(endpoint)
	if err != nil {
		return options{}, err
	}
	username := props["username"]
	if strings.TrimSpace(username) == "" {
		return options{}, apperrors.WithDetails(apperrors.CodeProviderUnavailable, "storage property missing", map[string]string{"key": "username"})
	}
	password := props["password"]
	if strings.TrimSpace(password) == "" {
		return options{}, apperrors.WithDetails(apperrors.CodeProviderUnavailable, "storage property missing", map[string]string{"key": "password"})
	}

	indexName, timeField, serviceField, err := resolveKindConfig(req)
	if err != nil {
		return options{}, err
	}
	timeoutMs, err := parseRequestTimeoutMs(props)
	if err != nil {
		return options{}, err
	}

	headers, err := parseHeadersJSON(props["headers_json"])
	if err != nil {
		return options{}, err
	}

	return options{
		endpoint:         strings.TrimRight(endpoint, "/"),
		safeEndpoint:     strings.TrimRight(safeEndpoint, "/"),
		username:         username,
		password:         password,
		indexName:        indexName,
		timeField:        timeField,
		serviceField:     serviceField,
		verifyTLS:        parseVerifyTLS(props),
		requestTimeoutMs: timeoutMs,
		headers:          headers,
	}, nil
}

func parseURL(raw string) (*url.URL, error) {
	u, err := url.Parse(raw)
	if err != nil {
		return nil, apperrors.WithDetails(apperrors.CodeInvalidArgument, "invalid opensearch endpoint", map[string]string{"endpoint": raw})
	}
	return u, nil
}

func parseHeadersJSON(raw string) (map[string]string, error) {
	if strings.TrimSpace(raw) == "" {
		return map[string]string{}, nil
	}
	var headers map[string]string
	if err := json.Unmarshal([]byte(raw), &headers); err != nil {
		return nil, apperrors.WithDetails(apperrors.CodeInvalidArgument, "invalid headers_json", map[string]string{"error": err.Error()})
	}
	return headers, nil
}

func isTimeoutError(err error) bool {
	netErr, ok := err.(interface{ Timeout() bool })
	return ok && netErr.Timeout()
}

func mapHTTPStatus(status int, endpoint, index string) error {
	details := map[string]string{"status": fmt.Sprint(status), "endpoint": endpoint, "index": index}
	switch status {
	case http.StatusUnauthorized, http.StatusForbidden:
		return apperrors.WithDetails(apperrors.CodeProviderUnavailable, "opensearch authentication failed", details)
	case http.StatusNotFound:
		return apperrors.WithDetails(apperrors.CodeNotFound, "opensearch index not found", details)
	case http.StatusRequestTimeout, http.StatusGatewayTimeout:
		return apperrors.WithDetails(apperrors.CodeTimeout, "opensearch request timeout", details)
	default:
		return apperrors.WithDetails(apperrors.CodeProviderUnavailable, "opensearch request failed", details)
	}
}
