# Deployments

This directory contains local deployment assets for MModel Open Source.

| Path | Purpose |
|---|---|
| `docker/Dockerfile` | Builds `mmodel-server` into a small runtime image. |
| `compose/docker-compose.yaml` | Runs the server with a persistent local Docker volume. |

## Provider Default

The open-source deployment assets use `--graphstore file.memory` by default. This avoids local Ladybug runtime requirements and persists GraphStore JSON data under `/data`.

Use `local.ladybug` only in an environment that has:

- A Ladybug-enabled build.
- The `liblbug` runtime available to the process.
- A deliberate operational reason to use the Ladybug-backed provider.

## Docker

Build the image from the repository root:

```bash
docker build -f deployments/docker/Dockerfile -t mmodel-open-source:local .
```

Run the server:

```bash
docker run --rm \
  -p 8080:8080 \
  -v mmodel-data:/data \
  mmodel-open-source:local
```

The container starts:

```bash
mmodel-server --addr :8080 --data /data --graphstore file.memory
```

Check health:

```bash
curl http://localhost:8080/healthz
```

## Docker Compose

Start:

```bash
docker compose -f deployments/compose/docker-compose.yaml up --build
```

Stop:

```bash
docker compose -f deployments/compose/docker-compose.yaml down
```

Remove persisted data:

```bash
docker compose -f deployments/compose/docker-compose.yaml down -v
```

## Ports And Data

| Setting | Default | Notes |
|---|---|---|
| API port | `8080` | Exposed as `http://localhost:8080`. |
| Data directory | `/data` | Mounted to the `mmodel-data` Docker volume in Compose. |
| GraphStore provider | `file.memory` | Stores JSON snapshots under `/data/graphstore/file-memory/`. |

Workspace metadata is persisted separately at `/data/workspaces.json` when using `file.memory`.

## Import The Demo In Docker

After the server starts:

```bash
go run ./cmd/mmctl --addr http://localhost:8080 workspace create demo '{"name":"Demo"}'
curl -X POST http://localhost:8080/api/v1/samples/demo/multi-domain-quickstart:import \
  -H 'Content-Type: application/json' \
  -d '{}'
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".mmodel | limit 5"
```

## Compatibility Notes

- The JSON files written by `file.memory` are useful for local inspection and demos, but they are not a long-term storage compatibility contract.
- Do not run multiple writers against the same file-memory directory.
- When upgrading between development builds, prefer exporting or re-importing example data rather than depending on raw JSON layout stability.
- If a future release changes storage layout, document the migration in [CHANGELOG.md](../CHANGELOG.md).
