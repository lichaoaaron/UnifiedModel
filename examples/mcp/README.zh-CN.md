# MCP 示例

English: [MCP Examples](README.md)

以下示例从仓库根目录运行，覆盖 stdio、Streamable HTTP、旧 HTTP+SSE，以及 MModel MCP response 使用的 TOON payload 契约。

## 契约形态

MModel 保持 MCP protocol envelope 为 JSON-RPC，并把 tool/resource 的文本 payload 编码为 TOON：

- JSON-RPC envelope：`application/json`
- Tool payload text：`result.content[].text`，并带 `_meta.mimeType: text/toon`
- Tool JSON mirror：`result.structuredContent`
- Resource payload text：`result.contents[].text`，并带 `mimeType: text/toon`

先解析 JSON-RPC envelope。Client 需要 JSON 时使用 `structuredContent`；prompt 或 agent context 需要紧凑文本时使用 TOON text block。

## Stdio

运行内置请求序列：

```bash
go run ./cmd/mmodel-mcp --data data --graphstore memory < examples/mcp/stdio-requests.jsonl
```

`notifications/initialized` 是 JSON-RPC notification，不会产生 response。Tool call 返回 TOON 格式的 `content` text，例如：

```toon
name: query_spl_examples
ok: true
output[6]: ".mmodel with(kind='entity_set') | project domain,name,kind | sort domain,name | limit 20",".entity with(domain='devops', name='devops.service', query='checkout', topk=20)"
```

## Streamable HTTP

启动 HTTP MCP server：

```bash
go run ./cmd/mmodel-mcp --transport http --addr 127.0.0.1:8090 --data data --graphstore file.memory
```

发送请求：

```bash
curl -sS http://127.0.0.1:8090/mcp \
  -H 'Content-Type: application/json' \
  -H 'MCP-Protocol-Version: 2025-06-18' \
  --data '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"workspace":"demo","name":"query_spl_examples","arguments":{}}}'
```

[streamable-http.http](streamable-http.http) 中提供了同一组请求，可供支持 `.http` 文件的编辑器直接运行。

## 旧 HTTP+SSE

启动同一个 HTTP server 后，打开 SSE stream：

```bash
curl -N http://127.0.0.1:8090/sse
```

第一个 event 会返回 endpoint：

```text
event: endpoint
data: /messages?session=s1
```

把 JSON-RPC message 发送到这个 endpoint：

```bash
curl -sS 'http://127.0.0.1:8090/messages?session=s1' \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":2,"method":"resources/read","params":{"workspace":"demo","uri":"mmodel://workspace/demo/overview"}}'
```

Response 会通过 SSE stream 的 `message` event 返回。

## 共享数据目录

`memory` GraphStore 状态只在单个进程内可见。需要让 `mmodel-server` 和 `mmodel-mcp` 看到同一份 workspace 数据时，使用相同 `--data` 路径和 `file.memory`。

写工具默认保持关闭，除非服务端策略显式启用。默认示例只使用读向方法和有界查询模板。
