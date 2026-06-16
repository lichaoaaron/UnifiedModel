package contract_test

import (
	"encoding/json"
	"os"
	"strings"
	"testing"
)

func TestOpenAPIContainsPublicContracts(t *testing.T) {
	body, err := os.ReadFile("../../api/openapi/openapi.yaml")
	if err != nil {
		t.Fatalf("read openapi: %v", err)
	}
	text := string(body)
	required := []string{
		"/api/v1/workspaces",
		"/api/v1/mmodel/{workspace}/elements",
		"/api/v1/mmodel/{workspace}/import",
		"/api/v1/samples/{workspace}/multi-domain-quickstart:import",
		"/api/v1/entitystore/{workspace}/entities:write",
		"/api/v1/entitystore/{workspace}/relations:write",
		"/api/v1/query/{workspace}/execute",
		"/api/v1/query/{workspace}/explain",
		"/api/v1/agent/{workspace}/discover",
		"/api/v1/agent/{workspace}/tools:execute",
		"/api/v1/agent/{workspace}/resources:read",
		"operationId: getServiceIndex",
		"ServiceIndexResponse:",
		"HealthResponse:",
		"WorkspacePage:",
		"WorkspacePaths:",
		"DeleteMModelElementsRequest:",
		"ExpireRequest:",
		"ValidationResult:",
		"QueryRequest:",
		"QueryResult:",
		"BatchItemResult:",
		"MModelImportRequest:",
		"MModelImportResult:",
		"SampleImportResult:",
		"AgentToolCallRequest:",
		"AgentResource:",
		"operationId: deleteMModelElements",
		"operationId: importMultiDomainQuickstartSample",
		"operationId: expireEntities",
		"operationId: expireRelations",
	}
	for _, needle := range required {
		if !strings.Contains(text, needle) {
			t.Fatalf("openapi missing %q", needle)
		}
	}
	forbidden := []string{
		"/api/v1/" + "entities",
		"/api/v1/" + "relations",
		"/api/v1/" + "graph",
		"/api/v1/" + "related",
		"/api/v1/" + "neighbors",
	}
	for _, needle := range forbidden {
		if strings.Contains(text, needle) {
			t.Fatalf("openapi exposes forbidden domain read API %q", needle)
		}
	}
}

func TestMCPToolSchemaDefaults(t *testing.T) {
	body, err := os.ReadFile("../../api/mcp/tools.schema.json")
	if err != nil {
		t.Fatalf("read mcp schema: %v", err)
	}
	var schema map[string]any
	if err := json.Unmarshal(body, &schema); err != nil {
		t.Fatalf("invalid schema json: %v", err)
	}
	text := string(body)
	for _, tool := range []string{"query_spl_execute", "query_spl_explain", "query_spl_examples", "mmodel_validate", "entity_write", "entity_expire"} {
		if !strings.Contains(text, tool) {
			t.Fatalf("mcp schema missing tool %q", tool)
		}
	}
	if !strings.Contains(text, "requires_explicit_write_enable") {
		t.Fatalf("mcp schema should describe explicit write enablement")
	}
	for _, needle := range []string{"enabled_by_default", "input_schema", "output_schema", "stdio", "streamable-http", "http+sse", "text/toon", "tools/list", "tools/call", "resources/list", "resources/templates/list", "resources/read", "prompts/list", "prompts/get", "completion/complete", "tool-capability-metadata", `"read_only"`} {
		if !strings.Contains(text, needle) {
			t.Fatalf("mcp schema missing contract field %q", needle)
		}
	}
}
