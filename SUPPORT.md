# Support

Use the support path that matches what you need.

## Questions

Open a GitHub Discussion if discussions are enabled. If not, open a question issue and include:

- What you are trying to build.
- The command or API call you ran.
- The output or error.
- Your OS, Go version, Node version, and GraphStore provider.

## Bugs

Use the bug report template. Include a minimal reproduction and the output of:

```bash
go version
make status
go run ./cmd/mmctl --addr http://localhost:8080 query examples
```

If the bug involves the Web UI, include:

```bash
cd web
pnpm --version
pnpm build
```

## Feature Requests

Use the feature request template. Describe the user workflow, public interface impact, and why existing Query Service, CLI, MCP, or SDK surfaces are not enough.

## Security

Do not open public issues for vulnerabilities. Follow [SECURITY.md](SECURITY.md).

## Commercial Or Private Deployment Support

This repository documents the open-source local distribution. Production deployments need additional authentication, authorization, transport security, audit, and operations design outside the current open-source release scope.
