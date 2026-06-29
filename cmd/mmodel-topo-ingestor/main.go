// mmodel-topo-ingestor discovers service topology from OpenTelemetry trace
// data stored in OpenSearch and writes it into MModel's EntityStore with
// proper lifecycle timestamps (F/L/K/D fields).
//
// Usage:
//
//	go run ./cmd/mmodel-topo-ingestor --addr http://localhost:8080 --workspace otel-demo
//
// The ingestor runs continuously, scanning every 60s by default.
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/alibaba/MModel/internal/otel"
	"github.com/alibaba/MModel/pkg/model"

	"bytes"
	"encoding/json"
	"io"
	"net/http"
)

var (
	addr      = flag.String("addr", "http://localhost:8080", "MModel server address")
	workspace = flag.String("workspace", "otel-demo", "MModel workspace ID")
	osEndpoint = flag.String("os-endpoint", "http://localhost:13121", "OpenSearch endpoint")
	osUser    = flag.String("os-user", "admin", "OpenSearch username")
	osPass    = flag.String("os-pass", "MorenMima@123456", "OpenSearch password")
	interval  = flag.Duration("interval", 60*time.Second, "scan interval")
	once      = flag.Bool("once", false, "run once and exit")
)

// restEntityWriter implements otel.EntityWriter via the MModel REST API.
type restEntityWriter struct {
	baseURL string
	client  *http.Client
}

func newRESTWriter(addr string) *restEntityWriter {
	return &restEntityWriter{
		baseURL: addr,
		client:  &http.Client{Timeout: 30 * time.Second},
	}
}

func (w *restEntityWriter) WriteEntities(ctx context.Context, ws string, batch model.EntityWriteBatch) (model.WriteResult, error) {
	url := fmt.Sprintf("%s/api/v1/entitystore/%s/entities:write", w.baseURL, ws)
	return w.post(ctx, url, batch)
}

func (w *restEntityWriter) WriteRelations(ctx context.Context, ws string, batch model.RelationWriteBatch) (model.WriteResult, error) {
	url := fmt.Sprintf("%s/api/v1/entitystore/%s/relations:write", w.baseURL, ws)
	return w.post(ctx, url, batch)
}

// LookupEntityByName queries MModel for an existing entity by display_name
// and returns its entity ID if found. Uses exact match on display_name to
// avoid false positives from the text-search query parameter.
func (w *restEntityWriter) LookupEntityByName(ctx context.Context, ws, domain, entitySet, displayName string) (string, bool, error) {
	queryBody := map[string]any{
		"query": fmt.Sprintf(".entity with(domain='%s', name='%s') | project __entity_id__,display_name | limit 100",
			domain, entitySet),
	}
	b, err := json.Marshal(queryBody)
	if err != nil {
		return "", false, err
	}
	url := fmt.Sprintf("%s/api/v1/query/%s/execute", w.baseURL, ws)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(b))
	if err != nil {
		return "", false, err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := w.client.Do(req)
	if err != nil {
		return "", false, fmt.Errorf("lookup query: %w", err)
	}
	defer resp.Body.Close()

	bodyBytes, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		return "", false, fmt.Errorf("lookup HTTP %d: %s", resp.StatusCode, string(bodyBytes))
	}

	var qr struct {
		Rows []struct {
			EntityID    string `json:"__entity_id__"`
			DisplayName string `json:"display_name"`
		} `json:"rows"`
	}
	if err := json.Unmarshal(bodyBytes, &qr); err != nil {
		return "", false, fmt.Errorf("decode lookup: %w", err)
	}
	// Exact match on display_name — query parameter does fuzzy search.
	for _, row := range qr.Rows {
		if row.DisplayName == displayName {
			return row.EntityID, true, nil
		}
	}
	return "", false, nil
}

func (w *restEntityWriter) post(ctx context.Context, url string, body any) (model.WriteResult, error) {
	b, err := json.Marshal(body)
	if err != nil {
		return model.WriteResult{}, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(b))
	if err != nil {
		return model.WriteResult{}, err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := w.client.Do(req)
	if err != nil {
		return model.WriteResult{}, fmt.Errorf("REST call: %w", err)
	}
	defer resp.Body.Close()

	var wr model.WriteResult
	if err := json.NewDecoder(resp.Body).Decode(&wr); err != nil {
		return model.WriteResult{}, fmt.Errorf("decode response: %w", err)
	}
	if resp.StatusCode >= 400 {
		return wr, fmt.Errorf("REST error %d: accepted=%d failed=%d", resp.StatusCode, wr.Accepted, wr.Failed)
	}
	return wr, nil
}

func main() {
	flag.Parse()

	cfg := otel.DefaultConfig()
	cfg.OpenSearchEndpoint = *osEndpoint
	cfg.Username = *osUser
	cfg.Password = *osPass
	cfg.Workspace = *workspace
	cfg.ScanInterval = *interval

	store := newRESTWriter(*addr)
	ing := otel.NewIngestor(cfg, store)

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	runOne := func() {
		result, err := ing.Ingest(ctx)
		if err != nil {
			log.Printf("ERROR: ingest: %v", err)
			return
		}
		log.Printf("OK: %s", result.Summary())
		for _, p := range result.Relations {
			log.Printf("  %s -> %s", p.Caller, p.Callee)
		}
	}

	runOne()
	if *once {
		os.Exit(0)
	}

	ticker := time.NewTicker(cfg.ScanInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			log.Println("shutting down")
			return
		case <-ticker.C:
			runOne()
		}
	}
}
