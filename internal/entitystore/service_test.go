package entitystore

import (
	"context"
	"testing"
	"time"

	"github.com/alibaba/MModel/internal/graphstore"
	"github.com/alibaba/MModel/internal/mmodel"
	querysvc "github.com/alibaba/MModel/internal/query"
	apperrors "github.com/alibaba/MModel/pkg/errors"
	"github.com/alibaba/MModel/pkg/model"
)

func TestWriteEntitiesValidatesCMS2Payload(t *testing.T) {
	ctx := context.Background()
	graph := graphstore.NewMemoryStore()
	svc := NewService(graph, mmodel.NewService(graph))

	_, err := svc.WriteEntities(ctx, "demo", model.EntityWriteBatch{
		Entities: []model.EntityPayload{{
			"__domain__":      "apm",
			"__entity_type__": "apm.service",
			"__entity_id__":   "54013ba69c196820e56801f1ef5aad54",
			"__method__":      "Update",
		}},
	})
	if !apperrors.IsCode(err, apperrors.CodeValidationFailed) {
		t.Fatalf("expected validation error for missing time fields, got %v", err)
	}

	_, err = svc.WriteEntities(ctx, "demo", model.EntityWriteBatch{
		Entities: []model.EntityPayload{validEntity("cart")},
	})
	if !apperrors.IsCode(err, apperrors.CodeValidationFailed) {
		t.Fatalf("expected validation error for non-hex entity id, got %v", err)
	}

	result, err := svc.WriteEntities(ctx, "demo", model.EntityWriteBatch{
		Entities: []model.EntityPayload{validEntity("54013ba69c196820e56801f1ef5aad54")},
	})
	if err != nil {
		t.Fatalf("write valid entity: %v", err)
	}
	if result.Accepted != 1 {
		t.Fatalf("expected accepted entity, got %+v", result)
	}
}

func TestWriteEntitiesPartialSuccessAndIdempotency(t *testing.T) {
	ctx := context.Background()
	graph := graphstore.NewMemoryStore()
	svc := NewService(graph, mmodel.NewService(graph))

	result, err := svc.WriteEntities(ctx, "demo", model.EntityWriteBatch{
		PartialSuccess: true,
		Entities: []model.EntityPayload{
			{
				"__domain__":      "apm",
				"__entity_type__": "apm.service",
				"__entity_id__":   "missing-time",
				"__method__":      "Create",
			},
			validEntityWithMethod("54013ba69c196820e56801f1ef5aad54", "Create"),
		},
	})
	if err != nil {
		t.Fatalf("partial write: %v", err)
	}
	if result.Accepted != 1 || result.Failed != 1 {
		t.Fatalf("expected partial success, got %+v", result)
	}
	if result.Items[1].OK || result.Items[1].Code != string(apperrors.CodeValidationFailed) {
		t.Fatalf("expected validation item error, got %+v", result.Items)
	}

	batch := model.EntityWriteBatch{
		IdempotencyKey: "create-cart",
		Entities:       []model.EntityPayload{validEntityWithMethod("177627f91af678a9b03e993f1a91917f", "Create")},
	}
	first, err := svc.WriteEntities(ctx, "demo", batch)
	if err != nil {
		t.Fatalf("first idempotent write: %v", err)
	}
	second, err := svc.WriteEntities(ctx, "demo", batch)
	if err != nil {
		t.Fatalf("second idempotent write: %v", err)
	}
	if first.Accepted != 1 || second.Accepted != 1 || second.Failed != 0 {
		t.Fatalf("expected cached idempotent result, first=%+v second=%+v", first, second)
	}

	conflict, err := svc.WriteEntities(ctx, "demo", model.EntityWriteBatch{
		PartialSuccess: true,
		Entities:       []model.EntityPayload{validEntityWithMethod("177627f91af678a9b03e993f1a91917f", "Create")},
	})
	if err != nil {
		t.Fatalf("duplicate create with partial success: %v", err)
	}
	if conflict.Failed != 1 || conflict.Items[0].Code != string(apperrors.CodeAlreadyExists) {
		t.Fatalf("expected duplicate create item failure, got %+v", conflict)
	}
}

func TestWriteEntitiesCRUDVisibilityThroughQuery(t *testing.T) {
	ctx := context.Background()
	graph := graphstore.NewMemoryStore()
	svc := NewService(graph, mmodel.NewService(graph))
	query := querysvc.NewService(graph)

	if _, err := svc.WriteEntities(ctx, "demo", model.EntityWriteBatch{
		Entities: []model.EntityPayload{entityWithFields("54013ba69c196820e56801f1ef5aad54", "Create", map[string]any{
			"display_name": "cart",
		})},
	}); err != nil {
		t.Fatalf("create entity: %v", err)
	}
	if _, err := svc.WriteEntities(ctx, "demo", model.EntityWriteBatch{
		Entities: []model.EntityPayload{entityWithFields("54013ba69c196820e56801f1ef5aad54", "Update", map[string]any{
			"__first_observed_time__": int64(999),
			"__last_observed_time__":  int64(300),
			"display_name":            "cart v2",
		})},
	}); err != nil {
		t.Fatalf("update entity: %v", err)
	}

	current, err := query.Execute(ctx, "demo", model.QueryRequest{Query: ".entity with(domain='apm', name='apm.service', query='cart v2') | limit 10"})
	if err != nil {
		t.Fatalf("query current entity: %v", err)
	}
	if len(current.Rows) != 1 {
		t.Fatalf("expected current entity row, got %+v", current.Rows)
	}
	if current.Rows[0]["__first_observed_time__"] != int64(100) {
		t.Fatalf("update should preserve first_observed_time, got %+v", current.Rows[0])
	}

	if _, err := svc.WriteEntities(ctx, "demo", model.EntityWriteBatch{
		Entities: []model.EntityPayload{entityWithFields("54013ba69c196820e56801f1ef5aad54", "Expire", map[string]any{
			"__last_observed_time__": int64(350),
		})},
	}); err != nil {
		t.Fatalf("expire entity: %v", err)
	}
	current, err = query.Execute(ctx, "demo", model.QueryRequest{Query: ".entity with(domain='apm', name='apm.service', query='cart') | limit 10"})
	if err != nil {
		t.Fatalf("query expired current entity: %v", err)
	}
	if len(current.Rows) != 0 {
		t.Fatalf("expired entity should be hidden from current query, got %+v", current.Rows)
	}

	from := time.Unix(150, 0)
	to := time.Unix(360, 0)
	historical, err := query.Execute(ctx, "demo", model.QueryRequest{
		Query:     ".entity with(domain='apm', name='apm.service', query='cart') | limit 10",
		TimeRange: model.TimeRange{From: &from, To: &to},
	})
	if err != nil {
		t.Fatalf("query historical entity: %v", err)
	}
	if len(historical.Rows) != 1 || historical.Rows[0]["__deleted__"] != true {
		t.Fatalf("expected expired entity to be historically visible, got %+v", historical.Rows)
	}

	if _, err := svc.WriteEntities(ctx, "demo", model.EntityWriteBatch{
		Entities: []model.EntityPayload{entityWithFields("12c500ed0b7879105fb46af0f246be87", "Create", nil)},
	}); err != nil {
		t.Fatalf("create deleted entity fixture: %v", err)
	}
	if _, err := svc.WriteEntities(ctx, "demo", model.EntityWriteBatch{
		Entities: []model.EntityPayload{entityWithFields("12c500ed0b7879105fb46af0f246be87", "Delete", map[string]any{
			"__last_observed_time__": int64(380),
		})},
	}); err != nil {
		t.Fatalf("delete entity: %v", err)
	}
	deleted, err := query.Execute(ctx, "demo", model.QueryRequest{
		Query:     ".entity with(domain='apm', name='apm.service', query='orders') | limit 10",
		TimeRange: model.TimeRange{From: &from, To: &to},
	})
	if err != nil {
		t.Fatalf("query deleted entity: %v", err)
	}
	if len(deleted.Rows) != 0 {
		t.Fatalf("deleted entity should stay hidden, got %+v", deleted.Rows)
	}
}

func TestExpireEntitiesUsesStableKey(t *testing.T) {
	ctx := context.Background()
	graph := graphstore.NewMemoryStore()
	svc := NewService(graph, mmodel.NewService(graph))

	if _, err := svc.WriteEntities(ctx, "demo", model.EntityWriteBatch{
		Entities: []model.EntityPayload{validEntityWithMethod("54013ba69c196820e56801f1ef5aad54", "Create")},
	}); err != nil {
		t.Fatalf("create entity: %v", err)
	}
	result, err := svc.ExpireEntities(ctx, "demo", model.ExpireRequest{IDs: []string{"apm/apm.service/54013ba69c196820e56801f1ef5aad54", "bad-key"}})
	if err != nil {
		t.Fatalf("expire entities: %v", err)
	}
	if result.Accepted != 1 || result.Failed != 1 {
		t.Fatalf("expected stable-key expire with one parse failure, got %+v", result)
	}
}

func TestWriteRelationsValidatesCMS2Payload(t *testing.T) {
	ctx := context.Background()
	graph := graphstore.NewMemoryStore()
	svc := NewService(graph, mmodel.NewService(graph))

	_, err := svc.WriteRelations(ctx, "demo", model.RelationWriteBatch{
		Relations: []model.RelationPayload{{
			"__src_domain__":      "apm",
			"__src_entity_type__": "apm.service",
			"__src_entity_id__":   "54013ba69c196820e56801f1ef5aad54",
		}},
	})
	if !apperrors.IsCode(err, apperrors.CodeValidationFailed) {
		t.Fatalf("expected validation error, got %v", err)
	}

	_, err = svc.WriteRelations(ctx, "demo", model.RelationWriteBatch{
		Relations: []model.RelationPayload{validRelation("cart", "checkout")},
	})
	if !apperrors.IsCode(err, apperrors.CodeValidationFailed) {
		t.Fatalf("expected validation error for non-hex relation entity ids, got %v", err)
	}

	result, err := svc.WriteRelations(ctx, "demo", model.RelationWriteBatch{
		Relations: []model.RelationPayload{validRelation("54013ba69c196820e56801f1ef5aad54", "177627f91af678a9b03e993f1a91917f")},
	})
	if err != nil {
		t.Fatalf("write valid relation: %v", err)
	}
	if result.Accepted != 1 {
		t.Fatalf("expected accepted relation, got %+v", result)
	}
}

func TestWriteRelationsPartialSuccessAndIdempotency(t *testing.T) {
	ctx := context.Background()
	graph := graphstore.NewMemoryStore()
	svc := NewService(graph, mmodel.NewService(graph))

	result, err := svc.WriteRelations(ctx, "demo", model.RelationWriteBatch{
		PartialSuccess: true,
		Relations: []model.RelationPayload{
			{
				"__src_domain__":      "apm",
				"__src_entity_type__": "apm.service",
				"__src_entity_id__":   "54013ba69c196820e56801f1ef5aad54",
				"__relation_type__":   "calls",
			},
			relationWithFields("54013ba69c196820e56801f1ef5aad54", "177627f91af678a9b03e993f1a91917f", "Create", nil),
		},
	})
	if err != nil {
		t.Fatalf("partial relation write: %v", err)
	}
	if result.Accepted != 1 || result.Failed != 1 {
		t.Fatalf("expected relation partial success, got %+v", result)
	}

	batch := model.RelationWriteBatch{
		IdempotencyKey: "create-relation",
		Relations:      []model.RelationPayload{relationWithFields("177627f91af678a9b03e993f1a91917f", "8efdd10756595e9a58dc3d7fee6f53ee", "Create", nil)},
	}
	first, err := svc.WriteRelations(ctx, "demo", batch)
	if err != nil {
		t.Fatalf("first relation idempotent write: %v", err)
	}
	second, err := svc.WriteRelations(ctx, "demo", batch)
	if err != nil {
		t.Fatalf("second relation idempotent write: %v", err)
	}
	if first.Accepted != 1 || second.Accepted != 1 || second.Failed != 0 {
		t.Fatalf("expected cached relation idempotent result, first=%+v second=%+v", first, second)
	}

	conflict, err := svc.WriteRelations(ctx, "demo", model.RelationWriteBatch{
		PartialSuccess: true,
		Relations:      []model.RelationPayload{relationWithFields("177627f91af678a9b03e993f1a91917f", "8efdd10756595e9a58dc3d7fee6f53ee", "Create", nil)},
	})
	if err != nil {
		t.Fatalf("duplicate relation create with partial success: %v", err)
	}
	if conflict.Failed != 1 || conflict.Items[0].Code != string(apperrors.CodeAlreadyExists) {
		t.Fatalf("expected duplicate relation item failure, got %+v", conflict)
	}
}

func TestWriteRelationsCRUDVisibilityThroughQuery(t *testing.T) {
	ctx := context.Background()
	graph := graphstore.NewMemoryStore()
	svc := NewService(graph, mmodel.NewService(graph))
	query := querysvc.NewService(graph)

	if _, err := svc.WriteRelations(ctx, "demo", model.RelationWriteBatch{
		Relations: []model.RelationPayload{relationWithFields("54013ba69c196820e56801f1ef5aad54", "177627f91af678a9b03e993f1a91917f", "Create", map[string]any{
			"weight": int64(1),
		})},
	}); err != nil {
		t.Fatalf("create relation: %v", err)
	}
	if _, err := svc.WriteRelations(ctx, "demo", model.RelationWriteBatch{
		Relations: []model.RelationPayload{relationWithFields("54013ba69c196820e56801f1ef5aad54", "177627f91af678a9b03e993f1a91917f", "Update", map[string]any{
			"__last_observed_time__": int64(300),
			"weight":                 int64(2),
		})},
	}); err != nil {
		t.Fatalf("update relation: %v", err)
	}
	current, err := query.Execute(ctx, "demo", model.QueryRequest{Query: ".topo with(relation_type='calls') | limit 10"})
	if err != nil {
		t.Fatalf("query current topo: %v", err)
	}
	if len(current.Rows) != 1 || current.Rows[0]["weight"] != int64(2) {
		t.Fatalf("unexpected current topo rows: %+v", current.Rows)
	}

	if _, err := svc.WriteRelations(ctx, "demo", model.RelationWriteBatch{
		Relations: []model.RelationPayload{relationWithFields("54013ba69c196820e56801f1ef5aad54", "177627f91af678a9b03e993f1a91917f", "Expire", map[string]any{
			"__last_observed_time__": int64(350),
		})},
	}); err != nil {
		t.Fatalf("expire relation: %v", err)
	}
	current, err = query.Execute(ctx, "demo", model.QueryRequest{Query: ".topo with(relation_type='calls') | limit 10"})
	if err != nil {
		t.Fatalf("query expired topo: %v", err)
	}
	if len(current.Rows) != 0 {
		t.Fatalf("expired relation should be hidden from current query, got %+v", current.Rows)
	}

	from := time.Unix(150, 0)
	to := time.Unix(360, 0)
	historical, err := query.Execute(ctx, "demo", model.QueryRequest{
		Query:     ".topo with(relation_type='calls') | limit 10",
		TimeRange: model.TimeRange{From: &from, To: &to},
	})
	if err != nil {
		t.Fatalf("query historical topo: %v", err)
	}
	if len(historical.Rows) != 1 || historical.Rows[0]["__deleted__"] != true {
		t.Fatalf("expected expired relation to be historically visible, got %+v", historical.Rows)
	}

	if _, err := svc.WriteRelations(ctx, "demo", model.RelationWriteBatch{
		Relations: []model.RelationPayload{relationWithFields("54013ba69c196820e56801f1ef5aad54", "12c500ed0b7879105fb46af0f246be87", "Create", nil)},
	}); err != nil {
		t.Fatalf("create deleted relation fixture: %v", err)
	}
	if _, err := svc.WriteRelations(ctx, "demo", model.RelationWriteBatch{
		Relations: []model.RelationPayload{relationWithFields("54013ba69c196820e56801f1ef5aad54", "12c500ed0b7879105fb46af0f246be87", "Delete", map[string]any{
			"__last_observed_time__": int64(380),
		})},
	}); err != nil {
		t.Fatalf("delete relation: %v", err)
	}
	historical, err = query.Execute(ctx, "demo", model.QueryRequest{
		Query:     ".topo with(relation_type='calls') | limit 10",
		TimeRange: model.TimeRange{From: &from, To: &to},
	})
	if err != nil {
		t.Fatalf("query deleted topo: %v", err)
	}
	if len(historical.Rows) != 1 {
		t.Fatalf("deleted relation should stay hidden; expected only expired relation, got %+v", historical.Rows)
	}

	result, err := svc.ExpireRelations(ctx, "demo", model.ExpireRequest{IDs: []string{"apm/apm.service/54013ba69c196820e56801f1ef5aad54/calls/apm/apm.service/177627f91af678a9b03e993f1a91917f", "bad-key"}})
	if err != nil {
		t.Fatalf("expire relations by stable key: %v", err)
	}
	if result.Failed != 1 {
		t.Fatalf("expected malformed relation stable key failure, got %+v", result)
	}
}

func TestRunTTLDoesNotMutateWithoutExpiredData(t *testing.T) {
	ctx := context.Background()
	graph := graphstore.NewMemoryStore()
	svc := NewService(graph, mmodel.NewService(graph))

	result, err := svc.RunTTL(ctx, "demo", time.Unix(1_000, 0))
	if err != nil {
		t.Fatalf("run ttl: %v", err)
	}
	if result.Accepted != 0 || result.Failed != 0 {
		t.Fatalf("ttl run should not mutate without expired data, got %+v", result)
	}
}

func validEntity(id string) model.EntityPayload {
	return validEntityWithMethod(id, "Update")
}

func validEntityWithMethod(id, method string) model.EntityPayload {
	return model.EntityPayload{
		"__domain__":              "apm",
		"__entity_type__":         "apm.service",
		"__entity_id__":           id,
		"__method__":              method,
		"__first_observed_time__": int64(100),
		"__last_observed_time__":  int64(200),
	}
}

func entityWithFields(id, method string, fields map[string]any) model.EntityPayload {
	payload := validEntityWithMethod(id, method)
	for key, value := range fields {
		payload[key] = value
	}
	return payload
}

func validRelation(src, dest string) model.RelationPayload {
	return relationWithFields(src, dest, "Update", nil)
}

func relationWithFields(src, dest, method string, fields map[string]any) model.RelationPayload {
	payload := model.RelationPayload{
		"__src_domain__":          "apm",
		"__src_entity_type__":     "apm.service",
		"__src_entity_id__":       src,
		"__dest_domain__":         "apm",
		"__dest_entity_type__":    "apm.service",
		"__dest_entity_id__":      dest,
		"__relation_type__":       "calls",
		"__method__":              method,
		"__first_observed_time__": int64(100),
		"__last_observed_time__":  int64(200),
	}
	for key, value := range fields {
		payload[key] = value
	}
	return payload
}
