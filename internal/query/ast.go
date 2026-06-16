package query

import "github.com/alibaba/MModel/pkg/model"

type AST struct {
	Source    string
	Query     string
	Filters   map[string]any
	Operators []model.QueryPipelineOperator
	Limit     int
	Depth     int
}

func (a AST) OperatorNames() []string {
	names := make([]string, 0, len(a.Operators))
	for _, operator := range a.Operators {
		names = append(names, operator.Name)
	}
	return names
}
