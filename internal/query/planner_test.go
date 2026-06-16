package query

import (
	"testing"

	apperrors "github.com/alibaba/MModel/pkg/errors"
	"github.com/alibaba/MModel/pkg/model"
)

const plannerCartNode = "(:\"apm@apm.service\" {__entity_id__: '54013ba69c196820e56801f1ef5aad54'})"

func TestPlannerRejectsLimitDepthAndUnsupportedCapabilities(t *testing.T) {
	caps := model.GraphStoreCapabilities{
		EntitySearch:       true,
		GraphMatch:         true,
		GraphCallNeighbors: true,
		MaxDepth:           2,
		MaxLimit:           10,
	}

	cases := []struct {
		name  string
		query string
		caps  model.GraphStoreCapabilities
		code  apperrors.Code
	}{
		{
			name:  "limit",
			query: ".entity with(domain='apm') | limit 11",
			caps:  caps,
			code:  apperrors.CodeValidationFailed,
		},
		{
			name:  "depth",
			query: ".topo | graph-call getNeighborNodes('full', 3, [" + plannerCartNode + "]) | limit 10",
			caps:  caps,
			code:  apperrors.CodeValidationFailed,
		},
		{
			name:  "graph-call capability",
			query: ".topo | graph-call getNeighborNodes('full', 2, [" + plannerCartNode + "]) | limit 10",
			caps:  model.GraphStoreCapabilities{GraphMatch: true, MaxDepth: 2, MaxLimit: 10},
			code:  apperrors.CodeProviderUnsupported,
		},
		{
			name:  "unknown graph-call",
			query: ".topo | graph-call nativeCall('both', 1, []) | limit 10",
			caps:  caps,
			code:  apperrors.CodeQueryPlanError,
		},
		{
			name:  "controlled cypher capability",
			query: ".topo | graph-call cypher(`MATCH (s) RETURN s`) | limit 10",
			caps:  caps,
			code:  apperrors.CodeProviderUnsupported,
		},
		{
			name:  "graph-match capability",
			query: ".topo | graph-match (s:\"apm@apm.service\" {__entity_id__: '54013ba69c196820e56801f1ef5aad54'})-[e]-(d) | limit 10",
			caps:  model.GraphStoreCapabilities{GraphCallNeighbors: true, MaxDepth: 2, MaxLimit: 10},
			code:  apperrors.CodeProviderUnsupported,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := (Planner{}).Plan(model.QueryRequest{Query: tc.query}, tc.caps)
			if !apperrors.IsCode(err, tc.code) {
				t.Fatalf("expected %s, got %v", tc.code, err)
			}
		})
	}
}

func TestExplainShowsTopoPushdowns(t *testing.T) {
	cypherPlan, err := (Planner{}).Plan(
		model.QueryRequest{Query: ".topo | graph-call cypher(`MATCH (s) RETURN s`) | limit 5"},
		model.GraphStoreCapabilities{ControlledCypher: true, MaxDepth: 2, MaxLimit: 10},
	)
	if err != nil {
		t.Fatalf("plan cypher: %v", err)
	}
	cypherExplain := buildExplain(cypherPlan, model.GraphStoreCapabilities{ControlledCypher: true, MaxDepth: 2, MaxLimit: 10}, model.GraphStoreHealth{Provider: "local.ladybug"})
	if !containsString(cypherExplain.Pushdown, "graph_call:cypher") || !containsString(cypherExplain.Pushdown, "controlled_cypher") {
		t.Fatalf("expected cypher pushdown: %+v", cypherExplain)
	}
	if cypherExplain.CypherDialect != "ladybug" || cypherExplain.CypherEngine != "go" {
		t.Fatalf("expected cypher explain metadata: %+v", cypherExplain)
	}

	matchPlan, err := (Planner{}).Plan(
		model.QueryRequest{Query: ".topo | graph-match (s:\"apm@apm.service\" {__entity_id__: '54013ba69c196820e56801f1ef5aad54'})-[e]-(d) | limit 5"},
		model.GraphStoreCapabilities{GraphMatch: true, MaxDepth: 2, MaxLimit: 10},
	)
	if err != nil {
		t.Fatalf("plan graph-match: %v", err)
	}
	matchExplain := buildExplain(matchPlan, model.GraphStoreCapabilities{GraphMatch: true, MaxDepth: 2, MaxLimit: 10}, model.GraphStoreHealth{Provider: "ladybug"})
	if !containsString(matchExplain.Pushdown, "graph_match") {
		t.Fatalf("expected graph_match pushdown: %+v", matchExplain)
	}
}

func TestExplainShowsCapabilityFallback(t *testing.T) {
	plan, err := (Planner{}).Plan(
		model.QueryRequest{Query: ".entity with(domain='apm', query='cart') | where __entity_id__ = '54013ba69c196820e56801f1ef5aad54' | project __entity_id__ | sort __entity_id__ | limit 5"},
		model.GraphStoreCapabilities{EntitySearch: true, MaxDepth: 2, MaxLimit: 10},
	)
	if err != nil {
		t.Fatalf("plan: %v", err)
	}
	explain := buildExplain(plan, model.GraphStoreCapabilities{EntitySearch: true, MaxDepth: 2, MaxLimit: 10}, model.GraphStoreHealth{Provider: "memory"})
	if explain.Source != ".entity" || explain.Provider != "memory" || explain.StorageProvider != "memory" {
		t.Fatalf("unexpected explain identity: %+v", explain)
	}
	if !containsString(explain.Pushdown, "entity_search") {
		t.Fatalf("expected entity_search pushdown: %+v", explain.Pushdown)
	}
	for _, fallback := range []string{"application_filter", "application_project", "application_sort"} {
		if !containsString(explain.Fallback, fallback) {
			t.Fatalf("expected fallback %q in %+v", fallback, explain.Fallback)
		}
	}
	if explain.Limit != 5 || !containsString(explain.Operators, "where") {
		t.Fatalf("unexpected explain plan fields: %+v", explain)
	}
}
