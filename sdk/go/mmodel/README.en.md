# MModel Go SDK V2

中文版本：[README.md](README.md)

This directory contains the generated Go SDK for MModel schemas. V2 preserves schema inheritance and shared type reuse more directly than the earlier generated shape.

## Key Features

- Shared types such as `MetadataV1` and `SchemaV1` are generated once and reused.
- Go struct embedding represents schema inheritance where appropriate.
- Generated code is smaller and easier to maintain than duplicate per-schema structures.
- Concrete generated types improve type safety compared with raw `map[string]interface{}` usage.

## File Layout

- `base_types.go`: base types such as semantic strings.
- `shared_types.go`: shared schema types such as metadata, schema, and link definitions.
- `{schema_name}.go`: generated implementation for each schema.
- `mmodel.go`: package entry point, parsing helpers, and type registry.

## Usage

```go
obj, err := mmodel.ParseType("metric_set:v1.0.0", jsonData, "json")
if err != nil {
    return err
}
_ = obj
```

Regenerate and verify from the repository root:

```bash
make expand
make verify-go
```
