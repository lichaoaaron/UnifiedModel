package bootstrap

import (
	"context"
	"strings"

	"github.com/alibaba/MModel/internal/sampledata"
	apperrors "github.com/alibaba/MModel/pkg/errors"
	"github.com/alibaba/MModel/pkg/model"
)

const (
	DefaultQuickStartWorkspaceID          = "demo"
	DefaultQuickStartWorkspaceName        = "Demo"
	DefaultQuickStartWorkspaceDescription = "Multi-domain quickstart demo"
	DefaultQuickStartSample               = sampledata.MultiDomainQuickStartSample
)

type QuickStartOptions struct {
	WorkspaceID          string
	WorkspaceName        string
	WorkspaceDescription string
	Sample               string
}

func (a *App) LoadQuickStart(ctx context.Context, opts QuickStartOptions) (model.SampleImportResult, error) {
	workspaceID := strings.TrimSpace(opts.WorkspaceID)
	if workspaceID == "" {
		workspaceID = DefaultQuickStartWorkspaceID
	}
	workspaceName := strings.TrimSpace(opts.WorkspaceName)
	if workspaceName == "" {
		workspaceName = DefaultQuickStartWorkspaceName
	}
	workspaceDescription := strings.TrimSpace(opts.WorkspaceDescription)
	if workspaceDescription == "" {
		workspaceDescription = DefaultQuickStartWorkspaceDescription
	}
	sample := strings.TrimSpace(opts.Sample)
	if sample == "" {
		sample = DefaultQuickStartSample
	}

	if _, err := a.Workspace.GetWorkspace(ctx, workspaceID); err != nil {
		if !apperrors.IsCode(err, apperrors.CodeNotFound) {
			return model.SampleImportResult{}, err
		}
		if _, err := a.Workspace.CreateWorkspace(ctx, model.CreateWorkspaceRequest{
			ID:          workspaceID,
			Name:        workspaceName,
			Description: workspaceDescription,
			Labels: map[string]string{
				"mmodel.io/quickstart": "true",
			},
		}); err != nil && !apperrors.IsCode(err, apperrors.CodeConflict) {
			return model.SampleImportResult{}, err
		}
	}

	return a.Samples.Import(ctx, workspaceID, sample)
}
