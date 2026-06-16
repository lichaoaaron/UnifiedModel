package bootstrap

import (
	"context"
	"testing"

	"github.com/alibaba/MModel/pkg/model"
)

func TestFileMemoryAppPersistsWorkspaceMetadata(t *testing.T) {
	ctx := context.Background()
	root := t.TempDir()

	first := NewFileMemoryApp(root)
	if _, err := first.Workspace.CreateWorkspace(ctx, model.CreateWorkspaceRequest{ID: "demo", Name: "Demo"}); err != nil {
		t.Fatalf("create workspace: %v", err)
	}

	second := NewFileMemoryApp(root)
	page, err := second.Workspace.ListWorkspaces(ctx, model.WorkspaceListRequest{})
	if err != nil {
		t.Fatalf("list workspaces: %v", err)
	}
	if len(page.Items) != 1 || page.Items[0].ID != "demo" || page.Items[0].Name != "Demo" {
		t.Fatalf("expected persisted demo workspace, got %+v", page.Items)
	}
}
