// Package diagnosis provides a minimal DiagnosisContextContract (DCC) builder
// that queries existing workspace entities and topology via QueryService and
// produces a DCC-v0.1 map consumable by MModel's DCC-first skills pipeline.
package diagnosis

import (
	"context"
	"crypto/rand"
	"fmt"
	"sort"
	"time"

	"github.com/alibaba/UnifiedModel/pkg/model"
)

const (
	dccProtocolVersion = "dcc-v0.1"
	defaultDepth       = 1
	defaultTopoLimit   = 50
)

// queryInterface is the minimal subset of query.Service used by the Builder.
type queryInterface interface {
	Execute(ctx context.Context, workspace string, req model.QueryRequest) (model.QueryResult, error)
}

// DCCBuildRequest holds the inputs needed to build a DiagnosisContextContract.
type DCCBuildRequest struct {
	// EntryEntityID is the canonical 32-char hex entity ID of the alerting entity.
	EntryEntityID string `json:"entry_entity_id"`
	// EntryEntityDomain and EntryEntityType are optional hints; resolved from
	// the entity store if omitted.
	EntryEntityDomain string `json:"entry_entity_domain,omitempty"`
	EntryEntityType   string `json:"entry_entity_type,omitempty"`
	// Symptom is a free-text description of the alert symptom (e.g. "latency spike").
	Symptom string `json:"symptom"`
	// API is the alert API identifier or endpoint name, if any.
	API string `json:"api,omitempty"`
	// TimeFrom / TimeTo scope the observation window.
	TimeFrom *time.Time `json:"time_from,omitempty"`
	TimeTo   *time.Time `json:"time_to,omitempty"`
	// Depth controls topology traversal depth (default 1).
	Depth int `json:"depth,omitempty"`
}

// Builder produces DCC-v0.1 maps from existing workspace entities and topology.
// It is intentionally thin: it delegates all data access to QueryService and
// derives candidates from topology structure alone, without running full diagnosis.
type Builder struct {
	query queryInterface
}

// NewBuilder creates a Builder backed by the given QueryService implementation.
func NewBuilder(q queryInterface) *Builder {
	return &Builder{query: q}
}

// Build queries entities and topology for the entry entity in the given workspace
// and returns a DCC-v0.1 map. Evidence fields are stubs (availability="unknown")
// because telemetry resolution is handled externally; candidates are derived from
// topology structure (outgoing edges → root cause, incoming edges → impact scope).
func (b *Builder) Build(ctx context.Context, workspace string, req DCCBuildRequest) (map[string]any, error) {
	depth := req.Depth
	if depth <= 0 {
		depth = defaultDepth
	}

	// Step 1: resolve entry entity from entity store.
	entry, err := b.resolveEntryEntity(ctx, workspace, req)
	if err != nil {
		return nil, err
	}

	domain := strVal(entry["__domain__"])
	entityType := strVal(entry["__entity_type__"])
	entityID := strVal(entry["__entity_id__"])
	displayName := strVal(entry["display_name"])
	if displayName == "" {
		displayName = entityID
	}

	// Step 2: query all direct relations involving the entry entity.
	relRows, err := b.queryNeighborRelations(ctx, workspace, entityID, domain, entityType, depth)
	if err != nil {
		return nil, err
	}

	// Step 3: build DCC object sections from entity + relation data.
	entitiesMap, relationsSlice, topoNodes, topoEdges := b.buildObjectSections(entry, relRows, entityID)

	// Step 4: derive topology-based candidates.
	rootCauseCandidates := inferRootCauseCandidates(entitiesMap, relRows, entityID)
	impactScopeCandidates := inferImpactScopeCandidates(entitiesMap, relRows, entityID)
	relatedEntities := buildRelatedEntities(entitiesMap, entityID)

	// Step 5: assemble the full DCC map.
	now := time.Now().UTC()
	alertTime := now.Format(time.RFC3339)
	if req.TimeFrom != nil {
		alertTime = req.TimeFrom.Format(time.RFC3339)
	}

	dcc := map[string]any{
		"protocol_version": dccProtocolVersion,
		"context_id":       newContextID(),
		"generated_at":     now.Format(time.RFC3339),
		"workspace":        workspace,
		"alert": map[string]any{
			"api":     req.API,
			"time":    alertTime,
			"symptom": req.Symptom,
		},
		"objects": map[string]any{
			"entities":  entitySlice(entitiesMap),
			"relations": relationsSlice,
			"topology": map[string]any{
				"nodes": topoNodes,
				"edges": topoEdges,
				"entry_points": []map[string]any{
					{"id": entityID, "display_name": displayName},
				},
			},
		},
		"related_entities": relatedEntities,
		"evidence": map[string]any{
			"trace":  map[string]any{"availability": "unknown", "spans": []any{}},
			"log":    map[string]any{"availability": "unknown", "entries": []any{}},
			"metric": map[string]any{"availability": "unknown", "series": []any{}},
		},
		"candidates": map[string]any{
			"root_cause":   rootCauseCandidates,
			"impact_scope": impactScopeCandidates,
		},
		"provenance": map[string]any{
			"builder":          "unifiedmodel/diagnosis.Builder",
			"entry_entity_id":  entityID,
			"topology_depth":   depth,
			"candidate_source": "topology_structure",
		},
		"meta": map[string]any{
			"topology_relation_count": len(relRows),
			"entity_count":            len(entitiesMap),
		},
	}
	return dcc, nil
}

// resolveEntryEntity fetches the entry entity from the entity store by ID.
// If not found, a minimal stub is returned so Build can proceed with topology.
func (b *Builder) resolveEntryEntity(ctx context.Context, workspace string, req DCCBuildRequest) (map[string]any, error) {
	q := fmt.Sprintf(".entity with(ids=['%s']) | limit 1", req.EntryEntityID)
	result, err := b.query.Execute(ctx, workspace, model.QueryRequest{Query: q})
	if err != nil {
		return nil, fmt.Errorf("resolve entry entity %q: %w", req.EntryEntityID, err)
	}
	for _, row := range result.Rows {
		if strVal(row["__entity_id__"]) == req.EntryEntityID {
			return row, nil
		}
	}
	if len(result.Rows) > 0 {
		return result.Rows[0], nil
	}
	// Entity not found; build a stub so topology traversal can still proceed.
	domain := req.EntryEntityDomain
	if domain == "" {
		domain = "unknown"
	}
	entityType := req.EntryEntityType
	if entityType == "" {
		entityType = "unknown"
	}
	return map[string]any{
		"__entity_id__":   req.EntryEntityID,
		"__domain__":      domain,
		"__entity_type__": entityType,
	}, nil
}

// queryNeighborRelations fetches all relations that directly involve entityID.
// It prefers getNeighborNodes (precise) when entityID is a valid 32-char hex string
// and domain/entityType are known; falls back to a full topo scan otherwise.
func (b *Builder) queryNeighborRelations(
	ctx context.Context, workspace, entityID, domain, entityType string, depth int,
) ([]map[string]any, error) {
	if model.IsEntityID(entityID) && domain != "unknown" && entityType != "unknown" {
		rows, err := b.queryViaGetNeighborNodes(ctx, workspace, entityID, domain, entityType, depth)
		if err == nil {
			return rows, nil
		}
		// Fall through to scan on any error (e.g. store does not support the call).
	}
	return b.queryTopoScanAndFilter(ctx, workspace, entityID)
}

// queryViaGetNeighborNodes uses the typed getNeighborNodes graph-call.
func (b *Builder) queryViaGetNeighborNodes(
	ctx context.Context, workspace, entityID, domain, entityType string, depth int,
) ([]map[string]any, error) {
	label := fmt.Sprintf(`%s@%s`, domain, entityType)
	nodeSelector := fmt.Sprintf(`(:"%s" {__entity_id__: '%s'})`, label, entityID)
	q := fmt.Sprintf(`.topo | graph-call getNeighborNodes('full', %d, [%s]) | limit %d`,
		depth, nodeSelector, defaultTopoLimit)
	result, err := b.query.Execute(ctx, workspace, model.QueryRequest{Query: q})
	if err != nil {
		return nil, err
	}
	return result.Rows, nil
}

// queryTopoScanAndFilter fetches up to 200 relations and filters by entity ID in Go.
// Used as a fallback when the precise getNeighborNodes call is not applicable.
func (b *Builder) queryTopoScanAndFilter(ctx context.Context, workspace, entityID string) ([]map[string]any, error) {
	result, err := b.query.Execute(ctx, workspace, model.QueryRequest{Query: ".topo | limit 200"})
	if err != nil {
		return nil, fmt.Errorf("query topology: %w", err)
	}
	var filtered []map[string]any
	for _, row := range result.Rows {
		if strVal(row["__src_entity_id__"]) == entityID || strVal(row["__dest_entity_id__"]) == entityID {
			filtered = append(filtered, row)
		}
	}
	return filtered, nil
}

// buildObjectSections builds the objects.entities, objects.relations,
// objects.topology.nodes, and objects.topology.edges sections of the DCC.
func (b *Builder) buildObjectSections(
	entry map[string]any,
	relRows []map[string]any,
	entryEntityID string,
) (
	entitiesMap map[string]map[string]any,
	relationsSlice []map[string]any,
	topoNodes []map[string]any,
	topoEdges []map[string]any,
) {
	entitiesMap = map[string]map[string]any{}

	// Seed with the entry entity.
	entryID := strVal(entry["__entity_id__"])
	if entryID != "" {
		entitiesMap[entryID] = entry
	}

	relationsSlice = []map[string]any{}
	topoEdges = []map[string]any{}

	for _, row := range relRows {
		srcID := strVal(row["__src_entity_id__"])
		destID := strVal(row["__dest_entity_id__"])
		relType := strVal(row["__relation_type__"])

		// Populate entity stubs for relation endpoints not yet seen.
		if srcID != "" {
			if _, ok := entitiesMap[srcID]; !ok {
				entitiesMap[srcID] = map[string]any{
					"__entity_id__":   srcID,
					"__entity_type__": strVal(row["__src_entity_type__"]),
					"__domain__":      strVal(row["__src_domain__"]),
					"display_name":    srcID,
				}
			}
		}
		if destID != "" {
			if _, ok := entitiesMap[destID]; !ok {
				entitiesMap[destID] = map[string]any{
					"__entity_id__":   destID,
					"__entity_type__": strVal(row["__dest_entity_type__"]),
					"__domain__":      strVal(row["__dest_domain__"]),
					"display_name":    destID,
				}
			}
		}

		relationsSlice = append(relationsSlice, map[string]any{
			"src":           srcID,
			"dest":          destID,
			"relation_type": relType,
		})
		topoEdges = append(topoEdges, map[string]any{
			"src":  srcID,
			"dest": destID,
			"type": relType,
		})
	}

	// Build sorted topology nodes for stable output.
	ids := sortedKeys(entitiesMap)
	topoNodes = make([]map[string]any, 0, len(ids))
	for _, id := range ids {
		e := entitiesMap[id]
		dn := strVal(e["display_name"])
		if dn == "" || dn == id {
			// Try to use a richer name field if present.
			if v := strVal(e["name"]); v != "" {
				dn = v
			}
		}
		topoNodes = append(topoNodes, map[string]any{
			"entity_id":    id,
			"entity_type":  strVal(e["__entity_type__"]),
			"domain":       strVal(e["__domain__"]),
			"display_name": dn,
			"is_entry":     id == entryEntityID,
		})
	}
	return
}

// inferRootCauseCandidates returns entities that the entry entity has outgoing
// dependencies to (entry → dest). A failure in dest would propagate to entry.
func inferRootCauseCandidates(
	entitiesMap map[string]map[string]any,
	relRows []map[string]any,
	entryEntityID string,
) []map[string]any {
	seen := map[string]bool{}
	var candidates []map[string]any
	for _, row := range relRows {
		srcID := strVal(row["__src_entity_id__"])
		destID := strVal(row["__dest_entity_id__"])
		if srcID == entryEntityID && destID != "" && !seen[destID] {
			seen[destID] = true
			dn, et := entityDisplayInfo(entitiesMap, destID)
			candidates = append(candidates, map[string]any{
				"entity_id":        destID,
				"entity_name":      dn,
				"entity_type":      et,
				"node_type":        "root_cause_node",
				"candidate_source": "dependency_graph",
				"confidence_level": "medium",
				"reason": fmt.Sprintf(
					"entry entity %s has outgoing %q dependency to %s",
					entryEntityID, strVal(row["__relation_type__"]), destID),
			})
		}
	}
	if candidates == nil {
		return []map[string]any{}
	}
	return candidates
}

// inferImpactScopeCandidates returns entities that have an incoming dependency
// on the entry entity (src → entry). A failure in entry propagates to these callers.
func inferImpactScopeCandidates(
	entitiesMap map[string]map[string]any,
	relRows []map[string]any,
	entryEntityID string,
) []map[string]any {
	seen := map[string]bool{}
	var candidates []map[string]any
	for _, row := range relRows {
		srcID := strVal(row["__src_entity_id__"])
		destID := strVal(row["__dest_entity_id__"])
		if destID == entryEntityID && srcID != "" && !seen[srcID] {
			seen[srcID] = true
			dn, et := entityDisplayInfo(entitiesMap, srcID)
			candidates = append(candidates, map[string]any{
				"entity_id":        srcID,
				"entity_name":      dn,
				"entity_type":      et,
				"node_type":        "directly_affected_node",
				"candidate_source": "topology_propagation",
				"confidence_level": "medium",
				"reason": fmt.Sprintf(
					"entity %s depends on entry entity %s via %q",
					srcID, entryEntityID, strVal(row["__relation_type__"])),
			})
		}
	}
	if candidates == nil {
		return []map[string]any{}
	}
	return candidates
}

// buildRelatedEntities returns a compact list of all entities in entitiesMap
// except the entry entity itself.
func buildRelatedEntities(entitiesMap map[string]map[string]any, entryEntityID string) []map[string]any {
	ids := sortedKeys(entitiesMap)
	result := make([]map[string]any, 0, len(ids))
	for _, id := range ids {
		if id == entryEntityID {
			continue
		}
		e := entitiesMap[id]
		dn := strVal(e["display_name"])
		if dn == "" || dn == id {
			if v := strVal(e["name"]); v != "" {
				dn = v
			}
		}
		result = append(result, map[string]any{
			"entity_id":    id,
			"entity_type":  strVal(e["__entity_type__"]),
			"domain":       strVal(e["__domain__"]),
			"display_name": dn,
		})
	}
	return result
}

// entitySlice returns a sorted slice of compact entity maps from entitiesMap.
func entitySlice(entitiesMap map[string]map[string]any) []map[string]any {
	ids := sortedKeys(entitiesMap)
	result := make([]map[string]any, 0, len(ids))
	for _, id := range ids {
		e := entitiesMap[id]
		dn := strVal(e["display_name"])
		if dn == "" || dn == id {
			if v := strVal(e["name"]); v != "" {
				dn = v
			}
		}
		result = append(result, map[string]any{
			"entity_id":    id,
			"entity_type":  strVal(e["__entity_type__"]),
			"domain":       strVal(e["__domain__"]),
			"display_name": dn,
		})
	}
	return result
}

// entityDisplayInfo looks up display_name and entity_type for an entity ID.
func entityDisplayInfo(entitiesMap map[string]map[string]any, id string) (displayName, entityType string) {
	if e, ok := entitiesMap[id]; ok {
		displayName = strVal(e["display_name"])
		if displayName == "" || displayName == id {
			if v := strVal(e["name"]); v != "" {
				displayName = v
			}
		}
		entityType = strVal(e["__entity_type__"])
	}
	if displayName == "" {
		displayName = id
	}
	return
}

// sortedKeys returns map keys in sorted order for deterministic output.
func sortedKeys(m map[string]map[string]any) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

// strVal coerces an any value to string; returns "" for nil or non-string.
func strVal(v any) string {
	if v == nil {
		return ""
	}
	s, _ := v.(string)
	return s
}

// newContextID generates a random 32-char hex context ID.
func newContextID() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	return fmt.Sprintf("%x", b)
}
