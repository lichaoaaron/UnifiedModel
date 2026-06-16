# 部署

English version: [README.md](README.md)

本目录包含 MModel Open Source 的本地部署资产。

| 路径 | 作用 |
|---|---|
| `docker/Dockerfile` | 将 `mmodel-server` 构建为小型运行时镜像。 |
| `compose/docker-compose.yaml` | 使用持久化 Docker volume 运行服务。 |

## 默认 Provider

开源部署资产默认使用 `--graphstore file.memory`。这样不需要本地 Ladybug runtime，并将 GraphStore JSON 数据持久化到 `/data`。

仅在具备 Ladybug-enabled build、`liblbug` runtime 且有明确运维原因时使用 `local.ladybug`。

## Docker

```bash
docker build -f deployments/docker/Dockerfile -t mmodel-open-source:local .
docker run --rm \
  -p 8080:8080 \
  -v mmodel-data:/data \
  mmodel-open-source:local
```

健康检查：

```bash
curl http://localhost:8080/healthz
```

## Docker Compose

```bash
docker compose -f deployments/compose/docker-compose.yaml up --build
docker compose -f deployments/compose/docker-compose.yaml down
```

删除持久化数据：

```bash
docker compose -f deployments/compose/docker-compose.yaml down -v
```

## 端口与数据

| 配置 | 默认值 | 说明 |
|---|---|---|
| API port | `8080` | `http://localhost:8080` |
| Data directory | `/data` | Compose 中挂载到 `mmodel-data` volume。 |
| GraphStore provider | `file.memory` | JSON snapshot 位于 `/data/graphstore/file-memory/`。 |

## 导入 Demo

```bash
go run ./cmd/mmctl --addr http://localhost:8080 workspace create demo '{"name":"Demo"}'
curl -X POST http://localhost:8080/api/v1/samples/demo/multi-domain-quickstart:import \
  -H 'Content-Type: application/json' \
  -d '{}'
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".mmodel | limit 5"
```
