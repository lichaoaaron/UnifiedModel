# MModel Controlled Fault Samples

This directory is generated from the exported telemetry under `data/`.

The sample reuses the formal model definitions from
`examples/incident-investigation` and provides:

- UModel-compatible runtime entities and relations under `sample-data/`.
- Redis and database middleware model definitions under `model-pack/`.
- Twelve controlled fault scenarios under `scenarios/`.
- Mutated log, metric, and trace evidence under `evidence/`.
- Three concise presentation scenarios in `scenarios/demo-scenarios.json`.

Generate or refresh the sample:

```bash
python scripts/generate_mmodel_fault_samples.py
```

Load the model and runtime graph:

```bash
go run ./cmd/umctl --addr http://localhost:8080 workspace create mmodel-faults '{"name":"MModel Fault Samples"}'
go run ./cmd/umctl --addr http://localhost:8080 umodel import mmodel-faults examples/incident-investigation
go run ./cmd/umctl --addr http://localhost:8080 umodel import mmodel-faults examples/mmodel-fault-samples/model-pack
go run ./cmd/umctl --addr http://localhost:8080 entity write mmodel-faults examples/mmodel-fault-samples/sample-data/entities.json
go run ./cmd/umctl --addr http://localhost:8080 topo write mmodel-faults examples/mmodel-fault-samples/sample-data/relations.json
```

Useful verification queries:

```bash
go run ./cmd/umctl --addr http://localhost:8080 query run mmodel-faults ".entity with(domain='platform', name='platform.incident') | project display_name,severity,impacted_service | limit 20"
go run ./cmd/umctl --addr http://localhost:8080 query run mmodel-faults ".entity with(domain='platform', name='platform.service', query='degraded') | project display_name,status | limit 20"
go run ./cmd/umctl --addr http://localhost:8080 query run mmodel-faults ".entity with(domain='platform', name='platform.redis') | project display_name,instance,status | limit 20"
go run ./cmd/umctl --addr http://localhost:8080 query run mmodel-faults ".entity with(domain='platform', name='platform.database') | project display_name,instance,status | limit 20"
```

These samples are controlled synthetic mutations of real exported telemetry.
They are suitable for closed-loop validation and demonstrations, but they are
not production incident ground truth.
