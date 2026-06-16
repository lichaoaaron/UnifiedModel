package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"sync/atomic"

	"github.com/alibaba/MModel/internal/bootstrap"
)

type sseBroker struct {
	next     uint64
	mu       sync.Mutex
	sessions map[string]chan rpcResponse
}

func serveHTTP(ctx context.Context, app *bootstrap.App, defaultWorkspace, addr, mcpPath string, errOut io.Writer) error {
	if !strings.HasPrefix(mcpPath, "/") {
		mcpPath = "/" + mcpPath
	}
	broker := &sseBroker{sessions: map[string]chan rpcResponse{}}
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
	})
	mux.HandleFunc(mcpPath, streamableHTTPHandler(ctx, app, defaultWorkspace))
	mux.HandleFunc("/sse", legacySSEHandler(broker))
	mux.HandleFunc("/messages", legacyMessageHandler(ctx, app, defaultWorkspace, broker))

	server := &http.Server{Addr: addr, Handler: mux}
	go func() {
		<-ctx.Done()
		_ = server.Close()
	}()
	fmt.Fprintf(errOut, "mmodel-mcp HTTP listening on http://%s%s\n", addr, mcpPath)
	err := server.ListenAndServe()
	if err == http.ErrServerClosed {
		return nil
	}
	return err
}

func streamableHTTPHandler(ctx context.Context, app *bootstrap.App, defaultWorkspace string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if !validOrigin(r) {
			http.Error(w, "invalid Origin", http.StatusForbidden)
			return
		}
		if !validProtocolVersionHeader(r) {
			http.Error(w, "unsupported MCP protocol version", http.StatusBadRequest)
			return
		}
		switch r.Method {
		case http.MethodPost:
			handleHTTPRPC(ctx, app, defaultWorkspace, w, r)
		case http.MethodGet:
			w.Header().Set("Content-Type", "text/event-stream")
			w.Header().Set("Cache-Control", "no-cache")
			w.Header().Set("Connection", "keep-alive")
			_, _ = fmt.Fprint(w, ": mmodel-mcp stream ready\n\n")
			if flusher, ok := w.(http.Flusher); ok {
				flusher.Flush()
			}
			<-r.Context().Done()
		case http.MethodDelete:
			w.WriteHeader(http.StatusAccepted)
		default:
			w.Header().Set("Allow", "GET, POST, DELETE")
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	}
}

func handleHTTPRPC(ctx context.Context, app *bootstrap.App, defaultWorkspace string, w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	responses, err := handleHTTPPayload(ctx, app, defaultWorkspace, body)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if len(responses) == 0 {
		w.WriteHeader(http.StatusAccepted)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	if len(responses) == 1 && !isJSONArray(body) {
		_ = json.NewEncoder(w).Encode(responses[0])
		return
	}
	_ = json.NewEncoder(w).Encode(responses)
}

func handleHTTPPayload(ctx context.Context, app *bootstrap.App, defaultWorkspace string, body []byte) ([]rpcResponse, error) {
	if isJSONArray(body) {
		var raws []json.RawMessage
		if err := json.Unmarshal(body, &raws); err != nil {
			return nil, err
		}
		responses := make([]rpcResponse, 0, len(raws))
		for _, raw := range raws {
			resp, ok := handleRawRPC(ctx, app, defaultWorkspace, raw)
			if ok {
				responses = append(responses, resp)
			}
		}
		return responses, nil
	}
	resp, ok := handleRawRPC(ctx, app, defaultWorkspace, body)
	if !ok {
		return nil, nil
	}
	return []rpcResponse{resp}, nil
}

func isJSONArray(body []byte) bool {
	return strings.HasPrefix(strings.TrimSpace(string(body)), "[")
}

func legacySSEHandler(broker *sseBroker) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if !validOrigin(r) {
			http.Error(w, "invalid Origin", http.StatusForbidden)
			return
		}
		if !validProtocolVersionHeader(r) {
			http.Error(w, "unsupported MCP protocol version", http.StatusBadRequest)
			return
		}
		if r.Method != http.MethodGet {
			w.Header().Set("Allow", "GET")
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		id, ch := broker.open()
		defer broker.close(id)

		endpoint := "/messages?session=" + url.QueryEscape(id)
		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("Cache-Control", "no-cache")
		w.Header().Set("Connection", "keep-alive")
		writeRawSSE(w, "endpoint", endpoint)
		if flusher, ok := w.(http.Flusher); ok {
			flusher.Flush()
		}
		for {
			select {
			case <-r.Context().Done():
				return
			case resp := <-ch:
				writeSSE(w, "message", resp)
				if flusher, ok := w.(http.Flusher); ok {
					flusher.Flush()
				}
			}
		}
	}
}

func legacyMessageHandler(ctx context.Context, app *bootstrap.App, defaultWorkspace string, broker *sseBroker) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if !validOrigin(r) {
			http.Error(w, "invalid Origin", http.StatusForbidden)
			return
		}
		if !validProtocolVersionHeader(r) {
			http.Error(w, "unsupported MCP protocol version", http.StatusBadRequest)
			return
		}
		if r.Method != http.MethodPost {
			w.Header().Set("Allow", "POST")
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		body, err := io.ReadAll(r.Body)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		responses, err := handleHTTPPayload(ctx, app, defaultWorkspace, body)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		if session := r.URL.Query().Get("session"); session != "" {
			if ch, ok := broker.get(session); ok {
				for _, resp := range responses {
					ch <- resp
				}
				w.WriteHeader(http.StatusAccepted)
				return
			}
			http.Error(w, "unknown SSE session", http.StatusNotFound)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		if len(responses) == 1 && !isJSONArray(body) {
			_ = json.NewEncoder(w).Encode(responses[0])
			return
		}
		_ = json.NewEncoder(w).Encode(responses)
	}
}

func (b *sseBroker) open() (string, chan rpcResponse) {
	id := fmt.Sprintf("s%d", atomic.AddUint64(&b.next, 1))
	ch := make(chan rpcResponse, 16)
	b.mu.Lock()
	b.sessions[id] = ch
	b.mu.Unlock()
	return id, ch
}

func (b *sseBroker) get(id string) (chan rpcResponse, bool) {
	b.mu.Lock()
	defer b.mu.Unlock()
	ch, ok := b.sessions[id]
	return ch, ok
}

func (b *sseBroker) close(id string) {
	b.mu.Lock()
	delete(b.sessions, id)
	b.mu.Unlock()
}

func writeSSE(w io.Writer, event string, value any) {
	body, _ := json.Marshal(value)
	writeRawSSE(w, event, string(body))
}

func writeRawSSE(w io.Writer, event, data string) {
	_, _ = fmt.Fprintf(w, "event: %s\n", event)
	for _, line := range strings.Split(data, "\n") {
		_, _ = fmt.Fprintf(w, "data: %s\n", line)
	}
	_, _ = fmt.Fprint(w, "\n")
}

func validOrigin(r *http.Request) bool {
	origin := r.Header.Get("Origin")
	if origin == "" {
		return true
	}
	parsed, err := url.Parse(origin)
	if err != nil {
		return false
	}
	originHost := hostOnly(parsed.Host)
	requestHost := hostOnly(r.Host)
	if originHost == requestHost {
		return true
	}
	return originHost == "localhost" || originHost == "127.0.0.1" || originHost == "::1"
}

func validProtocolVersionHeader(r *http.Request) bool {
	version := r.Header.Get("MCP-Protocol-Version")
	if version == "" {
		return true
	}
	return supportedProtocolVersions[version]
}

func hostOnly(hostport string) string {
	if hostport == "" {
		return ""
	}
	if host, _, err := net.SplitHostPort(hostport); err == nil {
		return strings.Trim(host, "[]")
	}
	return strings.Trim(hostport, "[]")
}
