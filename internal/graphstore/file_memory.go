package graphstore

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"

	"github.com/alibaba/MModel/pkg/model"
)

const fileMemoryStateVersion = 1

type FileMemoryStore struct {
	*MemoryStore
	root       string
	legacyPath string
	persistMu  sync.Mutex
}

type fileMemoryState struct {
	Version   int                                         `json:"version"`
	MModels   map[string]map[string]model.MModelElement   `json:"mmodels,omitempty"`
	Entities  map[string]map[string]model.EntityPayload   `json:"entities,omitempty"`
	Relations map[string]map[string]model.RelationPayload `json:"relations,omitempty"`
}

type fileMemoryCollection[T any] struct {
	Version int          `json:"version"`
	Items   map[string]T `json:"items,omitempty"`
}

type fileMemoryWorkspaceState struct {
	MModels   map[string]model.MModelElement
	Entities  map[string]model.EntityPayload
	Relations map[string]model.RelationPayload
}

func NewFileMemoryStore(config ProviderConfig) (*FileMemoryStore, error) {
	root, legacyPath := fileMemoryPaths(config)
	store := &FileMemoryStore{
		MemoryStore: NewMemoryStore(),
		root:        root,
		legacyPath:  legacyPath,
	}
	loadedLegacy, err := store.load()
	if err != nil {
		return nil, err
	}
	if loadedLegacy {
		if err := store.persistAll(); err != nil {
			return nil, err
		}
	}
	return store, nil
}

func (s *FileMemoryStore) OpenWorkspace(ctx context.Context, workspace model.WorkspaceMetadata) error {
	s.persistMu.Lock()
	defer s.persistMu.Unlock()

	if err := s.MemoryStore.OpenWorkspace(ctx, workspace); err != nil {
		return err
	}
	return s.persistWorkspaceLocked(workspace.ID)
}

func (s *FileMemoryStore) EnsureSchema(ctx context.Context, workspace string) error {
	s.persistMu.Lock()
	defer s.persistMu.Unlock()

	if err := s.MemoryStore.EnsureSchema(ctx, workspace); err != nil {
		return err
	}
	return s.persistWorkspaceLocked(workspace)
}

func (s *FileMemoryStore) PutMModelElements(ctx context.Context, batch model.MModelElementBatch) (model.WriteResult, error) {
	s.persistMu.Lock()
	defer s.persistMu.Unlock()

	result, err := s.MemoryStore.PutMModelElements(ctx, batch)
	if err != nil {
		return result, err
	}
	if err := s.persistWorkspaceLocked(batch.Workspace); err != nil {
		return result, err
	}
	return result, nil
}

func (s *FileMemoryStore) GetMModelSnapshot(ctx context.Context, req model.MModelSnapshotRequest) (model.MModelSnapshot, error) {
	snapshot, err := s.MemoryStore.GetMModelSnapshot(ctx, req)
	if err != nil {
		return snapshot, err
	}
	if req.Version == "" {
		snapshot.Version = ProviderTypeFileMemory
	}
	return snapshot, nil
}

func (s *FileMemoryStore) WriteEntities(ctx context.Context, batch model.EntityWriteBatch) (model.WriteResult, error) {
	s.persistMu.Lock()
	defer s.persistMu.Unlock()

	result, err := s.MemoryStore.WriteEntities(ctx, batch)
	if err != nil {
		return result, err
	}
	if err := s.persistWorkspaceLocked(batch.Workspace); err != nil {
		return result, err
	}
	return result, nil
}

func (s *FileMemoryStore) WriteRelations(ctx context.Context, batch model.RelationWriteBatch) (model.WriteResult, error) {
	s.persistMu.Lock()
	defer s.persistMu.Unlock()

	result, err := s.MemoryStore.WriteRelations(ctx, batch)
	if err != nil {
		return result, err
	}
	if err := s.persistWorkspaceLocked(batch.Workspace); err != nil {
		return result, err
	}
	return result, nil
}

func (s *FileMemoryStore) Health(ctx context.Context) (model.GraphStoreHealth, error) {
	return model.GraphStoreHealth{Provider: ProviderTypeFileMemory, Status: "ok"}, nil
}

func (s *FileMemoryStore) load() (bool, error) {
	loadedDirectory, err := s.loadDirectory()
	if err != nil {
		return false, err
	}
	if loadedDirectory {
		return false, nil
	}
	return s.loadLegacyFile()
}

func (s *FileMemoryStore) loadDirectory() (bool, error) {
	workspacesRoot := filepath.Join(s.root, "workspaces")
	entries, err := os.ReadDir(workspacesRoot)
	if err != nil {
		if os.IsNotExist(err) {
			return false, nil
		}
		return false, fmt.Errorf("read file memory graphstore workspace directory: %w", err)
	}

	mmodels := make(map[string]map[string]model.MModelElement)
	entities := make(map[string]map[string]model.EntityPayload)
	relations := make(map[string]map[string]model.RelationPayload)
	loaded := false
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		workspace, err := url.PathUnescape(entry.Name())
		if err != nil {
			workspace = entry.Name()
		}
		workspaceDir := filepath.Join(workspacesRoot, entry.Name())

		mmodelItems, hasMModels, err := readMModelCollection(workspaceDir)
		if err != nil {
			return false, err
		}
		entityItems, hasEntities, err := readFileMemoryCollection[model.EntityPayload](filepath.Join(workspaceDir, "entities.json"))
		if err != nil {
			return false, err
		}
		relationItems, hasRelations, err := readFileMemoryCollection[model.RelationPayload](filepath.Join(workspaceDir, "relations.json"))
		if err != nil {
			return false, err
		}
		if !hasMModels && !hasEntities && !hasRelations {
			continue
		}

		loaded = true
		mmodels[workspace] = normalizeMModelMap(mmodelItems)
		entities[workspace] = normalizeEntityMap(entityItems)
		relations[workspace] = normalizeRelationMap(relationItems)
	}
	if !loaded {
		return false, nil
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	s.mmodels = mmodels
	s.entities = entities
	s.relations = relations
	s.ensureMapsLocked()
	return true, nil
}

func (s *FileMemoryStore) loadLegacyFile() (bool, error) {
	data, err := os.ReadFile(s.legacyPath)
	if err != nil {
		if os.IsNotExist(err) {
			return false, nil
		}
		return false, fmt.Errorf("read legacy file memory graphstore state: %w", err)
	}
	if len(bytes.TrimSpace(data)) == 0 {
		return false, nil
	}

	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	var state fileMemoryState
	if err := decoder.Decode(&state); err != nil {
		return false, fmt.Errorf("decode legacy file memory graphstore state: %w", err)
	}
	if state.Version != 0 && state.Version != fileMemoryStateVersion {
		return false, fmt.Errorf("unsupported file memory graphstore state version %d", state.Version)
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	s.mmodels = normalizeMModelWorkspaceMap(state.MModels)
	s.entities = normalizeEntityWorkspaceMap(state.Entities)
	s.relations = normalizeRelationWorkspaceMap(state.Relations)
	s.ensureMapsLocked()
	return true, nil
}

func (s *FileMemoryStore) persistAll() error {
	s.persistMu.Lock()
	defer s.persistMu.Unlock()

	for _, workspace := range s.workspaceNames() {
		if err := s.persistWorkspaceLocked(workspace); err != nil {
			return err
		}
	}
	return nil
}

func (s *FileMemoryStore) persistWorkspaceLocked(workspace string) error {
	if workspace == "" {
		return nil
	}
	state := s.snapshotWorkspace(workspace)
	workspaceDir := s.workspaceDir(workspace)
	if err := os.MkdirAll(workspaceDir, 0o755); err != nil {
		return fmt.Errorf("create file memory graphstore workspace directory: %w", err)
	}
	if err := writeFileMemoryCollection(filepath.Join(workspaceDir, "mmodels.json"), state.MModels); err != nil {
		return err
	}
	if err := writeFileMemoryCollection(filepath.Join(workspaceDir, "entities.json"), state.Entities); err != nil {
		return err
	}
	if err := writeFileMemoryCollection(filepath.Join(workspaceDir, "relations.json"), state.Relations); err != nil {
		return err
	}
	return nil
}

func (s *FileMemoryStore) snapshotWorkspace(workspace string) fileMemoryWorkspaceState {
	s.mu.RLock()
	defer s.mu.RUnlock()

	return fileMemoryWorkspaceState{
		MModels:   cloneMModelMap(s.mmodels[workspace]),
		Entities:  cloneEntityMap(s.entities[workspace]),
		Relations: cloneRelationMap(s.relations[workspace]),
	}
}

func (s *FileMemoryStore) workspaceNames() []string {
	s.mu.RLock()
	defer s.mu.RUnlock()

	names := make(map[string]struct{})
	for workspace := range s.mmodels {
		names[workspace] = struct{}{}
	}
	for workspace := range s.entities {
		names[workspace] = struct{}{}
	}
	for workspace := range s.relations {
		names[workspace] = struct{}{}
	}

	out := make([]string, 0, len(names))
	for workspace := range names {
		out = append(out, workspace)
	}
	sort.Strings(out)
	return out
}

func (s *FileMemoryStore) workspaceDir(workspace string) string {
	return filepath.Join(s.root, "workspaces", url.PathEscape(workspace))
}

func (s *FileMemoryStore) ensureMapsLocked() {
	if s.mmodels == nil {
		s.mmodels = make(map[string]map[string]model.MModelElement)
	}
	if s.entities == nil {
		s.entities = make(map[string]map[string]model.EntityPayload)
	}
	if s.relations == nil {
		s.relations = make(map[string]map[string]model.RelationPayload)
	}
}

func fileMemoryPaths(config ProviderConfig) (string, string) {
	if config.Options != nil && config.Options["path"] != "" {
		path := config.Options["path"]
		if strings.HasSuffix(path, ".json") {
			return strings.TrimSuffix(path, ".json"), path
		}
		return path, path + ".json"
	}
	root := config.DataRoot
	if root == "" {
		root = "data"
	}
	base := filepath.Join(root, "graphstore")
	return filepath.Join(base, "file-memory"), filepath.Join(base, "file-memory.json")
}

func readFileMemoryCollection[T any](path string) (map[string]T, bool, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, false, nil
		}
		return nil, false, fmt.Errorf("read file memory graphstore collection %s: %w", path, err)
	}
	if len(bytes.TrimSpace(data)) == 0 {
		return map[string]T{}, true, nil
	}

	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	var collection fileMemoryCollection[T]
	if err := decoder.Decode(&collection); err != nil {
		return nil, false, fmt.Errorf("decode file memory graphstore collection %s: %w", path, err)
	}
	if collection.Version != 0 && collection.Version != fileMemoryStateVersion {
		return nil, false, fmt.Errorf("unsupported file memory graphstore collection version %d in %s", collection.Version, path)
	}
	if collection.Items == nil {
		collection.Items = make(map[string]T)
	}
	return collection.Items, true, nil
}

func readMModelCollection(workspaceDir string) (map[string]model.MModelElement, bool, error) {
	items, ok, err := readFileMemoryCollection[model.MModelElement](filepath.Join(workspaceDir, "mmodels.json"))
	if err != nil || ok {
		return items, ok, err
	}
	return readFileMemoryCollection[model.MModelElement](filepath.Join(workspaceDir, "umodels.json"))
}

func writeFileMemoryCollection[T any](path string, items map[string]T) error {
	if items == nil {
		items = make(map[string]T)
	}
	data, err := json.MarshalIndent(fileMemoryCollection[T]{
		Version: fileMemoryStateVersion,
		Items:   items,
	}, "", "  ")
	if err != nil {
		return fmt.Errorf("encode file memory graphstore collection %s: %w", path, err)
	}

	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, append(data, '\n'), 0o644); err != nil {
		return fmt.Errorf("write file memory graphstore collection %s: %w", path, err)
	}
	if err := os.Rename(tmp, path); err != nil {
		return fmt.Errorf("replace file memory graphstore collection %s: %w", path, err)
	}
	return nil
}

func cloneMModelWorkspaceMap(source map[string]map[string]model.MModelElement) map[string]map[string]model.MModelElement {
	if source == nil {
		return nil
	}
	target := make(map[string]map[string]model.MModelElement, len(source))
	for workspace, elements := range source {
		target[workspace] = cloneMModelMap(elements)
	}
	return target
}

func normalizeMModelWorkspaceMap(source map[string]map[string]model.MModelElement) map[string]map[string]model.MModelElement {
	if source == nil {
		return nil
	}
	target := make(map[string]map[string]model.MModelElement, len(source))
	for workspace, elements := range source {
		target[workspace] = normalizeMModelMap(elements)
	}
	return target
}

func cloneMModelMap(source map[string]model.MModelElement) map[string]model.MModelElement {
	if source == nil {
		return nil
	}
	target := make(map[string]model.MModelElement, len(source))
	for key, element := range source {
		target[key] = cloneMModelElement(element)
	}
	return target
}

func normalizeMModelMap(source map[string]model.MModelElement) map[string]model.MModelElement {
	if source == nil {
		return nil
	}
	target := make(map[string]model.MModelElement, len(source))
	for key, element := range source {
		element.Spec = normalizeJSONMap(element.Spec)
		if elementKey := model.MModelElementKey(element); elementKey != "" {
			key = elementKey
		}
		target[key] = element
	}
	return target
}

func cloneEntityWorkspaceMap(source map[string]map[string]model.EntityPayload) map[string]map[string]model.EntityPayload {
	if source == nil {
		return nil
	}
	target := make(map[string]map[string]model.EntityPayload, len(source))
	for workspace, entities := range source {
		target[workspace] = cloneEntityMap(entities)
	}
	return target
}

func cloneRelationWorkspaceMap(source map[string]map[string]model.RelationPayload) map[string]map[string]model.RelationPayload {
	if source == nil {
		return nil
	}
	target := make(map[string]map[string]model.RelationPayload, len(source))
	for workspace, relations := range source {
		target[workspace] = cloneRelationMap(relations)
	}
	return target
}

func normalizeEntityWorkspaceMap(source map[string]map[string]model.EntityPayload) map[string]map[string]model.EntityPayload {
	if source == nil {
		return nil
	}
	target := make(map[string]map[string]model.EntityPayload, len(source))
	for workspace, entities := range source {
		target[workspace] = normalizeEntityMap(entities)
	}
	return target
}

func normalizeRelationWorkspaceMap(source map[string]map[string]model.RelationPayload) map[string]map[string]model.RelationPayload {
	if source == nil {
		return nil
	}
	target := make(map[string]map[string]model.RelationPayload, len(source))
	for workspace, relations := range source {
		target[workspace] = normalizeRelationMap(relations)
	}
	return target
}

func cloneEntityMap(source map[string]model.EntityPayload) map[string]model.EntityPayload {
	if source == nil {
		return nil
	}
	target := make(map[string]model.EntityPayload, len(source))
	for key, payload := range source {
		target[key] = cloneEntityPayload(payload)
	}
	return target
}

func cloneRelationMap(source map[string]model.RelationPayload) map[string]model.RelationPayload {
	if source == nil {
		return nil
	}
	target := make(map[string]model.RelationPayload, len(source))
	for key, payload := range source {
		target[key] = cloneRelationPayload(payload)
	}
	return target
}

func normalizeEntityMap(source map[string]model.EntityPayload) map[string]model.EntityPayload {
	if source == nil {
		return nil
	}
	target := make(map[string]model.EntityPayload, len(source))
	for key, payload := range source {
		target[key] = model.EntityPayload(normalizeJSONMap(map[string]any(payload)))
	}
	return target
}

func normalizeRelationMap(source map[string]model.RelationPayload) map[string]model.RelationPayload {
	if source == nil {
		return nil
	}
	target := make(map[string]model.RelationPayload, len(source))
	for key, payload := range source {
		target[key] = model.RelationPayload(normalizeJSONMap(map[string]any(payload)))
	}
	return target
}

func normalizeJSONMap(source map[string]any) map[string]any {
	if source == nil {
		return nil
	}
	target := make(map[string]any, len(source))
	for key, value := range source {
		target[key] = normalizeJSONValue(value)
	}
	return target
}

func normalizeJSONValue(value any) any {
	switch typed := value.(type) {
	case json.Number:
		if n, err := typed.Int64(); err == nil {
			return n
		}
		if n, err := typed.Float64(); err == nil {
			return n
		}
		return typed.String()
	case map[string]any:
		return normalizeJSONMap(typed)
	case []any:
		out := make([]any, len(typed))
		for i, item := range typed {
			out[i] = normalizeJSONValue(item)
		}
		return out
	default:
		return value
	}
}
