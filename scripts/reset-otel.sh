#!/bin/bash
# 一键重置并重建 otel-demo workspace
# 用法: bash ./scripts/reset-otel.sh
set -e

ADDR="http://localhost:8080"
WS="otel-demo"
DATA_ROOT="data"

echo "=== 0. 清理旧数据 ==="
rm -rf "$DATA_ROOT/graphstore/file-memory/workspaces/$WS"
rm -rf "$DATA_ROOT/instances/$WS"

# 清理 workspaces.json 中的 tombstone
python3 -c "
import json, sys
try:
    with open('$DATA_ROOT/workspaces.json') as f:
        d = json.load(f)
    if '$WS' in d.get('items', {}):
        del d['items']['$WS']
        with open('$DATA_ROOT/workspaces.json', 'w') as f:
            json.dump(d, f, indent=2)
        print('Removed $WS from workspaces.json')
    else:
        print('$WS not in workspaces.json')
except Exception as e:
    print(f'Warning: {e}', file=sys.stderr)
"

echo "=== 1. 创建 workspace ==="
curl -s -X POST "$ADDR/api/v1/workspaces" \
  -H "Content-Type: application/json" \
  -d "{\"id\":\"$WS\",\"name\":\"OpenTelemetry Demo\"}"

echo ""
echo "=== 2. 导入模型 ==="
go run ./cmd/umctl --addr "$ADDR" umodel import "$WS" examples/otel-demo

echo "=== 3. 导入实体 ==="
go run ./cmd/umctl --addr "$ADDR" entity write "$WS" examples/otel-demo/sample-data/entities.json

echo "=== 4. 导入关系 ==="
curl -s -X POST "$ADDR/api/v1/entitystore/$WS/relations:write" \
  -H "Content-Type: application/json" \
  -d "{\"relations\": $(cat examples/otel-demo/sample-data/relations.json)}"

echo ""
echo "=== 5. 验证 ==="
echo "Workspaces:"
curl -s "$ADDR/api/v1/workspaces" | python3 -c "import sys,json;d=json.load(sys.stdin);[print(f'  {k}') for k in d.get('items',{})]"

echo ""
echo "Entities:"
go run ./cmd/umctl --addr "$ADDR" query run "$WS" ".entity with(domain='otel') | project __entity_id__,display_name | limit 5"

echo ""
echo "Topo relations:"
go run ./cmd/umctl --addr "$ADDR" query run "$WS" ".topo | limit 3"

echo ""
echo "=== Done! ==="
echo "Open http://localhost:5173 → select $WS"
