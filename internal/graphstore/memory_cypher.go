package graphstore

import (
	"sort"

	"github.com/alibaba/MModel/internal/cypher"
	"github.com/alibaba/MModel/pkg/model"
)

func (s *MemoryStore) queryCypherLocked(plan model.TopoQueryPlan, limit int) (model.QueryResult, error) {
	result, err := cypher.Execute(plan.GraphCall.Cypher, s.cypherGraphLocked(plan), plan.Params, cypher.Options{Limit: limit})
	if err != nil {
		return model.QueryResult{}, err
	}
	return model.QueryResult{
		Columns: result.Columns,
		Rows:    result.Rows,
		Page:    model.PageRequest{Limit: result.Limit},
	}, nil
}

func (s *MemoryStore) cypherGraphLocked(plan model.TopoQueryPlan) cypher.Graph {
	nodes := map[string]cypher.Node{}
	entityKeys := sortedMapKeys(s.entities[plan.Workspace])
	for _, key := range entityKeys {
		payload := s.entities[plan.Workspace][key]
		if !entityMatches(payload, plan) {
			continue
		}
		nodes[key] = cypher.Node{
			ID:         key,
			Labels:     entityLabels(payload),
			Properties: cloneMap(map[string]any(payload)),
		}
	}

	edges := []cypher.Edge{}
	relationKeys := sortedMapKeys(s.relations[plan.Workspace])
	for _, key := range relationKeys {
		payload := s.relations[plan.Workspace][key]
		if !relationMatches(payload, plan) {
			continue
		}
		src := relationEndpoint(payload, "src")
		dest := relationEndpoint(payload, "dest")
		if _, ok := nodes[src]; !ok {
			nodePayload := entityPayloadFromRelation(payload, "src")
			nodes[src] = cypher.Node{ID: src, Labels: entityLabels(nodePayload), Properties: cloneMap(map[string]any(nodePayload))}
		}
		if _, ok := nodes[dest]; !ok {
			nodePayload := entityPayloadFromRelation(payload, "dest")
			nodes[dest] = cypher.Node{ID: dest, Labels: entityLabels(nodePayload), Properties: cloneMap(map[string]any(nodePayload))}
		}
		edgePayload := cloneMap(map[string]any(payload))
		edges = append(edges, cypher.Edge{
			ID:         key,
			From:       src,
			To:         dest,
			Type:       stringValue(payload["__relation_type__"]),
			Properties: edgePayload,
		})
	}
	return cypher.Graph{Nodes: nodes, Edges: edges}
}

func entityLabels(payload model.EntityPayload) []string {
	domain := stringValue(payload["__domain__"])
	entityType := stringValue(payload["__entity_type__"])
	labels := []string{}
	if entityType != "" {
		labels = append(labels, entityType)
	}
	if domain != "" && entityType != "" {
		labels = append(labels, domain+"@"+entityType)
	}
	return labels
}

func entityPayloadFromRelation(payload model.RelationPayload, side string) model.EntityPayload {
	return model.EntityPayload{
		"__domain__":      payload["__"+side+"_domain__"],
		"__entity_type__": payload["__"+side+"_entity_type__"],
		"__entity_id__":   payload["__"+side+"_entity_id__"],
		"__method__":      methodOf(map[string]any(payload)),
		"__deleted__":     false,
	}
}

func sortedMapKeys[T any](values map[string]T) []string {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}
