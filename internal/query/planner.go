package query

import (
	"fmt"
	"strings"

	apperrors "github.com/alibaba/MModel/pkg/errors"
	"github.com/alibaba/MModel/pkg/model"
)

type Planner struct{}

func (Planner) Plan(req model.QueryRequest, caps model.GraphStoreCapabilities) (model.QueryPlan, error) {
	plan, err := Parse(req)
	if err != nil {
		return model.QueryPlan{}, err
	}
	if err := validatePlan(plan, caps); err != nil {
		return model.QueryPlan{}, err
	}
	return plan, nil
}

func validatePlan(plan model.QueryPlan, caps model.GraphStoreCapabilities) error {
	maxLimit := caps.MaxLimit
	if maxLimit <= 0 {
		maxLimit = 1000
	}
	if plan.Limit > maxLimit {
		return apperrors.WithDetails(apperrors.CodeValidationFailed, "query limit exceeds provider capability", map[string]string{
			"limit":     fmt.Sprint(plan.Limit),
			"max_limit": fmt.Sprint(maxLimit),
		})
	}
	if plan.TopK > maxLimit {
		return apperrors.WithDetails(apperrors.CodeValidationFailed, "query topk exceeds provider capability", map[string]string{
			"topk":      fmt.Sprint(plan.TopK),
			"max_limit": fmt.Sprint(maxLimit),
		})
	}

	maxDepth := caps.MaxDepth
	if maxDepth <= 0 {
		maxDepth = 1
	}
	if plan.Depth > maxDepth {
		return apperrors.WithDetails(apperrors.CodeValidationFailed, "query depth exceeds provider capability", map[string]string{
			"depth":     fmt.Sprint(plan.Depth),
			"max_depth": fmt.Sprint(maxDepth),
		})
	}

	for _, operator := range plan.Operators {
		switch {
		case operator == "graph-match" && !caps.GraphMatch:
			return apperrors.New(apperrors.CodeProviderUnsupported, "graph-match is not supported by provider")
		case strings.HasPrefix(operator, "graph-call:"):
			if plan.Source != ".topo" {
				return apperrors.New(apperrors.CodeQueryPlanError, "graph-call is only supported for .topo")
			}
			if plan.GraphCall == nil || !isAllowedGraphCall(plan.GraphCall.Name) {
				return apperrors.WithDetails(apperrors.CodeQueryPlanError, "unsupported graph-call", map[string]string{"name": graphCallName(plan.GraphCall)})
			}
			if plan.GraphCall.Name == "cypher" {
				if !caps.ControlledCypher {
					return apperrors.New(apperrors.CodeProviderUnsupported, "controlled cypher is not supported by provider")
				}
				continue
			}
			if !caps.GraphCallNeighbors {
				return apperrors.New(apperrors.CodeProviderUnsupported, "graph-call is not supported by provider")
			}
		}
	}

	return nil
}

func isAllowedGraphCall(name string) bool {
	return name == "getNeighborNodes" || name == "getDirectRelations" || name == "cypher"
}

func graphCallName(call *model.GraphCallPlan) string {
	if call == nil {
		return ""
	}
	return call.Name
}
