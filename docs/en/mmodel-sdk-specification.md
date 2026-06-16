# MModel SDK Specification

中文：[MModel SDK 规范](../zh/mmodel-sdk-specification.md)

Expected behavior for generated and handwritten MModel SDKs across Go, Python, Java, and future language bindings.

## Version

- Specification version: `1.0.0`
- Scope: model object types, parsing, validation, type registration, serialization, and compatibility behavior
- Source of truth: schema files under `schemas/`, public model contracts under `pkg/model`, and public service contracts under `pkg/contract`

## Core Concepts

### Schema Envelope

Every MModel object follows a common envelope:

- `kind` identifies the model object type.
- `schema` carries schema version metadata.
- `metadata` carries identity, domain, name, labels, and display fields.
- `spec` carries type-specific configuration.

SDKs should expose this envelope consistently even when the target language uses different naming conventions.

### Inheritance And Composition

Schemas may use `extends` to share common structures. SDKs should map inheritance to idiomatic language features:

- Go: embedding or generated composition helpers.
- Python: classes, dataclasses, or Pydantic-style composition where applicable.
- Java: interfaces, abstract base classes, or generated inheritance.

The generated API should keep the schema relationship understandable without forcing callers to know generator internals.

### Versioning

SDKs should preserve schema versions in parsed objects and support version-aware parsing:

- Version keys should be stable and deterministic, for example `{kind}:{version}`.
- Pre-stable schema versions may map to the first stable SDK type when the structure is compatible.
- New SDK versions should continue to read older compatible objects.

## Type Mapping

| Schema type | Go | Python | Java |
|---|---|---|---|
| `string` | `string` | `str` | `String` |
| `number` | `float64` | `float` | `Double` |
| `integer` | `int64` | `int` | `Long` |
| `boolean` | `bool` | `bool` | `Boolean` |
| `object` | `map[string]any` or struct | `dict` or model class | `Map<String, Object>` or class |
| `array` | `[]T` | `list[T]` | `List<T>` |
| timestamp | `time.Time` or string wrapper | `datetime` or string wrapper | `Instant` or string wrapper |
| raw JSON | `json.RawMessage` | `dict` / `Any` | `JsonNode` or equivalent |

Language implementations may choose stricter target types, but they must preserve JSON/YAML round-trip behavior.

## Shared Interfaces

### MModelObject

All MModel objects should expose:

- `kind()` or equivalent kind access.
- `validate()` or equivalent validation entry point.
- JSON and YAML serialization.
- metadata and schema access when the object carries those sections.

### MModelCoreObject

Core model objects should expose:

- `schema` metadata.
- `metadata` metadata.
- stable identity fields.
- validation against the object schema.

### MModelLinkObject

Link objects should expose:

- source endpoint access.
- target endpoint access.
- optional filter or field mapping access.
- validation that source and target endpoint metadata is structurally complete.

## Parsing And Serialization

SDKs should provide:

- Parse JSON into a known target type.
- Parse YAML into a known target type.
- Detect `kind` and `schema.version`, then instantiate the matching generated type.
- Serialize objects back to JSON and YAML without losing unknown but allowed fields.
- Report parse errors with path, line/column when available, and a stable error category.

The automatic parser should follow this flow:

1. Decode enough of the document to read `kind` and `schema.version`.
2. Build a type key.
3. Look up the type registry.
4. Instantiate the target type.
5. Decode the full document.
6. Validate the object.

## Type Registry

Each SDK should provide a registry for generated and custom types:

- Register a type factory by kind and version.
- Create an instance from a type key.
- List known types for diagnostics.
- Check whether a type key is supported.

The registry should be extensible so downstream users can add domain-specific schema types without forking the generator.

## Helpers

SDKs should include helper functions for common runtime checks:

- Determine whether a value implements the core object interface.
- Determine whether a value implements the link object interface.
- Extract metadata from any compatible MModel object.
- Extract schema metadata from any compatible MModel object.
- Extract source and target endpoints from link objects.

## Error Handling

SDKs should expose structured errors with stable categories:

| Error category | Meaning |
|---|---|
| validation error | The object does not satisfy schema or semantic rules. |
| parse error | JSON/YAML decoding failed. |
| unknown type | No registered type matches the kind/version pair. |
| unsupported version | The kind is known but the version is not supported. |
| missing field | A required field is missing. |

Errors should include the best available field path and a human-readable message.

## Naming Rules

- Generated type names should be stable, for example `MetricSetV100`.
- Schema fields use `snake_case`.
- SDK fields and methods should follow target-language conventions.
- Serialization tags must keep JSON/YAML field names compatible with the schema.
- Optional fields should use idiomatic optional or pointer semantics.
- Embedded or inline fields should preserve the schema shape.

## Implementation Requirements

Every SDK implementation must support:

1. Generated model types for supported schema kinds.
2. JSON and YAML parsing.
3. JSON and YAML serialization.
4. Automatic kind/version detection.
5. Type registry lookup.
6. Core object validation.
7. Link endpoint validation.

Recommended features:

- Streaming parse for large files.
- Standalone schema validator.
- Type conversion helpers.
- Debug helpers for inspecting generated objects.
- Zero-copy or low-allocation parsing where practical.

## Testing Requirements

Each SDK should include:

- Unit tests for generated types and inheritance/composition behavior.
- Parser tests for JSON and YAML input.
- Auto-detection tests for kind/version routing.
- Validation tests for success and failure cases.
- Compatibility tests for older supported schema versions.
- Error tests that assert stable categories and useful paths.
- Example-file tests against the repository `examples/` tree.

Performance tests are recommended for large schema bundles and bulk example parsing.

## Documentation Requirements

Each SDK package should provide:

- Installation instructions.
- Basic parse/serialize examples.
- Type registry examples.
- Validation examples.
- Error handling examples.
- Compatibility and upgrade notes.

The Go, Python, and Java documentation should stay aligned with this specification and with the generated code behavior.

## Compatibility Rules

- New SDKs should read compatible older objects.
- Removing a public generated type is a breaking change.
- Renaming public methods is a breaking change unless compatibility aliases remain.
- Adding optional fields is compatible.
- Adding required fields requires a schema version change.
- Public contract changes must update OpenAPI, CLI, SDK docs, tests, and examples in the same pull request.

## Tooling Integration

SDK tooling may include:

- Schema validation commands.
- Code generation commands.
- Type checking commands.
- IDE metadata such as schema completion or diagnostics.
- Build tasks for generated code verification.

Repository verification entry points:

```bash
make verify
make verify-go
make verify-python
make verify-java
```
