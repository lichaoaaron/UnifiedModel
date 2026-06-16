package cypher

import (
	"testing"

	apperrors "github.com/alibaba/MModel/pkg/errors"
)

const (
	cartID     = "54013ba69c196820e56801f1ef5aad54"
	checkoutID = "177627f91af678a9b03e993f1a91917f"
	paymentID  = "2b5c1f4e7a6d8b9c0e1f23456789abcd"
)

func TestExecuteComplexOptionalPath(t *testing.T) {
	result, err := Execute(
		"match (svc:`apm@apm.service` {__entity_id__: $svc}) optional match path = (svc)-[:calls*1..2]-(neighbor) with svc, neighbor, relationships(path) as rels where neighbor is null or coalesce(neighbor.__deleted__, false) = false return svc.__entity_id__ as service, neighbor.__entity_id__ as neighbor, [rel in rels | type(rel)] as relation_types, size(rels) as hops order by hops, neighbor limit 20",
		testGraph(),
		map[string]any{"svc": cartID},
		Options{Limit: 20},
	)
	if err != nil {
		t.Fatalf("execute complex path: %v", err)
	}
	if len(result.Rows) != 2 {
		t.Fatalf("expected two path rows, got %+v", result.Rows)
	}
	if result.Rows[0]["service"] != cartID || result.Rows[0]["neighbor"] != checkoutID || result.Rows[0]["hops"] != 1 {
		t.Fatalf("unexpected first path row: %+v", result.Rows[0])
	}
	if types, ok := result.Rows[0]["relation_types"].([]string); !ok || len(types) != 1 || types[0] != "calls" {
		t.Fatalf("unexpected relation type list: %#v", result.Rows[0]["relation_types"])
	}
	if result.Rows[1]["neighbor"] != paymentID || result.Rows[1]["hops"] != 2 {
		t.Fatalf("unexpected second path row: %+v", result.Rows[1])
	}
}

func TestExecuteUnwindDistinctAndUnion(t *testing.T) {
	result, err := Execute(
		"with [1, 2, 2] as values unwind values as v return distinct v order by v desc limit 2 union match (n:`apm@apm.service` {__entity_id__: $svc}) return n.__entity_id__ as v",
		testGraph(),
		map[string]any{"svc": cartID},
		Options{Limit: 20},
	)
	if err != nil {
		t.Fatalf("execute unwind/union: %v", err)
	}
	if len(result.Rows) != 3 {
		t.Fatalf("expected union rows, got %+v", result.Rows)
	}
	if result.Rows[0]["v"] != int64(2) || result.Rows[1]["v"] != int64(1) || result.Rows[2]["v"] != cartID {
		t.Fatalf("unexpected union rows: %+v", result.Rows)
	}
}

func TestExecuteAggregation(t *testing.T) {
	result, err := Execute(
		"match (svc:`apm@apm.service`)-[r:calls]->(neighbor) with svc.__entity_id__ as service, type(r) as relation return service, count(relation) as relation_count, collect(relation) as relation_types order by service",
		testGraph(),
		nil,
		Options{Limit: 20},
	)
	if err != nil {
		t.Fatalf("execute aggregate: %v", err)
	}
	if len(result.Rows) != 2 {
		t.Fatalf("expected grouped rows, got %+v", result.Rows)
	}
	counts := map[any]any{}
	for _, row := range result.Rows {
		counts[row["service"]] = row["relation_count"]
	}
	if counts[cartID] != 1 || counts[checkoutID] != 1 {
		t.Fatalf("unexpected aggregate rows: %+v", result.Rows)
	}
}

func TestExecutePropertiesCoversNodeAndEdgeAttributes(t *testing.T) {
	result, err := Execute(
		"match (src:`apm@apm.service` {__entity_id__: $src})-[r:calls]->(dest) return properties(src) as src, properties(r) as relation, properties(dest) as dest, labels(src) as src_labels, id(r) as relation_id",
		testGraph(),
		map[string]any{"src": cartID},
		Options{Limit: 20},
	)
	if err != nil {
		t.Fatalf("execute property query: %v", err)
	}
	if len(result.Rows) != 1 {
		t.Fatalf("expected one property row, got %+v", result.Rows)
	}
	row := result.Rows[0]
	src, ok := row["src"].(map[string]any)
	if !ok || src["__entity_id__"] != cartID || src["display_name"] != "cart" {
		t.Fatalf("unexpected source properties: %#v", row["src"])
	}
	relation, ok := row["relation"].(map[string]any)
	if !ok || relation["__relation_type__"] != "calls" || relation["latency_ms"] != 12 {
		t.Fatalf("unexpected relation properties: %#v", row["relation"])
	}
	dest, ok := row["dest"].(map[string]any)
	if !ok || dest["__entity_id__"] != checkoutID || dest["display_name"] != "checkout" {
		t.Fatalf("unexpected destination properties: %#v", row["dest"])
	}
	labels, ok := row["src_labels"].([]string)
	if !ok || len(labels) != 2 || labels[0] != "apm.service" || labels[1] != "apm@apm.service" {
		t.Fatalf("unexpected source labels: %#v", row["src_labels"])
	}
	if row["relation_id"] != "cart-calls-checkout" {
		t.Fatalf("unexpected relation id: %#v", row["relation_id"])
	}
}

func TestValidateReadOnlyCypher(t *testing.T) {
	if err := ValidateReadOnly("MATCH (n) SET n.name = 'bad' RETURN n"); !apperrors.IsCode(err, apperrors.CodeQueryPlanError) {
		t.Fatalf("expected mutation rejection, got %v", err)
	}
	if err := ValidateReadOnly("MATCH (n {__entity_id__: 'cart'}) RETURN n"); !apperrors.IsCode(err, apperrors.CodeQueryPlanError) {
		t.Fatalf("expected entity id rejection, got %v", err)
	}
	if _, err := Execute("MATCH (n {__entity_id__: $id}) RETURN n", testGraph(), map[string]any{"id": "cart"}, Options{}); !apperrors.IsCode(err, apperrors.CodeQueryPlanError) {
		t.Fatalf("expected parameter entity id rejection, got %v", err)
	}
	if _, err := Execute("MATCH (n {__entity_id__: $missing}) RETURN n", testGraph(), nil, Options{}); !apperrors.IsCode(err, apperrors.CodeQueryPlanError) {
		t.Fatalf("expected missing parameter rejection, got %v", err)
	}
}

func testGraph() Graph {
	return Graph{
		Nodes: map[string]Node{
			"apm/apm.service/" + cartID: {
				ID:     "apm/apm.service/" + cartID,
				Labels: []string{"apm.service", "apm@apm.service"},
				Properties: map[string]any{
					"__domain__":      "apm",
					"__entity_type__": "apm.service",
					"__entity_id__":   cartID,
					"__deleted__":     false,
					"display_name":    "cart",
				},
			},
			"apm/apm.service/" + checkoutID: {
				ID:     "apm/apm.service/" + checkoutID,
				Labels: []string{"apm.service", "apm@apm.service"},
				Properties: map[string]any{
					"__domain__":      "apm",
					"__entity_type__": "apm.service",
					"__entity_id__":   checkoutID,
					"__deleted__":     false,
					"display_name":    "checkout",
				},
			},
			"apm/apm.service/" + paymentID: {
				ID:     "apm/apm.service/" + paymentID,
				Labels: []string{"apm.service", "apm@apm.service"},
				Properties: map[string]any{
					"__domain__":      "apm",
					"__entity_type__": "apm.service",
					"__entity_id__":   paymentID,
					"__deleted__":     false,
					"display_name":    "payment",
				},
			},
		},
		Edges: []Edge{
			{
				ID:   "cart-calls-checkout",
				From: "apm/apm.service/" + cartID,
				To:   "apm/apm.service/" + checkoutID,
				Type: "calls",
				Properties: map[string]any{
					"__relation_type__": "calls",
					"latency_ms":        12,
				},
			},
			{
				ID:   "checkout-calls-payment",
				From: "apm/apm.service/" + checkoutID,
				To:   "apm/apm.service/" + paymentID,
				Type: "calls",
				Properties: map[string]any{
					"__relation_type__": "calls",
					"latency_ms":        18,
				},
			},
		},
	}
}
