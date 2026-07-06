# Plugin provisioning

`apps.yaml` auto-enables this app in the dev Grafana and seeds its settings so you don't have to fill the Configuration page by hand:

- `jsonData.apiUrl` — base URL of the UModel server the Go backend reverse-proxies to. It must be reachable **from the Grafana server** (never `localhost` when Grafana runs in Docker).
- `secureJsonData.apiKey` — optional bearer token for the UModel server (leave empty when unauthenticated).

Notes:
- The committed `apiUrl` is a placeholder; override it for your environment (edit locally or set it via the Configuration page).
- Changing `plugin.json` requires a Grafana restart.

For more information see:

- [Provision Grafana](https://grafana.com/docs/grafana/latest/administration/provisioning/)
- [Provision a plugin](https://grafana.com/developers/plugin-tools/publish-a-plugin/provide-test-environment)