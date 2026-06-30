#!/bin/bash
# 一键重建 otel-demo workspace
set -e
ADDR="http://localhost:8080"
WS="otel-demo"

echo "=== 1. 创建 workspace ==="
curl -s -X POST "$ADDR/api/v1/workspaces" \
  -H "Content-Type: application/json" \
  -d "{\"id\":\"$WS\",\"name\":\"OpenTelemetry Demo\"}"

echo "=== 2. 导入模型 ==="
go run ./cmd/mmctl --addr "$ADDR" mmodel import "$WS" examples/otel-demo

echo "=== 3. 导入实体 ==="
go run ./cmd/mmctl --addr "$ADDR" entity write "$WS" examples/otel-demo/sample-data/entities.json

echo "=== 4. 导入关系 ==="
curl -s -X POST "$ADDR/api/v1/entitystore/$WS/relations:write" \
  -H "Content-Type: application/json" \
  -d @examples/otel-demo/sample-data/relations.json

echo "=== 5. 验证 ==="
echo "Entities:"
go run ./cmd/mmctl --addr "$ADDR" query run "$WS" ".entity with(domain='otel') | project __entity_id__,display_name | limit 5"
echo ""
echo "Topo relations:"
go run ./cmd/mmctl --addr "$ADDR" query run "$WS" ".topo | limit 3"
echo ""
echo "Done! Open http://localhost:5173 → select otel-demo"
