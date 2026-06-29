// Package otel implements topology ingestion from OpenTelemetry trace data.
// It discovers service-to-service call relationships from OpenSearch-stored
// spans and writes them into MModel's EntityStore with proper F/L/K/D
// lifecycle timestamps.
package otel

import (
	"bytes"
	"context"
	"crypto/md5"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/alibaba/MModel/pkg/model"
)

// Config holds the topology ingestor configuration.
type Config struct {
	// OpenSearch endpoint, e.g. "http://localhost:13121".
	OpenSearchEndpoint string
	// OpenSearch credentials.
	Username string
	Password string
	// Span index pattern, e.g. "otel-v1-apm-span-*".
	SpanIndex string
	// MModel workspace to write topology into.
	Workspace string
	// Domain for entities and relations.
	Domain string
	// Entity set name for discovered services.
	EntitySetName string
	// How often to scan for new topology (ingestion interval).
	ScanInterval time.Duration
	// Lookback window for each scan.
	LookbackWindow time.Duration
	// Keep-alive seconds for entities and relations.
	KeepAliveSeconds int64
	// Relation type for service-to-service calls.
	RelationType string
}

// DefaultConfig returns a configuration tuned for the OTel Demo on a local
// OpenSearch instance.
func DefaultConfig() Config {
	return Config{
		OpenSearchEndpoint: "http://localhost:13121",
		Username:           "admin",
		Password:           "MorenMima@123456",
		SpanIndex:          "otel-v1-apm-span-*",
		Workspace:          "otel-demo",
		Domain:             "otel",
		EntitySetName:      "otel.service",
		ScanInterval:       60 * time.Second,
		LookbackWindow:     5 * time.Minute,
		KeepAliveSeconds:   3600,
		RelationType:       "calls",
	}
}

// CallPair represents a discovered service-to-service call.
type CallPair struct {
	Caller string
	Callee string
}

// EntityWriter abstracts writing entities and relations into EntityStore.
type EntityWriter interface {
	WriteEntities(ctx context.Context, workspace string, batch model.EntityWriteBatch) (model.WriteResult, error)
	WriteRelations(ctx context.Context, workspace string, batch model.RelationWriteBatch) (model.WriteResult, error)
	// LookupEntityByName finds an existing entity by domain, entity set name,
	// and display_name (which maps to serviceName in telemetry).
	// Returns the entity ID and true if found.
	LookupEntityByName(ctx context.Context, workspace, domain, entitySet, displayName string) (entityID string, found bool, err error)
}

// Ingestor discovers topology from OpenSearch spans and writes it to EntityStore.
type Ingestor struct {
	cfg    Config
	store  EntityWriter
	client *http.Client
}

// NewIngestor creates a topology ingestor.
func NewIngestor(cfg Config, store EntityWriter) *Ingestor {
	return &Ingestor{
		cfg:    cfg,
		store:  store,
		client: &http.Client{Timeout: 30 * time.Second},
	}
}

// authHeader builds the Basic auth header value.
func (ing *Ingestor) authHeader() string {
	raw := ing.cfg.Username + ":" + ing.cfg.Password
	return "Basic " + base64.StdEncoding.EncodeToString([]byte(raw))
}

// openSearchRequest describes an OpenSearch search request body.
type openSearchRequest struct {
	Query struct {
		Bool struct {
			Must []any `json:"must"`
		} `json:"bool"`
	} `json:"query"`
	Size    int      `json:"size"`
	Source  []string `json:"_source"`
	Aggs    map[string]any `json:"aggs,omitempty"`
}

// openSearchResponse is a minimal OpenSearch search response.
type openSearchResponse struct {
	Hits struct {
		Total struct {
			Value int `json:"value"`
		} `json:"total"`
		Hits []openSearchHit `json:"hits"`
	} `json:"hits"`
	Aggregations map[string]struct {
		Buckets []struct {
			Key      string `json:"key"`
			DocCount int    `json:"doc_count"`
		} `json:"buckets"`
	} `json:"aggregations,omitempty"`
}

// DiscoverCallPairs queries OpenSearch for recent server spans grouped by
// serviceName, returning the set of active services. For service-to-service
// call discovery, we use the presence of server spans as evidence that a
// service is running.
func (ing *Ingestor) DiscoverCallPairs(ctx context.Context) ([]CallPair, []string, error) {
	// Discover active services by looking at span data.
	services, err := ing.discoverActiveServices(ctx)
	if err != nil {
		return nil, nil, fmt.Errorf("discover services: %w", err)
	}

	// Discover call pairs by analyzing parent-child span relationships.
	pairs, err := ing.discoverCallPairs(ctx)
	if err != nil {
		return nil, nil, fmt.Errorf("discover call pairs: %w", err)
	}

	return pairs, services, nil
}

// discoverActiveServices queries OpenSearch for distinct serviceName values
// in the recent lookback window.
func (ing *Ingestor) discoverActiveServices(ctx context.Context) ([]string, error) {
	from := time.Now().Add(-ing.cfg.LookbackWindow)

	reqBody := openSearchRequest{Size: 0}
	reqBody.Query.Bool.Must = []any{
		map[string]any{"range": map[string]any{
			"startTime": map[string]any{"gte": from.Format(time.RFC3339Nano)},
		}},
	}
	reqBody.Aggs = map[string]any{
		"services": map[string]any{
			"terms": map[string]any{
				"field": "serviceName",
				"size":  50,
			},
		},
	}

	resp, err := ing.search(ctx, reqBody)
	if err != nil {
		return nil, err
	}

	var services []string
	if resp.Aggregations != nil {
		if svcAgg, ok := resp.Aggregations["services"]; ok {
			for _, b := range svcAgg.Buckets {
				if b.Key != "" {
					services = append(services, b.Key)
				}
			}
		}
	}
	return services, nil
}

// discoverCallPairs discovers service-to-service calls by examining
// server spans (kind=SPAN_KIND_SERVER) where the parentSpanId is set —
// meaning the call originated from another service. We use the traceId
// and parentSpanId to find the caller, then group by (caller, callee).
func (ing *Ingestor) discoverCallPairs(ctx context.Context) ([]CallPair, error) {
	from := time.Now().Add(-ing.cfg.LookbackWindow)

	// Find server spans with parentSpanIds (i.e., called by another service).
	reqBody := openSearchRequest{Size: 200}
	reqBody.Query.Bool.Must = []any{
		map[string]any{"term": map[string]any{"kind": "SPAN_KIND_SERVER"}},
		map[string]any{"range": map[string]any{
			"startTime": map[string]any{"gte": from.Format(time.RFC3339Nano)},
		}},
	}
	reqBody.Query.Bool.Must = append(reqBody.Query.Bool.Must,
		map[string]any{"bool": map[string]any{
			"must_not": []any{
				map[string]any{"term": map[string]any{"parentSpanId": ""}},
			},
		}},
	)
	reqBody.Source = []string{"serviceName", "traceId", "parentSpanId", "resource.attributes.service@name", "resource.attributes.host@name"}

	resp, err := ing.search(ctx, reqBody)
	if err != nil {
		return nil, err
	}

	// For each server span, find the caller by looking up the parent span.
	seen := make(map[string]CallPair)
	for _, hit := range resp.Hits.Hits {
		callee := stringValue(hit.Source, "serviceName")
		traceID := stringValue(hit.Source, "traceId")
		parentID := stringValue(hit.Source, "parentSpanId")
		if callee == "" || traceID == "" || parentID == "" {
			continue
		}

		// Look up the parent span to find the caller.
		caller, err := ing.findCaller(ctx, traceID, parentID)
		if err != nil || caller == "" || caller == callee {
			continue
		}

		key := caller + "->" + callee
		if _, ok := seen[key]; !ok {
			seen[key] = CallPair{Caller: caller, Callee: callee}
		}
	}

	var pairs []CallPair
	for _, p := range seen {
		pairs = append(pairs, p)
	}
	return pairs, nil
}

// findCaller looks up a span by traceId+spanId and returns its serviceName.
func (ing *Ingestor) findCaller(ctx context.Context, traceID, spanID string) (string, error) {
	reqBody := openSearchRequest{Size: 1}
	reqBody.Query.Bool.Must = []any{
		map[string]any{"term": map[string]any{"traceId": traceID}},
		map[string]any{"term": map[string]any{"spanId": spanID}},
	}
	reqBody.Source = []string{"serviceName"}

	resp, err := ing.search(ctx, reqBody)
	if err != nil {
		return "", err
	}
	if len(resp.Hits.Hits) == 0 {
		return "", nil
	}
	return stringValue(resp.Hits.Hits[0].Source, "serviceName"), nil
}

// openSearchHit is a single hit from OpenSearch.
type openSearchHit struct {
	Source map[string]any `json:"_source"`
}

// search executes an OpenSearch search and returns parsed results.
func (ing *Ingestor) search(ctx context.Context, body openSearchRequest) (*openSearchResponse, error) {
	type flatReq struct {
		Query  any            `json:"query"`
		Size   int            `json:"size"`
		Source []string       `json:"_source,omitempty"`
		Aggs   map[string]any `json:"aggs,omitempty"`
	}
	b, err := json.Marshal(flatReq{
		Query:  body.Query,
		Size:   body.Size,
		Source: body.Source,
		Aggs:   body.Aggs,
	})
	if err != nil {
		return nil, fmt.Errorf("marshal: %w", err)
	}

	url := strings.TrimRight(ing.cfg.OpenSearchEndpoint, "/") + "/" + ing.cfg.SpanIndex + "/_search"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(b))
	if err != nil {
		return nil, fmt.Errorf("new request: %w", err)
	}
	req.Header.Set("Authorization", ing.authHeader())
	req.Header.Set("Content-Type", "application/json")

	resp, err := ing.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("opensearch request: %w", err)
	}
	defer resp.Body.Close()

	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read response: %w", err)
	}
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("opensearch error %d: %s", resp.StatusCode, string(bodyBytes))
	}

	var result openSearchResponse
	if err := json.Unmarshal(bodyBytes, &result); err != nil {
		return nil, fmt.Errorf("parse response: %w", err)
	}
	return &result, nil
}

// buildEntityPayload creates a CMS 2.0 entity payload for a service.
func buildEntityPayload(domain, entitySet, serviceName, entityID string, now int64) model.EntityPayload {
	return model.EntityPayload{
		"__domain__":              domain,
		"__entity_type__":         entitySet,
		"__entity_id__":           entityID,
		"__category__":            "entity",
		"__method__":              "Update",
		"__first_observed_time__": now,
		"__last_observed_time__":  now,
		"__keep_alive_seconds__":  3600,
		"id":                      entityID,
		"display_name":            serviceName,
		"status":                  "active",
	}
}

// buildRelationPayload creates a CMS 2.0 relation payload with a
// human-readable display_name.
func buildRelationPayload(domain, srcType, srcID, srcName, destType, destID, destName, relType string, now int64) model.RelationPayload {
	return model.RelationPayload{
		"__src_domain__":          domain,
		"__src_entity_type__":     srcType,
		"__src_entity_id__":       srcID,
		"__dest_domain__":         domain,
		"__dest_entity_type__":    destType,
		"__dest_entity_id__":      destID,
		"__relation_type__":       relType,
		"__category__":            "entity_link",
		"__method__":              "Update",
		"__first_observed_time__": now,
		"__last_observed_time__":  now,
		"__keep_alive_seconds__":  3600,
		"display_name":            srcName + " " + relType + " " + destName,
	}
}

// serviceEntityID generates a stable entity ID from a service name.
func serviceEntityID(serviceName string) string {
	h := md5.Sum([]byte(serviceName))
	return fmt.Sprintf("%x", h)
}

// Ingest performs one ingestion cycle: discovers topology, writes entities
// and relations to EntityStore. Existing entities are looked up by
// display_name and their IDs are reused to avoid duplicates.
func (ing *Ingestor) Ingest(ctx context.Context) (*IngestResult, error) {
	pairs, services, err := ing.DiscoverCallPairs(ctx)
	if err != nil {
		return nil, fmt.Errorf("discover: %w", err)
	}

	now := time.Now().Unix()
	result := &IngestResult{}

	// Build entity set: all distinct service names from pairs + active services.
	svcSet := make(map[string]bool)
	for _, s := range services {
		svcSet[s] = true
	}
	for _, p := range pairs {
		svcSet[p.Caller] = true
		svcSet[p.Callee] = true
	}

	// Resolve entity IDs: lookup existing by display_name, fallback to MD5.
	entityIDs := make(map[string]string, len(svcSet))
	reused := 0
	newIDs := 0
	for svc := range svcSet {
		eid, found, lookupErr := ing.store.LookupEntityByName(ctx, ing.cfg.Workspace, ing.cfg.Domain, ing.cfg.EntitySetName, svc)
		if lookupErr != nil {
			entityIDs[svc] = serviceEntityID(svc)
			newIDs++
			continue
		}
		if found {
			entityIDs[svc] = eid
			reused++
		} else {
			entityIDs[svc] = serviceEntityID(svc)
			newIDs++
		}
		result.Entities = append(result.Entities, svc)
	}

	// Write entities.
	if len(svcSet) > 0 {
		entities := make([]model.EntityPayload, 0, len(svcSet))
		for svc := range svcSet {
			eid := entityIDs[svc]
			entities = append(entities, buildEntityPayload(ing.cfg.Domain, ing.cfg.EntitySetName, svc, eid, now))
		}
		wr, err := ing.store.WriteEntities(ctx, ing.cfg.Workspace, model.EntityWriteBatch{
			Entities:       entities,
			PartialSuccess: true,
		})
		if err != nil {
			return result, fmt.Errorf("write entities: %w", err)
		}
		result.EntityWrite = wr
	}

	// Write relations.
	if len(pairs) > 0 {
		relations := make([]model.RelationPayload, 0, len(pairs))
		for _, p := range pairs {
			srcID := entityIDs[p.Caller]
			destID := entityIDs[p.Callee]
			relations = append(relations, buildRelationPayload(
				ing.cfg.Domain,
				ing.cfg.EntitySetName, srcID, p.Caller,
				ing.cfg.EntitySetName, destID, p.Callee,
				ing.cfg.RelationType, now,
			))
			result.Relations = append(result.Relations, p)
		}
		wr, err := ing.store.WriteRelations(ctx, ing.cfg.Workspace, model.RelationWriteBatch{
			Relations:      relations,
			PartialSuccess: true,
		})
		if err != nil {
			return result, fmt.Errorf("write relations: %w", err)
		}
		result.RelationWrite = wr
	}

	return result, nil
}

// IngestResult captures the outcome of one ingestion cycle.
type IngestResult struct {
	Entities      []string
	Relations     []CallPair
	EntityWrite   model.WriteResult
	RelationWrite model.WriteResult
}

// Summary returns a human-readable summary.
func (r *IngestResult) Summary() string {
	return fmt.Sprintf("entities=%d relations=%d accepted_e=%d accepted_r=%d",
		len(r.Entities), len(r.Relations),
		r.EntityWrite.Accepted, r.RelationWrite.Accepted,
	)
}

func stringValue(m map[string]any, key string) string {
	v, ok := m[key]
	if !ok {
		return ""
	}
	s, _ := v.(string)
	return s
}

func int64Value(m map[string]any, key string) int64 {
	v, ok := m[key]
	if !ok {
		return 0
	}
	switch n := v.(type) {
	case int64:
		return n
	case float64:
		return int64(n)
	}
	return 0
}
