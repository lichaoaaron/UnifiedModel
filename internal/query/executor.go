package query

import (
	"context"
	"fmt"
	"sort"
	"strconv"
	"strings"

	"github.com/alibaba/UnifiedModel/internal/telemetry"
	apperrors "github.com/alibaba/UnifiedModel/pkg/errors"
	"github.com/alibaba/UnifiedModel/pkg/model"
)

type Executor struct {
	graph     graphStore
	evidence  *evidenceExecutor
}

func NewExecutor(graph graphStore, providers []telemetry.Provider) *Executor {
	return &Executor{
		graph:    graph,
		evidence: newEvidenceExecutor(graph, providers),
	}
}

func (e *Executor) Execute(ctx context.Context, workspace string, plan model.QueryPlan) (model.QueryResult, error) {
	plan.Workspace = workspace

	// Check if this is an evidence query (.entity | evidence(...))
	if plan.Source == ".entity" {
		if evOp, ok := findEvidenceOperator(plan.Pipeline); ok {
			return e.executeEntityEvidence(ctx, workspace, plan, evOp)
		}
	}

	var result model.QueryResult
	var err error
	switch plan.Source {
	case ".umodel":
		result, err = e.executeUModel(ctx, workspace, plan)
	case ".entity":
		result, err = e.graph.QueryEntities(ctx, model.EntityQueryPlan(plan))
	case ".topo":
		result, err = e.graph.QueryTopo(ctx, model.TopoQueryPlan(plan))
	default:
		return model.QueryResult{}, apperrors.New(apperrors.CodeQueryPlanError, "unsupported query source")
	}
	if err != nil {
		return model.QueryResult{}, err
	}

	rows, columns := applyPipeline(plan.Source, result.Rows, result.Columns, plan)
	result.Rows = rows
	result.Columns = columns
	result.Page = model.PageRequest{Limit: plan.Limit}
	return result, nil
}

// executeEntityEvidence runs the entity portion of the plan, then executes evidence().
// Post-evidence operators (project, sort, limit) are applied to the telemetry rows
// AFTER evidence returns, so entity context fields are never stripped before evidence.
func (e *Executor) executeEntityEvidence(ctx context.Context, workspace string, plan model.QueryPlan, evOp model.QueryPipelineOperator) (model.QueryResult, error) {
	// Build a plan without the evidence operator for the entity query.
	// Also strip post-evidence operators (project, sort, limit) so they don't affect
	// entity retrieval.
	entityPlan := entityPlanForEvidence(plan)
	entityResult, err := e.graph.QueryEntities(ctx, model.EntityQueryPlan(entityPlan))
	if err != nil {
		return model.QueryResult{}, err
	}

	// Only apply with/where to filter entities. Never apply project/sort here,
	// because that would strip __domain__, __entity_type__, display_name, etc.
	entityRows := filterEntityRowsForEvidence(entityResult.Rows, plan)

	result, evExplain, err := e.evidence.executeEvidence(ctx, workspace, entityRows, evOp, plan.Limit)
	if err != nil {
		return model.QueryResult{}, err
	}

	// Apply post-evidence operators (project, sort, limit) to the telemetry rows.
	result.Rows, result.Columns = applyPostEvidencePipeline(result.Rows, result.Columns, plan)

	// Attach evidence explain to the result for the service to pick up.
	if evExplain != nil {
		if result.Explain == nil {
			result.Explain = &model.QueryExplain{}
		}
		result.Explain.Evidence = evExplain
	}

	return result, nil
}

// findEvidenceOperator returns the evidence operator from a pipeline, if present.
func findEvidenceOperator(pipeline []model.QueryPipelineOperator) (model.QueryPipelineOperator, bool) {
	for _, op := range pipeline {
		if op.Name == "evidence" {
			return op, true
		}
	}
	return model.QueryPipelineOperator{}, false
}

// resolveEvidenceExplainForPlan is the explain-path entry point. It runs the entity
// query (without streaming telemetry) and resolves the full evidence chain, returning
// an EvidenceExplain for inclusion in explain output. Errors are treated as soft
// failures by the caller.
func (e *Executor) resolveEvidenceExplainForPlan(
	ctx context.Context,
	workspace string,
	plan model.QueryPlan,
	evOp model.QueryPipelineOperator,
) (*model.EvidenceExplain, error) {
	entityPlan := entityPlanForEvidence(plan)
	entityResult, err := e.graph.QueryEntities(ctx, model.EntityQueryPlan(entityPlan))
	if err != nil {
		return nil, err
	}
	entityRows := filterEntityRowsForEvidence(entityResult.Rows, plan)
	return e.evidence.resolveEvidenceExplain(ctx, workspace, entityRows, evOp)
}

// entityPlanForEvidence builds the plan used for the pre-evidence entity query.
// It removes the evidence operator and all post-evidence operators (project, sort,
// limit) so they do not affect entity retrieval or strip required entity fields.
func entityPlanForEvidence(plan model.QueryPlan) model.QueryPlan {
	p := plan
	pipeline := make([]model.QueryPipelineOperator, 0, len(plan.Pipeline))
	operators := make([]string, 0, len(plan.Operators))

	// Include only with/where operators that appear before the evidence operator.
	seenEvidence := false
	for i, op := range plan.Pipeline {
		if op.Name == "evidence" {
			seenEvidence = true
			continue
		}
		if seenEvidence {
			// Operators after evidence are post-evidence; skip them for entity retrieval.
			continue
		}
		if op.Name == "project" || op.Name == "sort" || op.Name == "limit" {
			// project/sort/limit before evidence would strip entity fields; skip.
			continue
		}
		pipeline = append(pipeline, op)
		if i < len(plan.Operators) {
			operators = append(operators, plan.Operators[i])
		}
	}
	p.Pipeline = pipeline
	p.Operators = operators
	// Use a generous limit for entity retrieval so we can validate count.
	p.Limit = 100
	return p
}

// filterEntityRowsForEvidence applies only with/where filters to entity rows.
// project/sort are intentionally excluded to preserve all entity fields for evidence.
func filterEntityRowsForEvidence(rows []map[string]any, plan model.QueryPlan) []map[string]any {
	if !hasOperator(plan.Pipeline, "with") && len(plan.Filters) > 0 {
		rows = filterRows(plan.Source, rows, plan.Filters)
	}
	for _, operator := range plan.Pipeline {
		if operator.Name == "evidence" {
			break // stop at evidence; everything after is post-evidence
		}
		switch operator.Name {
		case "with":
			rows = filterRows(plan.Source, rows, plan.Filters)
		case "where":
			if operator.Predicate != nil {
				rows = filterPredicate(rows, *operator.Predicate)
			}
		// project/sort/limit intentionally skipped — they must not touch entity rows
		}
	}
	return rows
}

// applyPostEvidencePipeline applies project/sort/limit operators that appear after
// the evidence operator in the pipeline, to the telemetry rows returned by evidence.
func applyPostEvidencePipeline(rows []map[string]any, columns []string, plan model.QueryPlan) ([]map[string]any, []string) {
	seenEvidence := false
	for _, operator := range plan.Pipeline {
		if operator.Name == "evidence" {
			seenEvidence = true
			continue
		}
		if !seenEvidence {
			continue
		}
		switch operator.Name {
		case "project":
			rows, columns = projectRows(rows, operator.Project)
		case "sort":
			if operator.Sort != nil {
				sortRows(rows, *operator.Sort)
			}
		case "limit":
			rows = limitRows(rows, operator.Limit)
		}
	}
	rows = limitRows(rows, plan.Limit)
	return rows, columns
}

func (e *Executor) executeUModel(ctx context.Context, workspace string, plan model.QueryPlan) (model.QueryResult, error) {
	snapshot, err := e.graph.GetUModelSnapshot(ctx, model.UModelSnapshotRequest{Workspace: workspace})
	if err != nil {
		return model.QueryResult{}, err
	}
	rows := make([]map[string]any, 0, len(snapshot.Elements))
	for _, element := range snapshot.Elements {
		rows = append(rows, map[string]any{
			"kind":    element.Kind,
			"domain":  element.Domain,
			"name":    element.Name,
			"version": element.Version,
			"spec":    element.Spec,
		})
	}
	return model.QueryResult{
		Columns: []string{"kind", "domain", "name", "version"},
		Rows:    rows,
		Page:    model.PageRequest{Limit: plan.Limit},
	}, nil
}

func applyPipeline(source string, rows []map[string]any, columns []string, plan model.QueryPlan) ([]map[string]any, []string) {
	if !hasOperator(plan.Pipeline, "with") && len(plan.Filters) > 0 {
		rows = filterRows(source, rows, plan.Filters)
	}

	for _, operator := range plan.Pipeline {
		switch operator.Name {
		case "with":
			rows = filterRows(source, rows, plan.Filters)
		case "where":
			if operator.Predicate != nil {
				rows = filterPredicate(rows, *operator.Predicate)
			}
		case "project":
			rows, columns = projectRows(rows, operator.Project)
		case "sort":
			if operator.Sort != nil {
				sortRows(rows, *operator.Sort)
			}
		case "limit":
			rows = limitRows(rows, operator.Limit)
		}
	}

	rows = limitRows(rows, plan.Limit)
	return rows, columns
}

func hasOperator(operators []model.QueryPipelineOperator, name string) bool {
	for _, operator := range operators {
		if operator.Name == name {
			return true
		}
	}
	return false
}

func filterRows(source string, rows []map[string]any, filters map[string]any) []map[string]any {
	if len(filters) == 0 {
		return rows
	}
	out := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		if rowMatchesFilters(source, row, filters) {
			out = append(out, row)
		}
	}
	return out
}

func rowMatchesFilters(source string, row map[string]any, filters map[string]any) bool {
	switch source {
	case ".umodel":
		if _, ok := filters["id"]; ok {
			return false
		}
		if !stringMatches(rowString(row, "kind"), filters["kind"]) {
			return false
		}
		if !stringMatches(rowString(row, "domain"), filters["domain"]) {
			return false
		}
		if !stringMatches(rowString(row, "name"), filters["name"]) {
			return false
		}
	case ".entity":
		if !stringMatches(rowString(row, "__domain__"), filters["domain"]) {
			return false
		}
		if !stringMatches(rowString(row, "__entity_type__"), filters["name"]) {
			return false
		}
		if !matchesIDs(rowString(row, "__entity_id__"), filters["ids"]) {
			return false
		}
	case ".topo":
		relationType := rowString(row, "__relation_type__")
		if relationType == "" {
			relationType = rowString(row, "relation")
		}
		if !stringMatches(relationType, coalesce(filters["relation_type"], filters["type"])) {
			return false
		}
		if !stringMatches(rowString(row, "src"), filters["src"]) {
			return false
		}
		if !stringMatches(rowString(row, "dest"), filters["dest"]) {
			return false
		}
	}

	query := stringFilter(filters["query"])
	if query != "" && !rowContains(row, query) {
		return false
	}
	return true
}

func filterPredicate(rows []map[string]any, predicate model.QueryPredicate) []map[string]any {
	out := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		if predicateMatches(row, predicate) {
			out = append(out, row)
		}
	}
	return out
}

func predicateMatches(row map[string]any, predicate model.QueryPredicate) bool {
	left, ok := row[predicate.Field]
	if !ok {
		return false
	}
	switch predicate.Op {
	case "=", "==":
		return compareEqual(left, predicate.Value)
	case "!=":
		return !compareEqual(left, predicate.Value)
	case "contains", "~":
		return containsFold(stringValue(left), stringValue(predicate.Value))
	case ">", ">=", "<", "<=":
		return compareOrdered(left, predicate.Value, predicate.Op)
	default:
		return false
	}
}

func projectRows(rows []map[string]any, fields []string) ([]map[string]any, []string) {
	out := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		next := make(map[string]any, len(fields))
		for _, field := range fields {
			next[field] = row[field]
		}
		out = append(out, next)
	}
	return out, append([]string(nil), fields...)
}

func sortRows(rows []map[string]any, sortSpec model.QuerySort) {
	sort.SliceStable(rows, func(i, j int) bool {
		cmp := compareForSort(rows[i][sortSpec.Field], rows[j][sortSpec.Field])
		if sortSpec.Desc {
			return cmp > 0
		}
		return cmp < 0
	})
}

func limitRows(rows []map[string]any, limit int) []map[string]any {
	if limit <= 0 || len(rows) <= limit {
		return rows
	}
	return rows[:limit]
}

func compareEqual(left, right any) bool {
	if lf, ok := floatValue(left); ok {
		if rf, ok := floatValue(right); ok {
			return lf == rf
		}
	}
	return stringValue(left) == stringValue(right)
}

func compareOrdered(left, right any, op string) bool {
	lf, lok := floatValue(left)
	rf, rok := floatValue(right)
	if lok && rok {
		switch op {
		case ">":
			return lf > rf
		case ">=":
			return lf >= rf
		case "<":
			return lf < rf
		case "<=":
			return lf <= rf
		}
	}
	lv := stringValue(left)
	rv := stringValue(right)
	switch op {
	case ">":
		return lv > rv
	case ">=":
		return lv >= rv
	case "<":
		return lv < rv
	case "<=":
		return lv <= rv
	default:
		return false
	}
}

func compareForSort(left, right any) int {
	if lf, ok := floatValue(left); ok {
		if rf, ok := floatValue(right); ok {
			switch {
			case lf < rf:
				return -1
			case lf > rf:
				return 1
			default:
				return 0
			}
		}
	}
	lv := stringValue(left)
	rv := stringValue(right)
	switch {
	case lv < rv:
		return -1
	case lv > rv:
		return 1
	default:
		return 0
	}
}

func floatValue(value any) (float64, bool) {
	switch typed := value.(type) {
	case int:
		return float64(typed), true
	case int64:
		return float64(typed), true
	case int32:
		return float64(typed), true
	case float64:
		return typed, true
	case float32:
		return float64(typed), true
	case string:
		n, err := strconv.ParseFloat(typed, 64)
		return n, err == nil
	default:
		return 0, false
	}
}

func rowContains(row map[string]any, query string) bool {
	for _, value := range row {
		if containsFold(stringValue(value), query) {
			return true
		}
	}
	return false
}

func rowString(row map[string]any, key string) string {
	return stringValue(row[key])
}

func matchesIDs(value string, filter any) bool {
	if filter == nil {
		return true
	}
	switch ids := filter.(type) {
	case []string:
		for _, id := range ids {
			if id == value {
				return true
			}
		}
		return false
	case []any:
		for _, id := range ids {
			if stringValue(id) == value {
				return true
			}
		}
		return false
	default:
		return stringValue(filter) == "" || stringValue(filter) == value
	}
}

func stringMatches(value string, filter any) bool {
	expected := stringFilter(filter)
	if expected == "" || expected == "*" {
		return true
	}
	if strings.HasSuffix(expected, "*") {
		return strings.HasPrefix(value, strings.TrimSuffix(expected, "*"))
	}
	return value == expected
}

func stringFilter(value any) string {
	if value == nil {
		return ""
	}
	if text, ok := value.(string); ok {
		return text
	}
	return ""
}

func stringValue(value any) string {
	switch typed := value.(type) {
	case string:
		return typed
	case fmt.Stringer:
		return typed.String()
	case nil:
		return ""
	default:
		return fmt.Sprint(value)
	}
}

func containsFold(value, query string) bool {
	return strings.Contains(strings.ToLower(value), strings.ToLower(query))
}

func coalesce(values ...any) any {
	for _, value := range values {
		if stringValue(value) != "" {
			return value
		}
	}
	return nil
}
