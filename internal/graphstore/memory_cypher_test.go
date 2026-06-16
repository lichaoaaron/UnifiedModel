package graphstore

import (
	"context"
	"testing"

	apperrors "github.com/alibaba/MModel/pkg/errors"
	"github.com/alibaba/MModel/pkg/model"
)

func TestMemoryCypherQueryTopoPath(t *testing.T) {
	store := NewMemoryStore()
	writeCypherRelationFixture(t, store)

	plan := model.TopoQueryPlan{
		Workspace: "demo",
		Limit:     20,
		GraphCall: &model.GraphCallPlan{
			Name:   "cypher",
			Cypher: "match (svc:`apm@apm.service` {__entity_id__: $svc}) optional match path = (svc)-[r*1..2]-(neighbor) with svc, neighbor, relationships(path) as rels where neighbor is null or coalesce(neighbor.__deleted__, false) = false return svc.__entity_id__ as service, neighbor.__entity_id__ as neighbor, [rel in rels | type(rel)] as relation_types, size(rels) as hops order by hops, neighbor limit 20",
		},
		Params: map[string]any{"svc": "54013ba69c196820e56801f1ef5aad54"},
	}
	result, err := store.QueryTopo(context.Background(), plan)
	if err != nil {
		t.Fatalf("query topo: %v", err)
	}
	if len(result.Rows) != 1 || result.Rows[0]["service"] != "54013ba69c196820e56801f1ef5aad54" || result.Rows[0]["neighbor"] != "177627f91af678a9b03e993f1a91917f" {
		t.Fatalf("unexpected rows: %+v", result.Rows)
	}
	if types, ok := result.Rows[0]["relation_types"].([]string); !ok || len(types) != 1 || types[0] != "calls" {
		t.Fatalf("unexpected relation types: %#v", result.Rows[0]["relation_types"])
	}
}

func TestMemoryCypherQueryReturnsFullProperties(t *testing.T) {
	store := NewMemoryStore()
	writeCypherRelationFixture(t, store)

	result, err := store.QueryTopo(context.Background(), model.TopoQueryPlan{
		Workspace: "demo",
		Limit:     10,
		GraphCall: &model.GraphCallPlan{
			Name:   "cypher",
			Cypher: "match (src:`apm@apm.service` {__entity_id__: $src})-[r:calls]->(dest) return properties(src) as src, properties(r) as relation, properties(dest) as dest",
		},
		Params: map[string]any{"src": "54013ba69c196820e56801f1ef5aad54"},
	})
	if err != nil {
		t.Fatalf("query topo properties: %v", err)
	}
	if len(result.Rows) != 1 {
		t.Fatalf("expected one property row, got %+v", result.Rows)
	}
	row := result.Rows[0]
	src, ok := row["src"].(map[string]any)
	if !ok || src["display_name"] != "cart service" || src["owner"] != "checkout-team" {
		t.Fatalf("unexpected source properties: %#v", row["src"])
	}
	relation, ok := row["relation"].(map[string]any)
	if !ok || relation["__relation_type__"] != "calls" || relation["latency_ms"] != int64(12) {
		t.Fatalf("unexpected relation properties: %#v", row["relation"])
	}
	dest, ok := row["dest"].(map[string]any)
	if !ok || dest["display_name"] != "checkout service" || dest["tier"] != "gold" {
		t.Fatalf("unexpected destination properties: %#v", row["dest"])
	}
}

func TestFileMemoryCypherQueryReturnsFullProperties(t *testing.T) {
	store, err := NewFileMemoryStore(ProviderConfig{DataRoot: t.TempDir()})
	if err != nil {
		t.Fatalf("new file memory store: %v", err)
	}
	writeCypherRelationFixture(t, store)

	result, err := store.QueryTopo(context.Background(), model.TopoQueryPlan{
		Workspace: "demo",
		Limit:     10,
		GraphCall: &model.GraphCallPlan{
			Name:   "cypher",
			Cypher: "match (src:`apm@apm.service` {__entity_id__: $src})-[r:calls]->(dest) return properties(src) as src, properties(r) as relation, properties(dest) as dest",
		},
		Params: map[string]any{"src": "54013ba69c196820e56801f1ef5aad54"},
	})
	if err != nil {
		t.Fatalf("query file memory topo properties: %v", err)
	}
	if len(result.Rows) != 1 {
		t.Fatalf("expected one property row, got %+v", result.Rows)
	}
	row := result.Rows[0]
	src, ok := row["src"].(map[string]any)
	if !ok || src["display_name"] != "cart service" || src["owner"] != "checkout-team" {
		t.Fatalf("unexpected source properties: %#v", row["src"])
	}
	relation, ok := row["relation"].(map[string]any)
	if !ok || relation["__relation_type__"] != "calls" || relation["latency_ms"] != int64(12) {
		t.Fatalf("unexpected relation properties: %#v", row["relation"])
	}
	dest, ok := row["dest"].(map[string]any)
	if !ok || dest["display_name"] != "checkout service" || dest["tier"] != "gold" {
		t.Fatalf("unexpected destination properties: %#v", row["dest"])
	}
}

func TestMemoryCypherRejectsReadableEntityID(t *testing.T) {
	store := NewMemoryStore()
	_, err := store.QueryTopo(context.Background(), model.TopoQueryPlan{
		Workspace: "demo",
		Limit:     10,
		GraphCall: &model.GraphCallPlan{Name: "cypher", Cypher: "MATCH (svc:`apm@apm.service` {__entity_id__: 'cart'}) RETURN svc"},
	})
	if !apperrors.IsCode(err, apperrors.CodeQueryPlanError) {
		t.Fatalf("expected non-hex entity id to be rejected, got %v", err)
	}
}

type cypherFixtureStore interface {
	WriteEntities(context.Context, model.EntityWriteBatch) (model.WriteResult, error)
	WriteRelations(context.Context, model.RelationWriteBatch) (model.WriteResult, error)
}

func writeCypherRelationFixture(t *testing.T, store cypherFixtureStore) {
	t.Helper()
	if _, err := store.WriteEntities(context.Background(), model.EntityWriteBatch{
		Workspace: "demo",
		Entities: []model.EntityPayload{
			{
				"__domain__":              "apm",
				"__entity_type__":         "apm.service",
				"__entity_id__":           "54013ba69c196820e56801f1ef5aad54",
				"__method__":              "Update",
				"__first_observed_time__": int64(100),
				"__last_observed_time__":  int64(200),
				"display_name":            "cart service",
				"owner":                   "checkout-team",
			},
			{
				"__domain__":              "apm",
				"__entity_type__":         "apm.service",
				"__entity_id__":           "177627f91af678a9b03e993f1a91917f",
				"__method__":              "Update",
				"__first_observed_time__": int64(100),
				"__last_observed_time__":  int64(200),
				"display_name":            "checkout service",
				"tier":                    "gold",
			},
		},
	}); err != nil {
		t.Fatalf("write entities: %v", err)
	}
	if _, err := store.WriteRelations(context.Background(), model.RelationWriteBatch{
		Workspace: "demo",
		Relations: []model.RelationPayload{{
			"__src_domain__":       "apm",
			"__src_entity_type__":  "apm.service",
			"__src_entity_id__":    "54013ba69c196820e56801f1ef5aad54",
			"__dest_domain__":      "apm",
			"__dest_entity_type__": "apm.service",
			"__dest_entity_id__":   "177627f91af678a9b03e993f1a91917f",
			"__relation_type__":    "calls",
			"__method__":           "Update",
			"latency_ms":           int64(12),
		}},
	}); err != nil {
		t.Fatalf("write relation: %v", err)
	}
}
