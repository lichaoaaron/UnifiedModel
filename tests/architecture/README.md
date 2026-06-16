# Architecture Tests

Architecture checks are implemented in `tools/guards/architecture_guard.py` and run through:

```bash
make guard
```

The guard enforces the project-level constraints from the specs:

- Workspace metadata APIs must not grow runtime lifecycle operations.
- Domain read APIs must not bypass Query Service.
- MModelAssistant is not part of the current open-source runtime/API surface.
- Business modules must not import GraphStore provider implementation packages.
