package mmodel

import (
	"strings"

	"github.com/alibaba/MModel/pkg/model"
)

type schemaIndex struct {
	byKey            map[string]model.MModelElement
	byKindDomainName map[string]model.MModelElement
}

func newSchemaIndex(elements []model.MModelElement) *schemaIndex {
	idx := &schemaIndex{
		byKey:            make(map[string]model.MModelElement),
		byKindDomainName: make(map[string]model.MModelElement),
	}
	for _, element := range elements {
		idx.add(element)
	}
	return idx
}

func (idx *schemaIndex) add(element model.MModelElement) {
	element = cloneElement(element)
	if key := model.MModelElementKey(element); key != "" {
		idx.byKey[key] = element
	}
	if element.Kind != "" && element.Domain != "" && element.Name != "" {
		idx.byKindDomainName[indexKey(element.Kind, element.Domain, element.Name)] = element
	}
}

func (idx *schemaIndex) find(kind, domain, name string) (model.MModelElement, bool) {
	element, ok := idx.byKindDomainName[indexKey(kind, domain, name)]
	return cloneElement(element), ok
}

func (s *Service) mergeIndex(workspace string, elements []model.MModelElement) {
	s.mu.Lock()
	defer s.mu.Unlock()
	idx := s.indexes[workspace]
	if idx == nil {
		idx = newSchemaIndex(nil)
		s.indexes[workspace] = idx
	}
	for _, element := range elements {
		idx.add(element)
	}
}

func (s *Service) replaceIndex(workspace string, elements []model.MModelElement) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.indexes[workspace] = newSchemaIndex(elements)
}

func (s *Service) findIndexedElement(kind, domain, name string) (model.MModelElement, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	for _, idx := range s.indexes {
		if element, ok := idx.find(kind, domain, name); ok {
			return element, true
		}
	}
	return model.MModelElement{}, false
}

func (s *Service) findIndexedRelation(ref model.RelationTypeRef) (model.MModelElement, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	for _, idx := range s.indexes {
		for _, element := range idx.byKey {
			if element.Kind != "entity_set_link" {
				continue
			}
			if ref.Domain != "" && element.Domain != ref.Domain {
				continue
			}
			if relationTypeOf(element) == ref.Type {
				return cloneElement(element), true
			}
		}
	}
	return model.MModelElement{}, false
}

func indexKey(kind, domain, name string) string {
	return strings.Join([]string{kind, domain, name}, "\x00")
}

func relationTypeOf(element model.MModelElement) string {
	if value, ok := element.Spec["entity_link_type"].(string); ok {
		return value
	}
	if value, ok := element.Spec["relation_type"].(string); ok {
		return value
	}
	if value, ok := element.Spec["type"].(string); ok {
		return value
	}
	name := element.Name
	for _, token := range []string{"_calls_", "_contains_", "_instance_of_", "_parent_of_", "_same_as_"} {
		if strings.Contains(name, token) {
			return strings.Trim(token, "_")
		}
	}
	return ""
}

func fieldMapFromElement(element model.MModelElement) map[string]any {
	fields, ok := element.Spec["fields"].([]any)
	if !ok {
		return nil
	}
	out := make(map[string]any)
	for _, rawField := range fields {
		field, ok := rawField.(map[string]any)
		if !ok {
			continue
		}
		name, _ := field["name"].(string)
		if name == "" {
			continue
		}
		out[name] = cloneAny(field)
	}
	if len(out) == 0 {
		return nil
	}
	return out
}

func cloneElement(element model.MModelElement) model.MModelElement {
	element.Spec = cloneMapRecursive(element.Spec)
	return element
}

func cloneMapRecursive(source map[string]any) map[string]any {
	if source == nil {
		return nil
	}
	target := make(map[string]any, len(source))
	for key, value := range source {
		target[key] = cloneAny(value)
	}
	return target
}

func cloneAny(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return cloneMapRecursive(typed)
	case []any:
		out := make([]any, len(typed))
		for i, item := range typed {
			out[i] = cloneAny(item)
		}
		return out
	default:
		return typed
	}
}
