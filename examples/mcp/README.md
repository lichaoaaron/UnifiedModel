# MCP Examples

中文：[MCP 示例](README.zh-CN.md)

Use these examples from the repository root. They cover stdio, Streamable HTTP, legacy HTTP+SSE, and the TOON payload contract used by MModel MCP responses.

## Contract Shape

MModel keeps the MCP protocol envelope as JSON-RPC and encodes tool/resource text payloads as TOON:

- JSON-RPC envelope: `application/json`
- Tool payload text: `result.content[].text` with `_meta.mimeType: text/toon`
- Tool JSON mirror: `result.structuredContent`
- Resource payload text: `result.contents[].text` with `mimeType: text/toon`

Parse the JSON-RPC envelope first. Use `structuredContent` when a client wants JSON, and use the TOON text block when a prompt or agent context benefits from compact text.

## Stdio

Run the bundled request sequence:

```bash
go run ./cmd/mmodel-mcp --data data --graphstore memory < examples/mcp/stdio-requests.jsonl
```

The `notifications/initialized` line is a JSON-RPC notification and does not produce a response. Tool calls return `content` text in TOON, for example:

```toon
name: query_spl_examples
ok: true
output[6]: ".mmodel with(kind='entity_set') | project domain,name,kind | sort domain,name | limit 20",".entity with(domain='devops', name='devops.service', query='checkout', topk=20)"
```

## Streamable HTTP

Start the HTTP MCP server:

```bash
go run ./cmd/mmodel-mcp --transport http --addr 127.0.0.1:8090 --data data --graphstore file.memory
```

Send a request:

```bash
curl -sS http://127.0.0.1:8090/mcp \
  -H 'Content-Type: application/json' \
  -H 'MCP-Protocol-Version: 2025-06-18' \
  --data '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"workspace":"demo","name":"query_spl_examples","arguments":{}}}'
```

The same requests are available in [streamable-http.http](streamable-http.http) for editors that can run `.http` files.

## Legacy HTTP+SSE

Start the same HTTP server, then open the SSE stream:

```bash
curl -N http://127.0.0.1:8090/sse
```

The first event returns an endpoint like:

```text
event: endpoint
data: /messages?session=s1
```

Post JSON-RPC messages to that endpoint:

```bash
curl -sS 'http://127.0.0.1:8090/messages?session=s1' \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":2,"method":"resources/read","params":{"workspace":"demo","uri":"mmodel://workspace/demo/overview"}}'
```

Responses are delivered on the SSE stream as `message` events.

## Shared Data Roots

`memory` GraphStore state is process-local. Use `file.memory` with the same `--data` path when `mmodel-server` and `mmodel-mcp` need to see the same workspace data.

Write tools stay disabled unless server-side policy explicitly enables them. Default examples use read-oriented methods and bounded query templates.
