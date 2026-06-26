package diagnosis

import (
	"context"
	"testing"

	"github.com/alibaba/MModel/internal/graphstore"
	"github.com/alibaba/MModel/internal/query"
	"github.com/alibaba/MModel/pkg/model"
)

// serviceIDs used across all tests – valid 32-char lowercase hex strings.
const (
	checkoutID = "10000000000000000000000000000101"
	paymentID  = "10000000000000000000000000000201"
	redisID    = "10000000000000000000000000000301"
	frontendID = "10000000000000000000000000000401"
)

// newTestStore builds a MemoryStore with a small service topology:
//
//	frontend --calls--> checkout --calls--> payment --calls--> redis
func newTestStore(t *testing.T) *graphstore.MemoryStore {
	t.Helper()
	ctx := context.Background()
	store := graphstore.NewMemoryStore()

	entities := model.EntityWriteBatch{
		Workspace: "test",
		Entities: []model.EntityPayload{
			{
				"__domain__":             "apm",
				"__entity_type__":        "apm.service",
				"__entity_id__":          checkoutID,
				"__category__":           "entity",
				"__method__":             "Update",
				"__first_observed_time__": int64(1),
				"__last_observed_time__":  int64(9999999999),
				"__keep_alive_seconds__": int64(3600),
				"display_name":           "checkout",
			},
			{
				"__domain__":             "apm",
				"__entity_type__":        "apm.service",
				"__entity_id__":          paymentID,
				"__category__":           "entity",
				"__method__":             "Update",
				"__first_observed_time__": int64(1),
				"__last_observed_time__":  int64(9999999999),
				"__keep_alive_seconds__": int64(3600),
				"display_name":           "payment",
			},
			{
				"__domain__":             "apm",
				"__entity_type__":        "apm.service",
				"__entity_id__":          redisID,
				"__category__":           "entity",
				"__method__":             "Update",
				"__first_observed_time__": int64(1),
				"__last_observed_time__":  int64(9999999999),
				"__keep_alive_seconds__": int64(3600),
				"display_name":           "redis",
			},
			{
				"__domain__":             "apm",
				"__entity_type__":        "apm.service",
				"__entity_id__":          frontendID,
				"__category__":           "entity",
				"__method__":             "Update",
				"__first_observed_time__": int64(1),
				"__last_observed_time__":  int64(9999999999),
				"__keep_alive_seconds__": int64(3600),
				"display_name":           "frontend",
			},
		},
	}
	if _, err := store.WriteEntities(ctx, entities); err != nil {
		t.Fatalf("write entities: %v", err)
	}

	relations := model.RelationWriteBatch{
		Workspace: "test",
		Relations: []model.RelationPayload{
			{
				"__src_domain__":      "apm",
				"__src_entity_type__": "apm.service",
				"__src_entity_id__":   frontendID,
				"__dest_domain__":     "apm",
				"__dest_entity_type__": "apm.service",
				"__dest_entity_id__":  checkoutID,
				"__relation_type__":   "calls",
				"__category__":        "entity_link",
				"__method__":          "Update",
				"__first_observed_time__": int64(1),
				"__last_observed_time__":  int64(9999999999),
				"__keep_alive_seconds__": int64(3600),
			},
			{
				"__src_domain__":      "apm",
				"__src_entity_type__": "apm.service",
				"__src_entity_id__":   checkoutID,
				"__dest_domain__":     "apm",
				"__dest_entity_type__": "apm.service",
				"__dest_entity_id__":  paymentID,
				"__relation_type__":   "calls",
				"__category__":        "entity_link",
				"__method__":          "Update",
				"__first_observed_time__": int64(1),
				"__last_observed_time__":  int64(9999999999),
				"__keep_alive_seconds__": int64(3600),
			},
			{
				"__src_domain__":      "apm",
				"__src_entity_type__": "apm.service",
				"__src_entity_id__":   paymentID,
				"__dest_domain__":     "apm",
				"__dest_entity_type__": "apm.service",
				"__dest_entity_id__":  redisID,
				"__relation_type__":   "calls",
				"__category__":        "entity_link",
				"__method__":          "Update",
				"__first_observed_time__": int64(1),
				"__last_observed_time__":  int64(9999999999),
				"__keep_alive_seconds__": int64(3600),
			},
		},
	}
	if _, err := store.WriteRelations(ctx, relations); err != nil {
		t.Fatalf("write relations: %v", err)
	}
	return store
}

func newTestBuilder(t *testing.T) *Builder {
	t.Helper()
	store := newTestStore(t)
	svc := query.NewService(store)
	return NewBuilder(svc)
}

// TestBuildFromEntryEntity verifies that Build returns a valid DCC map with
// the required top-level fields set.
func TestBuildFromEntryEntity(t *testing.T) {
	b := newTestBuilder(t)
	dcc, err := b.Build(context.Background(), "test", DCCBuildRequest{
		EntryEntityID: checkoutID,
		Symptom:       "latency spike",
		API:           "/checkout",
	})
	if err != nil {
		t.Fatalf("Build: %v", err)
	}
	if dcc["protocol_version"] != dccProtocolVersion {
		t.Errorf("protocol_version: got %v", dcc["protocol_version"])
	}
	if dcc["workspace"] != "test" {
		t.Errorf("workspace: got %v", dcc["workspace"])
	}
	alert, ok := dcc["alert"].(map[string]any)
	if !ok {
		t.Fatal("alert is not a map")
	}
	if alert["symptom"] != "latency spike" {
		t.Errorf("alert.symptom: got %v", alert["symptom"])
	}
	if alert["api"] != "/checkout" {
		t.Errorf("alert.api: got %v", alert["api"])
	}
	if dcc["context_id"] == "" {
		t.Error("context_id should not be empty")
	}
	if dcc["generated_at"] == "" {
		t.Error("generated_at should not be empty")
	}
}

// TestDCCSchemaValid checks that all required top-level sections are present.
func TestDCCSchemaValid(t *testing.T) {
	b := newTestBuilder(t)
	dcc, err := b.Build(context.Background(), "test", DCCBuildRequest{
		EntryEntityID: paymentID,
		Symptom:       "error rate",
	})
	if err != nil {
		t.Fatalf("Build: %v", err)
	}
	for _, key := range []string{
		"protocol_version", "context_id", "generated_at", "workspace",
		"alert", "objects", "evidence", "candidates", "provenance", "meta",
	} {
		if _, ok := dcc[key]; !ok {
			t.Errorf("missing required DCC field: %q", key)
		}
	}
	// evidence sub-fields
	evidence, _ := dcc["evidence"].(map[string]any)
	for _, sub := range []string{"trace", "log", "metric"} {
		ev, ok := evidence[sub].(map[string]any)
		if !ok {
			t.Errorf("evidence.%s missing or wrong type", sub)
			continue
		}
		if ev["availability"] != "unknown" {
			t.Errorf("evidence.%s.availability: got %v", sub, ev["availability"])
		}
	}
}

// TestRelatedEntitiesPopulated verifies that objects.entities includes neighbors.
func TestRelatedEntitiesPopulated(t *testing.T) {
	b := newTestBuilder(t)
	dcc, err := b.Build(context.Background(), "test", DCCBuildRequest{
		EntryEntityID:     checkoutID,
		EntryEntityDomain: "apm",
		EntryEntityType:   "apm.service",
		Symptom:           "error",
	})
	if err != nil {
		t.Fatalf("Build: %v", err)
	}
	objects, _ := dcc["objects"].(map[string]any)
	entities, ok := objects["entities"].([]map[string]any)
	if !ok || len(entities) < 2 {
		t.Errorf("objects.entities should have at least entry + one neighbor, got %v", objects["entities"])
	}
}

// TestTopologyEdgesPopulated verifies that objects.topology.edges is non-empty.
func TestTopologyEdgesPopulated(t *testing.T) {
	b := newTestBuilder(t)
	dcc, err := b.Build(context.Background(), "test", DCCBuildRequest{
		EntryEntityID:     checkoutID,
		EntryEntityDomain: "apm",
		EntryEntityType:   "apm.service",
		Symptom:           "error",
	})
	if err != nil {
		t.Fatalf("Build: %v", err)
	}
	objects, _ := dcc["objects"].(map[string]any)
	topo, _ := objects["topology"].(map[string]any)
	edges, ok := topo["edges"].([]map[string]any)
	if !ok || len(edges) == 0 {
		t.Errorf("objects.topology.edges should be non-empty, got %v", topo["edges"])
	}
}

// TestRootCauseCandidatesNonEmpty verifies root cause candidates are derived
// from outgoing dependencies (checkout → payment).
func TestRootCauseCandidatesNonEmpty(t *testing.T) {
	b := newTestBuilder(t)
	dcc, err := b.Build(context.Background(), "test", DCCBuildRequest{
		EntryEntityID:     checkoutID,
		EntryEntityDomain: "apm",
		EntryEntityType:   "apm.service",
		Symptom:           "latency spike",
	})
	if err != nil {
		t.Fatalf("Build: %v", err)
	}
	candidates, _ := dcc["candidates"].(map[string]any)
	rc, ok := candidates["root_cause"].([]map[string]any)
	if !ok || len(rc) == 0 {
		t.Errorf("candidates.root_cause should be non-empty; checkout calls payment, got %v", candidates["root_cause"])
	}
	// payment should be a root cause candidate for checkout
	found := false
	for _, c := range rc {
		if c["entity_id"] == paymentID {
			found = true
			if c["node_type"] != "root_cause_node" {
				t.Errorf("node_type: got %v", c["node_type"])
			}
			if c["candidate_source"] != "dependency_graph" {
				t.Errorf("candidate_source: got %v", c["candidate_source"])
			}
		}
	}
	if !found {
		t.Errorf("expected payment (%s) in root_cause candidates, got %v", paymentID, rc)
	}
}

// TestImpactScopeCandidatesNonEmpty verifies impact scope candidates are derived
// from incoming dependencies (frontend → checkout).
func TestImpactScopeCandidatesNonEmpty(t *testing.T) {
	b := newTestBuilder(t)
	dcc, err := b.Build(context.Background(), "test", DCCBuildRequest{
		EntryEntityID:     checkoutID,
		EntryEntityDomain: "apm",
		EntryEntityType:   "apm.service",
		Symptom:           "error",
	})
	if err != nil {
		t.Fatalf("Build: %v", err)
	}
	candidates, _ := dcc["candidates"].(map[string]any)
	is, ok := candidates["impact_scope"].([]map[string]any)
	if !ok || len(is) == 0 {
		t.Errorf("candidates.impact_scope should be non-empty; frontend calls checkout, got %v", candidates["impact_scope"])
	}
	// frontend should be in impact scope for checkout
	found := false
	for _, c := range is {
		if c["entity_id"] == frontendID {
			found = true
			if c["node_type"] != "directly_affected_node" {
				t.Errorf("node_type: got %v", c["node_type"])
			}
			if c["candidate_source"] != "topology_propagation" {
				t.Errorf("candidate_source: got %v", c["candidate_source"])
			}
		}
	}
	if !found {
		t.Errorf("expected frontend (%s) in impact_scope candidates, got %v", frontendID, is)
	}
}

// TestLeafNodeRootCauseEmpty verifies that redis (no outgoing calls) has empty
// root cause candidates.
func TestLeafNodeRootCauseEmpty(t *testing.T) {
	b := newTestBuilder(t)
	dcc, err := b.Build(context.Background(), "test", DCCBuildRequest{
		EntryEntityID:     redisID,
		EntryEntityDomain: "apm",
		EntryEntityType:   "apm.service",
		Symptom:           "oom",
	})
	if err != nil {
		t.Fatalf("Build: %v", err)
	}
	candidates, _ := dcc["candidates"].(map[string]any)
	rc, _ := candidates["root_cause"].([]map[string]any)
	if len(rc) != 0 {
		t.Errorf("redis has no outgoing calls, root_cause should be empty, got %v", rc)
	}
	// payment should be in impact scope of redis
	is, ok := candidates["impact_scope"].([]map[string]any)
	if !ok || len(is) == 0 {
		t.Errorf("payment calls redis; impact_scope should be non-empty, got %v", candidates["impact_scope"])
	}
}

// TestExistingQueryUnbroken verifies that the underlying QueryService still
// handles standard .entity and .topo queries correctly after adding the Builder.
func TestExistingQueryUnbroken(t *testing.T) {
	store := newTestStore(t)
	svc := query.NewService(store)

	ctx := context.Background()
	entityResult, err := svc.Execute(ctx, "test", model.QueryRequest{
		Query: ".entity | limit 10",
	})
	if err != nil {
		t.Fatalf("entity query: %v", err)
	}
	if len(entityResult.Rows) < 4 {
		t.Errorf("expected at least 4 entities, got %d", len(entityResult.Rows))
	}

	topoResult, err := svc.Execute(ctx, "test", model.QueryRequest{
		Query: ".topo | limit 10",
	})
	if err != nil {
		t.Fatalf("topo query: %v", err)
	}
	if len(topoResult.Rows) < 3 {
		t.Errorf("expected at least 3 relations, got %d", len(topoResult.Rows))
	}
}
