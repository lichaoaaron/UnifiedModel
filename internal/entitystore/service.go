package entitystore

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"time"

	apperrors "github.com/alibaba/MModel/pkg/errors"
	"github.com/alibaba/MModel/pkg/model"
)

type graphStore interface {
	WriteEntities(ctx context.Context, batch model.EntityWriteBatch) (model.WriteResult, error)
	WriteRelations(ctx context.Context, batch model.RelationWriteBatch) (model.WriteResult, error)
}

type schemaResolver interface {
	ValidateEntityPayload(ctx context.Context, payload model.EntityPayload) (model.ValidationResult, error)
	ValidateRelationPayload(ctx context.Context, payload model.RelationPayload) (model.ValidationResult, error)
}

type Service struct {
	graph    graphStore
	resolver schemaResolver

	mu                  sync.Mutex
	entityIdempotency   map[string]model.WriteResult
	relationIdempotency map[string]model.WriteResult
}

func NewService(graph graphStore, resolver schemaResolver) *Service {
	return &Service{
		graph:               graph,
		resolver:            resolver,
		entityIdempotency:   make(map[string]model.WriteResult),
		relationIdempotency: make(map[string]model.WriteResult),
	}
}

func (s *Service) WriteEntities(ctx context.Context, workspace string, batch model.EntityWriteBatch) (model.WriteResult, error) {
	batch.Workspace = workspace
	if cached, ok := s.cachedEntityResult(workspace, batch.IdempotencyKey); ok {
		return cached, nil
	}

	var validationResult model.WriteResult
	valid := model.EntityWriteBatch{
		Workspace:      workspace,
		IdempotencyKey: batch.IdempotencyKey,
		PartialSuccess: batch.PartialSuccess,
		Entities:       make([]model.EntityPayload, 0, len(batch.Entities)),
	}
	for _, payload := range batch.Entities {
		result, err := s.resolver.ValidateEntityPayload(ctx, payload)
		if err != nil {
			return model.WriteResult{}, err
		}
		if !result.Valid {
			item := failedItem(model.EntityStableKey(payload), apperrors.CodeValidationFailed, "entity payload validation failed", result.Errors)
			if !batch.PartialSuccess {
				return model.WriteResult{}, validationError("entity payload validation failed", result.Errors)
			}
			validationResult.Failed++
			validationResult.Items = append(validationResult.Items, item)
			continue
		}
		valid.Entities = append(valid.Entities, payload)
	}

	graphResult := model.WriteResult{}
	if len(valid.Entities) > 0 {
		var err error
		graphResult, err = s.graph.WriteEntities(ctx, valid)
		if err != nil {
			return model.WriteResult{}, err
		}
	}
	result := mergeWriteResults(graphResult, validationResult)
	if result.Failed > 0 && !batch.PartialSuccess {
		return result, itemFailureError("entity", result.Failed)
	}
	s.rememberEntityResult(workspace, batch.IdempotencyKey, result)
	return result, nil
}

func (s *Service) WriteRelations(ctx context.Context, workspace string, batch model.RelationWriteBatch) (model.WriteResult, error) {
	batch.Workspace = workspace
	if cached, ok := s.cachedRelationResult(workspace, batch.IdempotencyKey); ok {
		return cached, nil
	}

	var validationResult model.WriteResult
	valid := model.RelationWriteBatch{
		Workspace:      workspace,
		IdempotencyKey: batch.IdempotencyKey,
		PartialSuccess: batch.PartialSuccess,
		Relations:      make([]model.RelationPayload, 0, len(batch.Relations)),
	}
	for _, payload := range batch.Relations {
		result, err := s.resolver.ValidateRelationPayload(ctx, payload)
		if err != nil {
			return model.WriteResult{}, err
		}
		if !result.Valid {
			item := failedItem(model.RelationStableKey(payload), apperrors.CodeValidationFailed, "relation payload validation failed", result.Errors)
			if !batch.PartialSuccess {
				return model.WriteResult{}, validationError("relation payload validation failed", result.Errors)
			}
			validationResult.Failed++
			validationResult.Items = append(validationResult.Items, item)
			continue
		}
		valid.Relations = append(valid.Relations, payload)
	}

	graphResult := model.WriteResult{}
	if len(valid.Relations) > 0 {
		var err error
		graphResult, err = s.graph.WriteRelations(ctx, valid)
		if err != nil {
			return model.WriteResult{}, err
		}
	}
	result := mergeWriteResults(graphResult, validationResult)
	if result.Failed > 0 && !batch.PartialSuccess {
		return result, itemFailureError("relation", result.Failed)
	}
	s.rememberRelationResult(workspace, batch.IdempotencyKey, result)
	return result, nil
}

func (s *Service) ExpireEntities(ctx context.Context, workspace string, req model.ExpireRequest) (model.WriteResult, error) {
	req.Workspace = workspace
	now := time.Now().Unix()
	var parseResult model.WriteResult
	payloads := make([]model.EntityPayload, 0, len(req.IDs))
	for _, id := range req.IDs {
		payload, ok := entityPayloadFromStableKey(id, now)
		if !ok {
			parseResult.Failed++
			parseResult.Items = append(parseResult.Items, failedItem(id, apperrors.CodeValidationFailed, "entity id must be a stable key", nil))
			continue
		}
		payloads = append(payloads, payload)
	}
	graphResult := model.WriteResult{}
	if len(payloads) > 0 {
		var err error
		graphResult, err = s.graph.WriteEntities(ctx, model.EntityWriteBatch{Workspace: workspace, PartialSuccess: true, Entities: payloads})
		if err != nil {
			return model.WriteResult{}, err
		}
	}
	return mergeWriteResults(graphResult, parseResult), nil
}

func (s *Service) ExpireRelations(ctx context.Context, workspace string, req model.ExpireRequest) (model.WriteResult, error) {
	req.Workspace = workspace
	now := time.Now().Unix()
	var parseResult model.WriteResult
	payloads := make([]model.RelationPayload, 0, len(req.IDs))
	for _, id := range req.IDs {
		payload, ok := relationPayloadFromStableKey(id, now)
		if !ok {
			parseResult.Failed++
			parseResult.Items = append(parseResult.Items, failedItem(id, apperrors.CodeValidationFailed, "relation id must be a stable key", nil))
			continue
		}
		payloads = append(payloads, payload)
	}
	graphResult := model.WriteResult{}
	if len(payloads) > 0 {
		var err error
		graphResult, err = s.graph.WriteRelations(ctx, model.RelationWriteBatch{Workspace: workspace, PartialSuccess: true, Relations: payloads})
		if err != nil {
			return model.WriteResult{}, err
		}
	}
	return mergeWriteResults(graphResult, parseResult), nil
}

func (s *Service) RunTTL(ctx context.Context, workspace string, now time.Time) (model.WriteResult, error) {
	if workspace == "" {
		return model.WriteResult{}, apperrors.New(apperrors.CodeInvalidArgument, "workspace is required")
	}
	return model.WriteResult{}, nil
}

func (s *Service) cachedEntityResult(workspace, key string) (model.WriteResult, bool) {
	if key == "" {
		return model.WriteResult{}, false
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	result, ok := s.entityIdempotency[idempotencyKey(workspace, key)]
	return cloneWriteResult(result), ok
}

func (s *Service) cachedRelationResult(workspace, key string) (model.WriteResult, bool) {
	if key == "" {
		return model.WriteResult{}, false
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	result, ok := s.relationIdempotency[idempotencyKey(workspace, key)]
	return cloneWriteResult(result), ok
}

func (s *Service) rememberEntityResult(workspace, key string, result model.WriteResult) {
	if key == "" {
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.entityIdempotency[idempotencyKey(workspace, key)] = cloneWriteResult(result)
}

func (s *Service) rememberRelationResult(workspace, key string, result model.WriteResult) {
	if key == "" {
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.relationIdempotency[idempotencyKey(workspace, key)] = cloneWriteResult(result)
}

func idempotencyKey(workspace, key string) string {
	return workspace + "\x00" + key
}

func validationError(message string, details []model.ErrorDetail) error {
	fields := map[string]string{}
	if len(details) > 0 {
		fields["field"] = details[0].Field
	}
	return apperrors.WithDetails(apperrors.CodeValidationFailed, message, fields)
}

func failedItem(id string, code apperrors.Code, message string, details []model.ErrorDetail) model.BatchItemResult {
	return model.BatchItemResult{
		ID:      id,
		OK:      false,
		Code:    string(code),
		Message: message,
		Details: cloneErrorDetails(details),
	}
}

func mergeWriteResults(results ...model.WriteResult) model.WriteResult {
	var merged model.WriteResult
	for _, result := range results {
		merged.Accepted += result.Accepted
		merged.Failed += result.Failed
		merged.Items = append(merged.Items, result.Items...)
	}
	return merged
}

func entityPayloadFromStableKey(key string, now int64) (model.EntityPayload, bool) {
	parts := strings.Split(key, "/")
	if len(parts) != 3 {
		return nil, false
	}
	for _, part := range parts {
		if part == "" {
			return nil, false
		}
	}
	if !model.IsEntityID(parts[2]) {
		return nil, false
	}
	return model.EntityPayload{
		"__domain__":              parts[0],
		"__entity_type__":         parts[1],
		"__entity_id__":           parts[2],
		"__method__":              "Expire",
		"__first_observed_time__": int64(0),
		"__last_observed_time__":  now,
	}, true
}

func relationPayloadFromStableKey(key string, now int64) (model.RelationPayload, bool) {
	parts := strings.Split(key, "/")
	if len(parts) != 7 {
		return nil, false
	}
	for _, part := range parts {
		if part == "" {
			return nil, false
		}
	}
	if !model.IsEntityID(parts[2]) || !model.IsEntityID(parts[6]) {
		return nil, false
	}
	return model.RelationPayload{
		"__src_domain__":          parts[0],
		"__src_entity_type__":     parts[1],
		"__src_entity_id__":       parts[2],
		"__relation_type__":       parts[3],
		"__dest_domain__":         parts[4],
		"__dest_entity_type__":    parts[5],
		"__dest_entity_id__":      parts[6],
		"__method__":              "Expire",
		"__first_observed_time__": int64(0),
		"__last_observed_time__":  now,
	}, true
}

func cloneWriteResult(result model.WriteResult) model.WriteResult {
	result.Items = append([]model.BatchItemResult(nil), result.Items...)
	for i := range result.Items {
		result.Items[i].Details = cloneErrorDetails(result.Items[i].Details)
	}
	return result
}

func cloneErrorDetails(details []model.ErrorDetail) []model.ErrorDetail {
	if details == nil {
		return nil
	}
	return append([]model.ErrorDetail(nil), details...)
}

func itemFailureError(entity string, failed int) error {
	return apperrors.New(apperrors.CodePartialFailed, fmt.Sprintf("%s batch contains %d failed item(s)", entity, failed))
}
