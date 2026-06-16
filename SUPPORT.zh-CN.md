# 支持

English version: [SUPPORT.md](SUPPORT.md)

请按问题类型选择支持路径。

## 问题咨询

如果启用了 GitHub Discussions，请优先使用 Discussion。否则创建 question issue，并包含：

- 你想构建什么。
- 运行的命令或 API 调用。
- 输出或错误。
- OS、Go version、Node version 和 GraphStore provider。

## Bug

使用 bug report template。请包含最小复现和以下输出：

```bash
go version
make status
go run ./cmd/mmctl --addr http://localhost:8080 query examples
```

如果涉及 Web UI，请包含：

```bash
cd web
pnpm --version
pnpm build
```

## Feature Request

使用 feature request template。说明用户工作流、公共接口影响，以及现有 Query Service、CLI、MCP 或 SDK 为什么不够。

## Security

不要为漏洞创建公开 issue。请遵循 [SECURITY.zh-CN.md](SECURITY.zh-CN.md)。

## 商业或私有部署支持

本仓库记录开源本地版本。生产部署还需要额外认证、授权、传输安全、审计和运维设计，这些超出当前开源 release 范围。
