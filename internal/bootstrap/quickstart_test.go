package bootstrap

import (
	"context"
	"testing"

	"github.com/alibaba/MModel/pkg/model"
)

func TestLoadQuickStartCreatesWorkspaceAndImportsSample(t *testing.T) {
	ctx := context.Background()
	app := NewMemoryApp(t.TempDir())

	result, err := app.LoadQuickStart(ctx, QuickStartOptions{})
	if err != nil {
		t.Fatalf("load quickstart: %v", err)
	}
	if result.Workspace != DefaultQuickStartWorkspaceID || result.Sample != DefaultQuickStartSample {
		t.Fatalf("unexpected quickstart result: %+v", result)
	}
	if result.MModel.Imported == 0 || result.EntityCount == 0 || result.RelationCount == 0 {
		t.Fatalf("quickstart should import model, entity, and topology data: %+v", result)
	}

	workspace, err := app.Workspace.GetWorkspace(ctx, DefaultQuickStartWorkspaceID)
	if err != nil {
		t.Fatalf("get quickstart workspace: %v", err)
	}
	if workspace.Name != DefaultQuickStartWorkspaceName || workspace.Labels["mmodel.io/quickstart"] != "true" {
		t.Fatalf("unexpected quickstart workspace metadata: %+v", workspace)
	}

	rows, err := app.Query.Execute(ctx, DefaultQuickStartWorkspaceID, model.QueryRequest{
		Query: ".entity with(domain='devops', name='devops.service', query='checkout') | limit 5",
	})
	if err != nil {
		t.Fatalf("query quickstart sample: %v", err)
	}
	if len(rows.Rows) == 0 {
		t.Fatalf("expected quickstart sample entity rows, got %+v", rows)
	}
}

func TestLoadQuickStartIsSafeWithExistingWorkspace(t *testing.T) {
	ctx := context.Background()
	root := t.TempDir()

	first := NewFileMemoryApp(root)
	if _, err := first.LoadQuickStart(ctx, QuickStartOptions{}); err != nil {
		t.Fatalf("first quickstart load: %v", err)
	}

	second := NewFileMemoryApp(root)
	result, err := second.LoadQuickStart(ctx, QuickStartOptions{})
	if err != nil {
		t.Fatalf("second quickstart load: %v", err)
	}
	if result.Workspace != DefaultQuickStartWorkspaceID || result.EntityCount == 0 || result.RelationCount == 0 {
		t.Fatalf("unexpected second quickstart result: %+v", result)
	}
}
