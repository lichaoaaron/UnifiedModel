package plugin

import (
	"context"
	"encoding/json"
	"net/http"

	"github.com/grafana/grafana-plugin-sdk-go/backend"
	"github.com/grafana/grafana-plugin-sdk-go/backend/instancemgmt"
	"github.com/grafana/grafana-plugin-sdk-go/backend/resource/httpadapter"
)

// Make sure App implements required interfaces. This is important to do
// since otherwise we will only get a not implemented error response from plugin in
// runtime.
var (
	_ backend.CallResourceHandler   = (*App)(nil)
	_ instancemgmt.InstanceDisposer = (*App)(nil)
	_ backend.CheckHealthHandler    = (*App)(nil)
)

// appSettings mirrors the non-secret jsonData configured on the plugin
// (AppConfig page / provisioning).
type appSettings struct {
	// APIURL is the base URL of the UModel server (cmd/umodel-server), e.g.
	// http://host.docker.internal:8080. It must be reachable from the Grafana
	// server (container), so never "localhost" when Grafana runs in Docker.
	APIURL string `json:"apiUrl"`
	// DiagnosisURL is the base URL of the (separate) diagnosis service that the
	// Diagnosis workbench talks to over SSE. Optional — only the Diagnosis page
	// needs it. Reached from the Grafana server (container), same as APIURL.
	DiagnosisURL string `json:"diagnosisUrl"`
}

// App is the UModel app backend. It reverse-proxies frontend resource calls to
// the configured UModel server, optionally injecting an API key (from
// secureJsonData) server-side so it never reaches the browser. Reached from the
// frontend via /api/plugins/<id>/resources/...
type App struct {
	backend.CallResourceHandler
	settings appSettings
	apiKey   string
}

// NewApp creates a new *App instance from the plugin's configured settings.
func NewApp(_ context.Context, instanceSettings backend.AppInstanceSettings) (instancemgmt.Instance, error) {
	var app App

	if len(instanceSettings.JSONData) > 0 {
		if err := json.Unmarshal(instanceSettings.JSONData, &app.settings); err != nil {
			return nil, err
		}
	}
	// Optional bearer token for the upstream UModel server. umodel-server is
	// currently unauthenticated, so this is usually empty.
	app.apiKey = instanceSettings.DecryptedSecureJSONData["apiKey"]

	// Use a httpadapter (provided by the SDK) so we can map resource routes with
	// a *http.ServeMux.
	mux := http.NewServeMux()
	app.registerRoutes(mux)
	app.CallResourceHandler = httpadapter.New(mux)

	return &app, nil
}

// Dispose tells the plugin SDK that the plugin wants to clean up resources when a
// new instance is created.
func (a *App) Dispose() {
	// nothing to clean up
}

// CheckHealth handles health checks sent from Grafana to the plugin.
func (a *App) CheckHealth(_ context.Context, _ *backend.CheckHealthRequest) (*backend.CheckHealthResult, error) {
	if a.settings.APIURL == "" {
		return &backend.CheckHealthResult{
			Status:  backend.HealthStatusError,
			Message: "apiUrl is not configured (set it on the plugin Configuration page)",
		}, nil
	}
	return &backend.CheckHealthResult{
		Status:  backend.HealthStatusOk,
		Message: "ok",
	}, nil
}