package contract

import (
	"context"

	"github.com/alibaba/MModel/pkg/model"
)

type WorkspaceManager interface {
	CreateWorkspace(ctx context.Context, req model.CreateWorkspaceRequest) (model.WorkspaceMetadata, error)
	GetWorkspace(ctx context.Context, id string) (model.WorkspaceMetadata, error)
	ListWorkspaces(ctx context.Context, req model.WorkspaceListRequest) (model.Page[model.WorkspaceMetadata], error)
	UpdateWorkspace(ctx context.Context, id string, req model.UpdateWorkspaceRequest) (model.WorkspaceMetadata, error)
	DeleteWorkspace(ctx context.Context, id string) (model.WorkspaceMetadata, error)
}

type WorkspaceMetadataReader interface {
	GetWorkspace(ctx context.Context, id string) (model.WorkspaceMetadata, error)
	ListWorkspaces(ctx context.Context, req model.WorkspaceListRequest) (model.Page[model.WorkspaceMetadata], error)
}

type WorkspaceConfigSchemaRegistry interface {
	ValidateNamespace(ctx context.Context, namespace string, value map[string]any) error
}

type GraphStore interface {
	OpenWorkspace(ctx context.Context, workspace model.WorkspaceMetadata) error
	EnsureSchema(ctx context.Context, workspace string) error
	PutMModelElements(ctx context.Context, batch model.MModelElementBatch) (model.WriteResult, error)
	GetMModelSnapshot(ctx context.Context, req model.MModelSnapshotRequest) (model.MModelSnapshot, error)
	WriteEntities(ctx context.Context, batch model.EntityWriteBatch) (model.WriteResult, error)
	WriteRelations(ctx context.Context, batch model.RelationWriteBatch) (model.WriteResult, error)
	QueryEntities(ctx context.Context, plan model.EntityQueryPlan) (model.QueryResult, error)
	QueryTopo(ctx context.Context, plan model.TopoQueryPlan) (model.QueryResult, error)
	Capabilities(ctx context.Context) (model.GraphStoreCapabilities, error)
	Health(ctx context.Context) (model.GraphStoreHealth, error)
}

type MModelService interface {
	Import(ctx context.Context, workspace string, req model.MModelImportRequest) (model.MModelImportResult, error)
	Validate(ctx context.Context, workspace string, elements []model.MModelElement) (model.ValidationResult, error)
	PutElements(ctx context.Context, batch model.MModelElementBatch) (model.WriteResult, error)
	DeleteElements(ctx context.Context, workspace string, ids []string) (model.WriteResult, error)
	RebuildIndex(ctx context.Context, workspace string) error
}

type MModelSchemaResolver interface {
	ResolveEntitySet(ctx context.Context, ref model.EntityTypeRef) (model.EntitySetSchema, error)
	ResolveRelationType(ctx context.Context, ref model.RelationTypeRef) (model.RelationSchema, error)
	ValidateEntityPayload(ctx context.Context, payload model.EntityPayload) (model.ValidationResult, error)
	ValidateRelationPayload(ctx context.Context, payload model.RelationPayload) (model.ValidationResult, error)
	SnapshotVersion(ctx context.Context, workspace string) (model.SchemaVersion, error)
}

type EntityWriteService interface {
	WriteEntities(ctx context.Context, workspace string, batch model.EntityWriteBatch) (model.WriteResult, error)
	WriteRelations(ctx context.Context, workspace string, batch model.RelationWriteBatch) (model.WriteResult, error)
	ExpireEntities(ctx context.Context, workspace string, req model.ExpireRequest) (model.WriteResult, error)
	ExpireRelations(ctx context.Context, workspace string, req model.ExpireRequest) (model.WriteResult, error)
}

type QueryService interface {
	Execute(ctx context.Context, workspace string, req model.QueryRequest) (model.QueryResult, error)
	Explain(ctx context.Context, workspace string, req model.QueryRequest) (model.QueryExplain, error)
	Examples(ctx context.Context) ([]string, error)
}

type AgentGateway interface {
	Discover(ctx context.Context, workspace string) (model.AgentDiscovery, error)
	Tools(ctx context.Context) ([]model.AgentTool, error)
	ReadResource(ctx context.Context, workspace string, req model.AgentResourceReadRequest) (model.AgentResourceReadResult, error)
	ExecuteTool(ctx context.Context, workspace string, req model.AgentToolCallRequest) (model.AgentToolCallResult, error)
}
