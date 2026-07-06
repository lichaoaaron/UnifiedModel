package plugin

import (
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// proxyClient is shared across (buffered) resource calls to the UModel server.
var proxyClient = &http.Client{Timeout: 60 * time.Second}

// diagnosisClient serves the streaming SSE proxy to the diagnosis service. A
// diagnosis run can take up to ~2min, so its timeout is well above proxyClient's
// 60s; the browser (AbortController) / request context cancels early otherwise.
var diagnosisClient = &http.Client{Timeout: 300 * time.Second}

// hopByHopHeaders are connection-scoped and must not be forwarded.
var hopByHopHeaders = map[string]bool{
	"Connection":          true,
	"Keep-Alive":          true,
	"Proxy-Authenticate":  true,
	"Proxy-Authorization": true,
	"Te":                  true,
	"Trailer":             true,
	"Transfer-Encoding":   true,
	"Upgrade":             true,
}

func copyHeaders(dst, src http.Header) {
	for k, vv := range src {
		if hopByHopHeaders[http.CanonicalHeaderKey(k)] {
			continue
		}
		for _, v := range vv {
			dst.Add(k, v)
		}
	}
}

// buildUpstreamRequest reverse-maps the incoming request onto base + (path with
// stripPrefix removed), preserving method/query/body and stripping the Grafana
// session so it never leaks upstream. Bearer, when set, is injected.
func buildUpstreamRequest(base, stripPrefix, bearer string, req *http.Request) (*http.Request, error) {
	rest := strings.TrimPrefix(req.URL.Path, stripPrefix)
	u, err := url.Parse(strings.TrimRight(base, "/") + rest)
	if err != nil {
		return nil, err
	}
	u.RawQuery = req.URL.RawQuery

	outReq, err := http.NewRequestWithContext(req.Context(), req.Method, u.String(), req.Body)
	if err != nil {
		return nil, err
	}
	copyHeaders(outReq.Header, req.Header)
	// Never leak Grafana's session/credentials to the upstream.
	outReq.Header.Del("Cookie")
	outReq.Header.Del("Authorization")
	if bearer != "" {
		outReq.Header.Set("Authorization", "Bearer "+bearer)
	}
	return outReq, nil
}

// proxyTo returns a handler that reverse-proxies the request to base + (request
// path with stripPrefix removed), buffering the response. An empty base means
// the upstream is not configured.
func (a *App) proxyTo(base, stripPrefix, bearer string) http.HandlerFunc {
	return func(w http.ResponseWriter, req *http.Request) {
		if base == "" {
			http.Error(w, "upstream not configured", http.StatusBadGateway)
			return
		}
		outReq, err := buildUpstreamRequest(base, stripPrefix, bearer, req)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		resp, err := proxyClient.Do(outReq)
		if err != nil {
			http.Error(w, "upstream unreachable: "+err.Error(), http.StatusBadGateway)
			return
		}
		defer func() { _ = resp.Body.Close() }()

		copyHeaders(w.Header(), resp.Header)
		w.WriteHeader(resp.StatusCode)
		_, _ = io.Copy(w, resp.Body)
	}
}

// streamProxyTo reverse-proxies to the diagnosis service and forwards the
// response body incrementally: it flushes after every read so SSE events reach
// the browser as they arrive. httpadapter's ResponseWriter sends a
// CallResourceResponse chunk on each Flush (a plain io.Copy would buffer the
// whole stream until the handler returns, defeating streaming).
func (a *App) streamProxyTo(base, stripPrefix string) http.HandlerFunc {
	return func(w http.ResponseWriter, req *http.Request) {
		if base == "" {
			http.Error(w, "diagnosis upstream not configured (set jsonData.diagnosisUrl)", http.StatusBadGateway)
			return
		}
		outReq, err := buildUpstreamRequest(base, stripPrefix, "", req)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		resp, err := diagnosisClient.Do(outReq)
		if err != nil {
			http.Error(w, "diagnosis upstream unreachable: "+err.Error(), http.StatusBadGateway)
			return
		}
		defer func() { _ = resp.Body.Close() }()

		copyHeaders(w.Header(), resp.Header)
		w.WriteHeader(resp.StatusCode)

		flusher, canFlush := w.(http.Flusher)
		buf := make([]byte, 4096)
		for {
			n, readErr := resp.Body.Read(buf)
			if n > 0 {
				if _, writeErr := w.Write(buf[:n]); writeErr != nil {
					return
				}
				if canFlush {
					flusher.Flush()
				}
			}
			if readErr != nil {
				return
			}
		}
	}
}

// handlePing is a lightweight health probe for the resource channel.
func (a *App) handlePing(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(`{"message": "ok"}`))
}

// registerRoutes wires the reverse-proxy routes onto the resource mux. The
// frontend UModelApi targets /api/plugins/<id>/resources, so its calls to
// /api/v1/... and /healthz arrive here and are forwarded to the UModel server.
// /diagnosis/* is streamed to the separate diagnosis service (SSE).
func (a *App) registerRoutes(mux *http.ServeMux) {
	mux.HandleFunc("/ping", a.handlePing)
	mux.HandleFunc("/api/", a.proxyTo(a.settings.APIURL, "", a.apiKey))
	mux.HandleFunc("/healthz", a.proxyTo(a.settings.APIURL, "", a.apiKey))
	mux.HandleFunc("/diagnosis/", a.streamProxyTo(a.settings.DiagnosisURL, "/diagnosis"))
}