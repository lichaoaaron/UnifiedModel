# Basic Root Cause Evaluation Cases

This directory contains 19 production-like observability cases derived from the fault injection scenario spreadsheet.

Each case has one explicit root cause and four files:

- trace.json
- log.json
- metric.json
- ground_truth.json

The JSON files intentionally mirror the OpenSearch-style field names used by MModel and are the canonical local demo data source.

Use index.json to enumerate cases and ground_truth.json to evaluate root cause, affected services, affected interfaces, and evidence quality.
