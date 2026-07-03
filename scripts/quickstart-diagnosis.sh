#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_URL="${API_URL:-${UMODEL_API_URL:-http://localhost:8080}}"

cd "${ROOT_DIR}"

require_path() {
  local path="$1"
  if [[ ! -e "${path}" ]]; then
    echo "Missing required diagnosis quickstart asset: ${path}" >&2
    exit 1
  fi
}

create_workspace() {
  local workspace_id="$1"
  local name="$2"
  local payload
  payload="{\"id\":\"${workspace_id}\",\"name\":\"${name}\"}"

  local status
  status="$(
    curl -sS -o /dev/null -w "%{http_code}" \
      -X POST "${API_URL}/api/v1/workspaces" \
      -H "Content-Type: application/json" \
      -d "${payload}"
  )"
  case "${status}" in
    200|201|204|409)
      ;;
    *)
      echo "Failed to create workspace ${workspace_id}; HTTP ${status}" >&2
      exit 1
      ;;
  esac
}

import_mmodel_faults() {
  local workspace="mmodel-faults"
  echo "Loading ${workspace} workspace..."

  require_path "examples/incident-investigation"
  require_path "outputs/mmodel-fault-samples/model-pack"
  require_path "outputs/mmodel-fault-samples/sample-data/entities.json"
  require_path "outputs/mmodel-fault-samples/sample-data/relations.json"

  create_workspace "${workspace}" "MModel Fault Samples"
  go run ./cmd/umctl --addr "${API_URL}" umodel import "${workspace}" examples/incident-investigation
  go run ./cmd/umctl --addr "${API_URL}" umodel import "${workspace}" outputs/mmodel-fault-samples/model-pack
  go run ./cmd/umctl --addr "${API_URL}" entity write "${workspace}" outputs/mmodel-fault-samples/sample-data/entities.json
  go run ./cmd/umctl --addr "${API_URL}" topo write "${workspace}" outputs/mmodel-fault-samples/sample-data/relations.json
}

import_otel_demo() {
  local workspace="otel-demo"
  echo "Loading ${workspace} workspace..."

  require_path "examples/otel-demo"
  require_path "examples/otel-demo/sample-data/entities.json"
  require_path "examples/otel-demo/sample-data/relations.json"

  create_workspace "${workspace}" "OpenTelemetry Demo"
  go run ./cmd/umctl --addr "${API_URL}" umodel import "${workspace}" examples/otel-demo
  go run ./cmd/umctl --addr "${API_URL}" entity write "${workspace}" examples/otel-demo/sample-data/entities.json
  go run ./cmd/umctl --addr "${API_URL}" topo write "${workspace}" examples/otel-demo/sample-data/relations.json
}

import_mmodel_faults
import_otel_demo

echo "Diagnosis quickstart workspaces are ready:"
echo "  - demo"
echo "  - mmodel-faults"
echo "  - otel-demo"
