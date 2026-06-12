---
name: os-query
description: >-
  Translate user requirements into OpenSearch DSL or PPL, execute via REST API,
  and always output the query statement for reuse in OpenSearch Dashboards
  Dev Tools or Query Workbench.
  Use this skill when the user wants to query, aggregate, filter, or analyze
  data in OpenSearch. Covers both Query DSL (JSON _search API) and
  PPL (Piped Processing Language). Includes all REST API endpoints:
  _search, _cat, _mapping, _count, _analyze, _field_caps, _plugins/_ppl, etc.
---

# OpenSearch Query Skill (DSL + PPL)

## Overview

This skill converts natural language data analysis requirements into OpenSearch
queries, executes them via the REST API, and always reports the exact query
statement used — so the user can replay it in Dashboards Dev Tools or Query Workbench.

Two query approaches are supported:
- **DSL** — JSON Query DSL (`_search`, `_count`, `_cat`, etc.)
- **PPL** — Piped Processing Language (`_plugins/_ppl`)

## Prerequisites

- OpenSearch REST API accessible at `http://localhost:13121`
- Credentials `admin / MorenMima@123456`
- The `curl` command is available

## Workflow

### 1. Understand the Requirement

Clarify what the user wants:
- Which index(es) to query?
- Which fields are relevant?
- What filtering / aggregation / grouping is needed?
- Do they need sample data, stats, or a specific answer?
- Which query language do they prefer (DSL or PPL)?

If the user doesn't specify a preference:
- Use **DSL** when: complex nested queries, `bool` logic, range queries,
  custom scoring, or when the user likely wants to run it in **Dev Tools** Discovery
- Use **PPL** when: simple stats/grouping, pipe-style chaining, or the user
  likely wants to run it in **Query Workbench**

### 2. Explore the Data Schema (if needed)

**DSL — Get mapping:**
```
GET /<index>/_mapping
```
```bash
curl -s -u admin:'MorenMima@123456' \
  "http://localhost:13121/<index>/_mapping" | python3 -m json.tool
```

**PPL — Describe index schema:**
```
describe <index>
```
```bash
curl -s -u admin:'MorenMima@123456' \
  -H "Content-Type: application/json" \
  "http://localhost:13121/_plugins/_ppl" \
  -d '{"query":"describe <index>"}' | python3 -m json.tool
```

**DSL — Sample document:**
```
GET /<index>/_search
{
  "size": 1
}
```
```bash
curl -s -u admin:'MorenMima@123456' \
  -H "Content-Type: application/json" \
  "http://localhost:13121/<index>/_search" \
  -d '{"size":1}' | python3 -m json.tool
```

### 3. Build and Execute the Query

Translate the user's requirement into the appropriate query language.

---

#### Category: List / explore indices

| Purpose | DSL | PPL |
|---------|-----|-----|
| List all indices | `GET /_cat/indices?v&s=index` | N/A (use DSL) |
| Get index mapping | `GET /<index>/_mapping` | `describe <index>` |
| Index stats | `GET /<index>/_stats` | N/A |

---

#### Category: Count / Stats

**DSL — Total count:**
```
GET /<index>/_count
```
```bash
curl -s -u admin:'MorenMima@123456' \
  "http://localhost:13121/<index>/_count"
```

**PPL — Total count:**
```
source = <index> | stats count()
```
```bash
curl -s -u admin:'MorenMima@123456' \
  -H "Content-Type: application/json" \
  "http://localhost:13121/_plugins/_ppl" \
  -d '{"query":"source = <index> | stats count()"}' | python3 -m json.tool
```

**PPL — Count with filter:**
```
source = <index> | where <field> = '<value>' | stats count()
```

**PPL — Stats on numeric field:**
```
source = <index> | stats avg(<field>), max(<field>), min(<field>), sum(<field>), count(<field>)
```

---

#### Category: Group / Aggregate

**DSL — Distinct values (terms agg):**
```
GET /<index>/_search
{
  "size": 0,
  "aggs": {
    "my_agg": {
      "terms": {
        "field": "<field>",
        "size": 100
      }
    }
  }
}
```
```bash
curl -s -u admin:'MorenMima@123456' \
  -H "Content-Type: application/json" \
  "http://localhost:13121/<index>/_search" \
  -d '{"size":0,"aggs":{"my_agg":{"terms":{"field":"<field>","size":100}}}}' | python3 -m json.tool
```

**PPL — Group by:**
```
source = <index> | stats count() by <field>
```
```bash
curl -s -u admin:'MorenMima@123456' \
  -H "Content-Type: application/json" \
  "http://localhost:13121/_plugins/_ppl" \
  -d '{"query":"source = <index> | stats count() by <field>"}' | python3 -m json.tool
```

---

#### Category: Filter / Search

**DSL — Bool query with match + range:**
```
GET /<index>/_search
{
  "query": {
    "bool": {
      "must": [
        { "match": { "<field1>": "<value1>" } },
        { "range": { "@timestamp": { "gte": "now-1h" } } }
      ]
    }
  },
  "sort": [{ "@timestamp": "desc" }],
  "size": 20
}
```

**PPL — Filter + sort:**
```
source = <index> | where <field1> = '<value1>' and @timestamp > now() - 1h | sort - @timestamp | head 20
```

**DSL — Count with filter:**
```
GET /<index>/_count
{
  "query": {
    "match": { "<field>": "<value>" }
  }
}
```
```bash
curl -s -u admin:'MorenMima@123456' \
  -H "Content-Type: application/json" \
  "http://localhost:13121/<index>/_count" \
  -d '{"query":{"match":{"<field>":"<value>"}}}'
```

---

#### Category: Time-series

**DSL — Date histogram:**
```
GET /<index>/_search
{
  "size": 0,
  "aggs": {
    "over_time": {
      "date_histogram": {
        "field": "@timestamp",
        "fixed_interval": "1h"
      }
    }
  }
}
```

**PPL — Group by date:**
```
source = <index> | stats count() by span(@timestamp, 1h)
```

---

#### Category: Field stats

**DSL — Stats on numeric field:**
```
GET /<index>/_search
{
  "size": 0,
  "aggs": {
    "stats": {
      "stats": { "field": "<numeric_field>" }
    }
  }
}
```

**PPL — Field stats:**
```
source = <index> | stats avg(<field>), max(<field>), min(<field>)
```

---

### 4. Always Output the Query Statement

**For DSL queries**, format as Dev Tools-compatible syntax:
```
GET /<index>/_search
{
  ...
}
```

**For PPL queries**, format as single-line or multi-line:
```
source = <index> | stats count() by <field>
```

Use this format in your response to the user:
```
**${语言} 语句：**
```${ppl_or_json}
...query...
\```
```

### 5. Execute via REST API

General pattern for **DSL**:
```bash
curl -s -u admin:'MorenMima@123456' \
  -H "Content-Type: application/json" \
  "http://localhost:13121/<endpoint>" \
  -d '<json-body>'
```

General pattern for **PPL**:
```bash
curl -s -u admin:'MorenMima@123456' \
  -H "Content-Type: application/json" \
  "http://localhost:13121/_plugins/_ppl" \
  -d '{"query":"<ppl-statement>"}'
```

Always pipe through `python3 -m json.tool` for readable output.

## Common Field Mappings (OTEL)

For `otel-*` indices, key fields:
- `serviceName` — application/service name (keyword)
- `resource.attributes.service@name` — same value in nested form
- `resource.attributes.host@ip` — host IP (keyword)
- `body` — log message (text)
- `severityText` / `severityNumber` — log level
- `traceId` / `spanId` — tracing context
- `log.attributes.*` — additional log attributes (keyword)

## Dev Tools vs Query Workbench

| Tool | URL | Language |
|------|-----|----------|
| Dev Tools (Console) | `http://localhost:13124/app/dev_tools#/console` | DSL (JSON) |
| Query Workbench | `http://localhost:13124/app/opensearch-query-workbench` | PPL / SQL |
