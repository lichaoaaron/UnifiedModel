package query

import (
	"context"

	"github.com/alibaba/MModel/internal/telemetry"
	"github.com/alibaba/MModel/pkg/model"
)

type graphStore interface {
	GetMModelSnapshot(ctx context.Context, req model.MModelSnapshotRequest) (model.MModelSnapshot, error)
	QueryEntities(ctx context.Context, plan model.EntityQueryPlan) (model.QueryResult, error)
	QueryTopo(ctx context.Context, plan model.TopoQueryPlan) (model.QueryResult, error)
	Capabilities(ctx context.Context) (model.GraphStoreCapabilities, error)
	Health(ctx context.Context) (model.GraphStoreHealth, error)
}

type Service struct {
	graph    graphStore
	planner  Planner
	executor *Executor
}

// NewService creates a Query Service without telemetry providers.
func NewService(graph graphStore) *Service {
	return &Service{
		graph:    graph,
		planner:  Planner{},
		executor: NewExecutor(graph, nil),
	}
}

// NewServiceWithProviders creates a Query Service with a set of TelemetryProviders
// for evidence() operator execution.
func NewServiceWithProviders(graph graphStore, providers []telemetry.Provider) *Service {
	return &Service{
		graph:    graph,
		planner:  Planner{},
		executor: NewExecutor(graph, providers),
	}
}

func (s *Service) Execute(ctx context.Context, workspace string, req model.QueryRequest) (model.QueryResult, error) {
	plan, caps, health, err := s.plan(ctx, workspace, req)
	if err != nil {
		return model.QueryResult{}, err
	}
	result, err := s.executor.Execute(ctx, workspace, plan)
	if err != nil {
		return model.QueryResult{}, err
	}
	explain := buildExplain(plan, caps, health)
	// Preserve evidence explain set by the executor
	if result.Explain != nil && result.Explain.Evidence != nil {
		explain.Evidence = result.Explain.Evidence
	}
	result.Explain = &explain
	return result, nil
}

func (s *Service) Explain(ctx context.Context, workspace string, req model.QueryRequest) (model.QueryExplain, error) {
	plan, caps, health, err := s.plan(ctx, workspace, req)
	if err != nil {
		return model.QueryExplain{}, err
	}
	explain := buildExplain(plan, caps, health)

	// For evidence queries, resolve the full chain so callers can see the
	// DataLink → DataSet → StorageLink → Storage → Provider path.
	if plan.Source == ".entity" {
		if evOp, ok := findEvidenceOperator(plan.Pipeline); ok {
			evExplain, resolveErr := s.executor.resolveEvidenceExplainForPlan(ctx, workspace, plan, evOp)
			if resolveErr == nil && evExplain != nil {
				explain.Evidence = evExplain
			}
			// If resolution fails (e.g. entity not found), return explain without evidence
			// section rather than surfacing an error — the query itself may still be valid.
		}
	}

	return explain, nil
}

func (s *Service) Examples(ctx context.Context) ([]string, error) {
	return []string{
		".mmodel with(kind='entity_set') | project domain,name,kind | sort domain,name | limit 20",
		".entity with(domain='devops', name='devops.service', query='checkout', topk=20)",
		".entity with(domain='k8s', name='k8s.workload', query='checkout', topk=20)",
		".topo | graph-call getNeighborNodes('full', 2, [(:\"devops@devops.service\" {__entity_id__: '10000000000000000000000000000101'})]) | limit 20",
		".topo | graph-call getDirectRelations([(:\"devops@devops.service\" {__entity_id__: '10000000000000000000000000000101'})]) | limit 20",
		".topo | graph-call cypher(`MATCH (src)-[r]->(dest) RETURN properties(src) AS src, properties(r) AS relation, properties(dest) AS dest LIMIT 20`)",
	}, nil
}

func (s *Service) plan(ctx context.Context, workspace string, req model.QueryRequest) (model.QueryPlan, model.GraphStoreCapabilities, model.GraphStoreHealth, error) {
	caps, err := s.graph.Capabilities(ctx)
	if err != nil {
		return model.QueryPlan{}, model.GraphStoreCapabilities{}, model.GraphStoreHealth{}, err
	}
	plan, err := s.planner.Plan(req, caps)
	if err != nil {
		return model.QueryPlan{}, model.GraphStoreCapabilities{}, model.GraphStoreHealth{}, err
	}
	plan.Workspace = workspace
	health, err := s.graph.Health(ctx)
	if err != nil {
		return model.QueryPlan{}, model.GraphStoreCapabilities{}, model.GraphStoreHealth{}, err
	}
	return plan, caps, health, nil
}
