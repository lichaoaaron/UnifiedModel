package graphstore

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/alibaba/MModel/pkg/model"
)

func TestFileMemoryStorePersistsAcrossReopen(t *testing.T) {
	ctx := context.Background()
	root := t.TempDir()

	store, err := NewFileMemoryStore(ProviderConfig{DataRoot: root})
	if err != nil {
		t.Fatalf("new file memory store: %v", err)
	}
	if err := store.OpenWorkspace(ctx, model.WorkspaceMetadata{ID: "demo"}); err != nil {
		t.Fatalf("open workspace: %v", err)
	}
	if _, err := store.PutMModelElements(ctx, model.MModelElementBatch{
		Workspace: "demo",
		Elements: []model.MModelElement{{
			Kind:    "entity_set",
			Domain:  "apm",
			Name:    "apm.service",
			Version: "v1",
			Spec:    map[string]any{"display_name": "APM Service"},
		}},
	}); err != nil {
		t.Fatalf("put mmodel: %v", err)
	}
	if _, err := store.WriteEntities(ctx, model.EntityWriteBatch{
		Workspace: "demo",
		Entities:  []model.EntityPayload{entityPayload("54013ba69c196820e56801f1ef5aad54", "Create", 100, 200, map[string]any{"display_name": "cart service"})},
	}); err != nil {
		t.Fatalf("write entity: %v", err)
	}
	if _, err := store.WriteRelations(ctx, model.RelationWriteBatch{
		Workspace: "demo",
		Relations: []model.RelationPayload{relationPayload("54013ba69c196820e56801f1ef5aad54", "177627f91af678a9b03e993f1a91917f", "Create", 100, 200, nil)},
	}); err != nil {
		t.Fatalf("write relation: %v", err)
	}

	assertFileExists(t, filepath.Join(root, "graphstore", "file-memory", "workspaces", "demo", "mmodels.json"))
	assertFileExists(t, filepath.Join(root, "graphstore", "file-memory", "workspaces", "demo", "entities.json"))
	assertFileExists(t, filepath.Join(root, "graphstore", "file-memory", "workspaces", "demo", "relations.json"))

	reopened, err := NewFileMemoryStore(ProviderConfig{DataRoot: root})
	if err != nil {
		t.Fatalf("reopen file memory store: %v", err)
	}
	health, err := reopened.Health(ctx)
	if err != nil {
		t.Fatalf("health: %v", err)
	}
	if health.Provider != ProviderTypeFileMemory {
		t.Fatalf("expected file memory provider health, got %+v", health)
	}

	snapshot, err := reopened.GetMModelSnapshot(ctx, model.MModelSnapshotRequest{Workspace: "demo"})
	if err != nil {
		t.Fatalf("snapshot: %v", err)
	}
	if snapshot.Version != ProviderTypeFileMemory || len(snapshot.Elements) != 1 || snapshot.Elements[0].Spec["display_name"] != "APM Service" {
		t.Fatalf("unexpected reopened snapshot: %+v", snapshot)
	}

	entityRows, err := reopened.QueryEntities(ctx, model.EntityQueryPlan{
		Workspace: "demo",
		Filters:   map[string]any{"ids": []string{"54013ba69c196820e56801f1ef5aad54"}, "query": "cart service"},
		Limit:     10,
	})
	if err != nil {
		t.Fatalf("query entity: %v", err)
	}
	if len(entityRows.Rows) != 1 || entityRows.Rows[0]["__entity_id__"] != "54013ba69c196820e56801f1ef5aad54" {
		t.Fatalf("unexpected reopened entity rows: %+v", entityRows.Rows)
	}

	topoRows, err := reopened.QueryTopo(ctx, model.TopoQueryPlan{
		Workspace: "demo",
		Filters:   map[string]any{"relation_type": "calls"},
		Limit:     10,
	})
	if err != nil {
		t.Fatalf("query topo: %v", err)
	}
	if len(topoRows.Rows) != 1 || topoRows.Rows[0]["relation"] != "calls" {
		t.Fatalf("unexpected reopened topo rows: %+v", topoRows.Rows)
	}
}

func TestFileMemoryStoreMigratesLegacySingleFileState(t *testing.T) {
	ctx := context.Background()
	root := t.TempDir()
	legacyPath := filepath.Join(root, "graphstore", "file-memory.json")
	if err := os.MkdirAll(filepath.Dir(legacyPath), 0o755); err != nil {
		t.Fatalf("create legacy dir: %v", err)
	}
	data, err := json.Marshal(fileMemoryState{
		Version: fileMemoryStateVersion,
		MModels: map[string]map[string]model.MModelElement{
			"demo": {
				"apm/apm.service/entity_set": {
					Kind:    "entity_set",
					Domain:  "apm",
					Name:    "apm.service",
					Version: "v1",
					Spec:    map[string]any{"display_name": "APM Service"},
				},
			},
		},
		Entities: map[string]map[string]model.EntityPayload{
			"demo": {
				"apm/apm.service/54013ba69c196820e56801f1ef5aad54": entityPayload("54013ba69c196820e56801f1ef5aad54", "Create", 100, 200, map[string]any{"display_name": "cart service"}),
			},
		},
		Relations: map[string]map[string]model.RelationPayload{
			"demo": {
				"apm/apm.service/54013ba69c196820e56801f1ef5aad54/calls/apm/apm.service/177627f91af678a9b03e993f1a91917f": relationPayload("54013ba69c196820e56801f1ef5aad54", "177627f91af678a9b03e993f1a91917f", "Create", 100, 200, nil),
			},
		},
	})
	if err != nil {
		t.Fatalf("marshal legacy state: %v", err)
	}
	if err := os.WriteFile(legacyPath, data, 0o644); err != nil {
		t.Fatalf("write legacy state: %v", err)
	}

	store, err := NewFileMemoryStore(ProviderConfig{DataRoot: root})
	if err != nil {
		t.Fatalf("new file memory store: %v", err)
	}
	assertFileExists(t, filepath.Join(root, "graphstore", "file-memory", "workspaces", "demo", "mmodels.json"))
	assertFileExists(t, filepath.Join(root, "graphstore", "file-memory", "workspaces", "demo", "entities.json"))
	assertFileExists(t, filepath.Join(root, "graphstore", "file-memory", "workspaces", "demo", "relations.json"))

	snapshot, err := store.GetMModelSnapshot(ctx, model.MModelSnapshotRequest{Workspace: "demo"})
	if err != nil {
		t.Fatalf("snapshot: %v", err)
	}
	if len(snapshot.Elements) != 1 || snapshot.Elements[0].Domain != "apm" || snapshot.Elements[0].Name != "apm.service" || snapshot.Elements[0].Kind != "entity_set" {
		t.Fatalf("unexpected migrated snapshot: %+v", snapshot)
	}
	entityRows, err := store.QueryEntities(ctx, model.EntityQueryPlan{
		Workspace: "demo",
		Filters:   map[string]any{"ids": []string{"54013ba69c196820e56801f1ef5aad54"}},
		Limit:     10,
	})
	if err != nil {
		t.Fatalf("query entity: %v", err)
	}
	if len(entityRows.Rows) != 1 || entityRows.Rows[0]["display_name"] != "cart service" {
		t.Fatalf("unexpected migrated entity rows: %+v", entityRows.Rows)
	}
}

func TestFileMemoryStoreLoadsLegacyMModelCollectionName(t *testing.T) {
	ctx := context.Background()
	root := t.TempDir()
	workspaceDir := filepath.Join(root, "graphstore", "file-memory", "workspaces", "demo")
	if err := os.MkdirAll(workspaceDir, 0o755); err != nil {
		t.Fatalf("create workspace dir: %v", err)
	}
	if err := writeFileMemoryCollection(filepath.Join(workspaceDir, "umodels.json"), map[string]model.MModelElement{
		"apm/apm.service/entity_set": {
			Kind:    "entity_set",
			Domain:  "apm",
			Name:    "apm.service",
			Version: "v1",
			Spec:    map[string]any{"display_name": "APM Service"},
		},
	}); err != nil {
		t.Fatalf("write legacy mmodel collection: %v", err)
	}

	store, err := NewFileMemoryStore(ProviderConfig{DataRoot: root})
	if err != nil {
		t.Fatalf("new file memory store: %v", err)
	}
	if _, err := store.PutMModelElements(ctx, model.MModelElementBatch{
		Workspace: "demo",
		Elements: []model.MModelElement{{
			Kind:    "entity_set",
			Domain:  "apm",
			Name:    "apm.database",
			Version: "v1",
		}},
	}); err != nil {
		t.Fatalf("put mmodel after legacy load: %v", err)
	}

	assertFileExists(t, filepath.Join(workspaceDir, "mmodels.json"))
	snapshot, err := store.GetMModelSnapshot(ctx, model.MModelSnapshotRequest{Workspace: "demo"})
	if err != nil {
		t.Fatalf("snapshot: %v", err)
	}
	if len(snapshot.Elements) != 2 {
		t.Fatalf("expected legacy and new elements, got %+v", snapshot.Elements)
	}
}

func TestFileMemoryStoreWritesMModelWhenWorkspaceHasOnlyRuntimeCollections(t *testing.T) {
	ctx := context.Background()
	root := t.TempDir()
	workspaceDir := filepath.Join(root, "graphstore", "file-memory", "workspaces", "demo")
	if err := os.MkdirAll(workspaceDir, 0o755); err != nil {
		t.Fatalf("create workspace dir: %v", err)
	}
	if err := writeFileMemoryCollection(filepath.Join(workspaceDir, "entities.json"), map[string]model.EntityPayload{
		"apm/apm.service/54013ba69c196820e56801f1ef5aad54": entityPayload("54013ba69c196820e56801f1ef5aad54", "Create", 100, 200, nil),
	}); err != nil {
		t.Fatalf("write entities collection: %v", err)
	}

	store, err := NewFileMemoryStore(ProviderConfig{DataRoot: root})
	if err != nil {
		t.Fatalf("new file memory store: %v", err)
	}
	if _, err := store.PutMModelElements(ctx, model.MModelElementBatch{
		Workspace: "demo",
		Elements: []model.MModelElement{{
			Kind:    "entity_set",
			Domain:  "apm",
			Name:    "apm.service",
			Version: "v1",
		}},
	}); err != nil {
		t.Fatalf("put mmodel after runtime-only load: %v", err)
	}

	assertFileExists(t, filepath.Join(workspaceDir, "mmodels.json"))
}

func assertFileExists(t *testing.T, path string) {
	t.Helper()
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("expected file %s: %v", path, err)
	}
}
