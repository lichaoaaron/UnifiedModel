#!/usr/bin/env python
"""Generate deterministic UModel incident samples from exported telemetry."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data"
DEFAULT_OUTPUT = ROOT / "outputs" / "mmodel-fault-samples"

FAULT_TYPES = {
    "downstream_timeout": {
        "title": "Downstream service timeout",
        "severity": "P2",
        "trace_match": lambda span: span.get("kind") == "SPAN_KIND_CLIENT"
        and not span.get("span.attributes.db@type"),
        "log_body": "Downstream request timed out; retry budget exhausted",
        "metric_names": [
            "service_request_latency_ms",
            "service_error_rate",
            "service_timeout_count",
        ],
    },
    "redis_saturation": {
        "title": "Redis saturation and rejected calls",
        "severity": "P1",
        "trace_match": lambda span: str(span.get("span.attributes.db@type", "")).lower()
        == "redis",
        "log_body": "JedisConnectionException: Redis command timed out after retries",
        "metric_names": [
            "redis_commands_duration_seconds_total",
            "redis_commands_failed_calls_total",
            "redis_commands_rejected_calls_total",
        ],
    },
    "database_lock_wait": {
        "title": "Database lock wait contention",
        "severity": "P1",
        "trace_match": lambda span: str(span.get("span.attributes.db@type", "")).lower()
        == "sql",
        "log_body": "SQLTransientConnectionException: lock wait timeout exceeded",
        "metric_names": [
            "cmdb_stat_lock_wait_statis_avg_wait_time",
            "cmdb_stat_lock_wait_statis_max_wait_time",
            "cmdb_stat_lock_wait_statis_failed_wait",
        ],
    },
}


def iter_json_array_records(files: Iterable[Path], limit: int | None = None):
    count = 0
    for file_path in sorted(files):
        with file_path.open("r", encoding="utf-8", errors="replace") as stream:
            for raw in stream:
                line = raw.strip()
                if not line or line in ("[", "]"):
                    continue
                if line.endswith(","):
                    line = line[:-1]
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
                count += 1
                if limit and count >= limit:
                    return


def stable_id(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def parse_time(value: str | None) -> datetime:
    if not value:
        return datetime(2026, 6, 3, 1, 0, tzinfo=timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def iso_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def profile_traces(data_dir: Path, limit: int) -> dict[str, list[dict[str, Any]]]:
    traces: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for span in iter_json_array_records((data_dir / "trace").glob("*.json"), limit):
        trace_id = span.get("traceId")
        if trace_id:
            traces[trace_id].append(span)
    return traces


def trace_services(spans: list[dict[str, Any]]) -> set[str]:
    return {span["serviceName"] for span in spans if span.get("serviceName")}


def trace_dependencies(spans: list[dict[str, Any]]) -> set[tuple[str, str]]:
    dependencies: set[tuple[str, str]] = set()
    for span in spans:
        child = span.get("serviceName")
        for link in span.get("links", []):
            parent = link.get("attributes", {}).get("parent@service")
            if parent and child and parent != child:
                dependencies.add((parent, child))
    return dependencies


def span_has_complete_ancestry(
    span_id: str | None, span_by_id: dict[str, dict[str, Any]]
) -> bool:
    if not span_id or span_id not in span_by_id:
        return False

    visited_ids: set[str] = set()
    current_span = span_by_id[span_id]
    while current_span is not None:
        current_span_id = current_span.get("spanId")
        if not current_span_id or current_span_id in visited_ids:
            return False
        visited_ids.add(current_span_id)

        parent_span_id = current_span.get("parentSpanId")
        if not parent_span_id:
            return True
        current_span = span_by_id.get(parent_span_id)

    return False


def choose_scenarios(
    traces: dict[str, list[dict[str, Any]]], per_type: int
) -> list[dict[str, Any]]:
    ranked = sorted(
        traces.items(),
        key=lambda item: (len(trace_services(item[1])), len(item[1])),
        reverse=True,
    )
    chosen: list[dict[str, Any]] = []
    used: set[str] = set()
    for fault_type, config in FAULT_TYPES.items():
        for trace_id, spans in ranked:
            if trace_id in used or len(trace_services(spans)) < 2:
                continue
            span_by_id = {
                span.get("spanId"): span for span in spans if span.get("spanId")
            }
            targets = sorted(
                (
                    span
                    for span in spans
                    if config["trace_match"](span)
                    and span_has_complete_ancestry(span.get("spanId"), span_by_id)
                ),
                key=lambda span: bool(span.get("span.attributes.db@instance")),
                reverse=True,
            )
            if fault_type in {"redis_saturation", "database_lock_wait"}:
                targets = [
                    span for span in targets if span.get("span.attributes.db@instance")
                ]
            if not targets:
                continue
            chosen.append(
                {
                    "fault_type": fault_type,
                    "source_trace_id": trace_id,
                    "spans": spans,
                    "target_span_id": targets[0].get("spanId"),
                }
            )
            used.add(trace_id)
            if sum(item["fault_type"] == fault_type for item in chosen) >= per_type:
                break
    return chosen


def collect_source_logs(
    data_dir: Path, trace_ids: set[str], services: set[str], limit: int
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    by_trace: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_service: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in iter_json_array_records((data_dir / "log").glob("*.json"), limit):
        trace_id = record.get("traceId")
        service = record.get("serviceName")
        if trace_id in trace_ids and len(by_trace[trace_id]) < 20:
            by_trace[trace_id].append(record)
        if service in services and len(by_service[service]) < 5:
            by_service[service].append(record)
    return by_trace, by_service


def service_entity(name: str, degraded: bool, first_seen: int, last_seen: int):
    entity_id = stable_id(name)
    return {
        "__domain__": "platform",
        "__entity_type__": "platform.service",
        "__entity_id__": entity_id,
        "__category__": "entity",
        "__method__": "Update",
        "__first_observed_time__": first_seen,
        "__last_observed_time__": last_seen,
        "__keep_alive_seconds__": 3600,
        "id": entity_id,
        "display_name": name,
        "status": "degraded" if degraded else "healthy",
        "owner": "telemetry-sample",
        "sla_tier": "gold",
        "language": "java",
        "runtime_platform": "unknown",
        "environment": "sample",
        "exposure": "internal",
        "contact_channel": "#mmodel-fault-samples",
        "business_value": "Service discovered from exported telemetry",
    }


def middleware_entity(
    middleware_type: str,
    instance: str,
    degraded: bool,
    first_seen: int,
    last_seen: int,
):
    entity_type = f"platform.{middleware_type}"
    semantic_id = f"{middleware_type}:{instance}"
    entity_id = stable_id(semantic_id)
    display_instance = instance
    if middleware_type == "database" and "currentSchema=" in instance:
        display_instance = instance.split("currentSchema=", 1)[1].split("&", 1)[0]
    result = {
        "__domain__": "platform",
        "__entity_type__": entity_type,
        "__entity_id__": entity_id,
        "__category__": "entity",
        "__method__": "Update",
        "__first_observed_time__": first_seen,
        "__last_observed_time__": last_seen,
        "__keep_alive_seconds__": 3600,
        "id": entity_id,
        "display_name": f"{middleware_type.title()} {display_instance}",
        "instance": instance,
        "status": "degraded" if degraded else "healthy",
        "source": "trace span.attributes.db@instance",
    }
    if middleware_type == "database":
        result["engine"] = "sql"
    return result


def target_middleware(fault_type: str, target: dict[str, Any]):
    if fault_type == "redis_saturation":
        middleware_type = "redis"
    elif fault_type == "database_lock_wait":
        middleware_type = "database"
    else:
        return None
    instance = target.get("span.attributes.db@instance") or f"unknown-{middleware_type}"
    return {
        "type": middleware_type,
        "entity_type": f"platform.{middleware_type}",
        "instance": instance,
        "id": stable_id(f"{middleware_type}:{instance}"),
    }


def incident_entity(
    scenario_id: str,
    title: str,
    severity: str,
    impacted_service: str,
    detected_at: str,
    first_seen: int,
    last_seen: int,
):
    entity_id = stable_id(scenario_id)
    return {
        "__domain__": "platform",
        "__entity_type__": "platform.incident",
        "__entity_id__": entity_id,
        "__category__": "entity",
        "__method__": "Update",
        "__first_observed_time__": first_seen,
        "__last_observed_time__": last_seen,
        "__keep_alive_seconds__": 3600,
        "id": entity_id,
        "display_name": title,
        "severity": severity,
        "status": "investigating",
        "impacted_service": impacted_service,
        "detected_at": detected_at,
        "oncall_responder": "mmodel-sample-generator",
        "escalation_channel": "#mmodel-fault-samples",
        "initial_hypothesis": title,
        "customer_impact": "Synthetic incident for MModel closed-loop validation",
    }


def relation(
    src_type: str,
    src_id: str,
    dest_type: str,
    dest_id: str,
    relation_type: str,
    display_name: str,
    first_seen: int,
    last_seen: int,
):
    return {
        "__src_domain__": "platform",
        "__src_entity_type__": src_type,
        "__src_entity_id__": src_id,
        "__dest_domain__": "platform",
        "__dest_entity_type__": dest_type,
        "__dest_entity_id__": dest_id,
        "__relation_type__": relation_type,
        "__category__": "entity_link",
        "__method__": "Update",
        "__first_observed_time__": first_seen,
        "__last_observed_time__": last_seen,
        "__keep_alive_seconds__": 3600,
        "display_name": display_name,
    }


def select_closed_trace_subset(
    source_spans: list[dict[str, Any]], target_span_id: str, limit: int = 100
) -> list[dict[str, Any]]:
    span_by_id = {
        span.get("spanId"): span for span in source_spans if span.get("spanId")
    }
    target = span_by_id.get(target_span_id)
    if target is None:
        raise ValueError(f"target span not found: {target_span_id}")

    selected_ids: set[str] = set()
    current_span = target
    visited_ids: set[str] = set()
    while current_span is not None:
        span_id = current_span.get("spanId")
        if not span_id or span_id in visited_ids:
            break
        selected_ids.add(span_id)
        visited_ids.add(span_id)
        parent_span_id = current_span.get("parentSpanId")
        if not parent_span_id:
            break
        current_span = span_by_id.get(parent_span_id)

    # Fill the remaining budget only with spans whose parents are already selected,
    # so the exported subset stays internally connected.
    while len(selected_ids) < limit:
        added = False
        for span in source_spans:
            span_id = span.get("spanId")
            if not span_id or span_id in selected_ids:
                continue
            parent_span_id = span.get("parentSpanId")
            if parent_span_id and parent_span_id not in selected_ids:
                continue
            selected_ids.add(span_id)
            added = True
            if len(selected_ids) >= limit:
                break
        if not added:
            break

    return [span for span in source_spans if span.get("spanId") in selected_ids]


def inject_trace(
    source_spans: list[dict[str, Any]],
    source_trace_id: str,
    synthetic_trace_id: str,
    target_span_id: str,
    fault_type: str,
) -> list[dict[str, Any]]:
    selected = copy.deepcopy(
        select_closed_trace_subset(source_spans, target_span_id, limit=100)
    )
    for span in selected:
        span["source.traceId"] = source_trace_id
        span["traceId"] = synthetic_trace_id
        span["sample.scenario_fault_type"] = fault_type
        for link in span.get("links", []):
            if link.get("traceId") == source_trace_id:
                link["traceId"] = synthetic_trace_id
        if span.get("spanId") == target_span_id:
            span["durationInNanos"] = max(int(span.get("durationInNanos", 0)) * 50, 5_000_000_000)
            span["status.code"] = 2
            span["status.message"] = FAULT_TYPES[fault_type]["title"]
            span["sample.injected_fault"] = True
    return selected


def inject_logs(
    scenario_id: str,
    fault_type: str,
    source_trace_id: str,
    synthetic_trace_id: str,
    service: str,
    start: datetime,
    source_logs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, source in enumerate(source_logs[:8]):
        record = copy.deepcopy(source)
        record["source.traceId"] = record.get("traceId") or source_trace_id
        record["traceId"] = synthetic_trace_id
        record["sample.scenario_id"] = scenario_id
        record["sample.injected_fault"] = False
        result.append(record)
    for index in range(6):
        timestamp = start + timedelta(seconds=20 * index)
        result.append(
            {
                "traceId": synthetic_trace_id,
                "spanId": "",
                "severityText": "ERROR",
                "severityNumber": 17,
                "time": iso_time(timestamp),
                "observedTimestamp": iso_time(timestamp + timedelta(milliseconds=50)),
                "serviceName": service,
                "body": FAULT_TYPES[fault_type]["log_body"],
                "resource.attributes.service@name": service,
                "log.attributes.trace_id": synthetic_trace_id,
                "log.attributes.severity_text": "ERROR",
                "sample.scenario_id": scenario_id,
                "sample.injected_fault": True,
                "source.traceId": source_trace_id,
            }
        )
    return result


def inject_metrics(
    scenario_id: str, fault_type: str, service: str, start: datetime
) -> list[dict[str, Any]]:
    records = []
    for metric_index, metric_name in enumerate(FAULT_TYPES[fault_type]["metric_names"]):
        baseline = 10.0 * (metric_index + 1)
        for point in range(9):
            multiplier = [1.0, 1.1, 1.0, 3.0, 7.0, 10.0, 8.0, 3.0, 1.2][point]
            records.append(
                {
                    "unit": "",
                    "exemplars": [],
                    "kind": "GAUGE",
                    "name": metric_name,
                    "flags": 0,
                    "description": "Controlled synthetic fault metric derived from exported telemetry",
                    "startTime": iso_time(start - timedelta(minutes=3)),
                    "time": iso_time(start + timedelta(minutes=point - 3)),
                    "serviceName": service,
                    "value": baseline * multiplier,
                    "resource.attributes.service@name": service,
                    "sample.scenario_id": scenario_id,
                    "sample.injected_fault": point >= 3 and point <= 7,
                }
            )
    return records


def generate(args: argparse.Namespace) -> dict[str, Any]:
    traces = profile_traces(args.data_dir, args.trace_scan_limit)
    selected = choose_scenarios(traces, args.per_type)
    expected_count = args.per_type * len(FAULT_TYPES)
    if len(selected) != expected_count:
        raise RuntimeError(f"selected {len(selected)} scenarios, expected {expected_count}")

    selected_trace_ids = {item["source_trace_id"] for item in selected}
    selected_services = set().union(*(trace_services(item["spans"]) for item in selected))
    selected_services.update(
        service
        for item in selected
        for dependency in trace_dependencies(item["spans"])
        for service in dependency
    )
    logs_by_trace, logs_by_service = collect_source_logs(
        args.data_dir, selected_trace_ids, selected_services, args.log_scan_limit
    )

    entities: dict[tuple[str, str], dict[str, Any]] = {}
    relations: dict[tuple[str, str, str], dict[str, Any]] = {}
    all_logs: list[dict[str, Any]] = []
    all_metrics: list[dict[str, Any]] = []
    all_traces: list[dict[str, Any]] = []
    scenarios: list[dict[str, Any]] = []
    counters: dict[str, int] = defaultdict(int)

    for item in selected:
        fault_type = item["fault_type"]
        counters[fault_type] += 1
        scenario_id = f"fault-{fault_type.replace('_', '-')}-{counters[fault_type]:03d}"
        spans = item["spans"]
        target = next(
            span for span in spans if span.get("spanId") == item["target_span_id"]
        )
        root_service = target.get("serviceName") or sorted(trace_services(spans))[0]
        dependencies = trace_dependencies(spans)
        services = sorted(
            trace_services(spans)
            | {service for dependency in dependencies for service in dependency}
        )
        impacted_service = next(
            (parent for parent, child in dependencies if child == root_service),
            services[0],
        )
        start = min(parse_time(span.get("startTime")) for span in spans)
        end = start + timedelta(minutes=8)
        first_seen, last_seen = int(start.timestamp()), int(end.timestamp())
        synthetic_trace_id = stable_id(scenario_id + ":" + item["source_trace_id"])
        title = f"{FAULT_TYPES[fault_type]['title']}: {impacted_service}"
        middleware = target_middleware(fault_type, target)

        entities[("platform.incident", stable_id(scenario_id))] = incident_entity(
            scenario_id,
            title,
            FAULT_TYPES[fault_type]["severity"],
            impacted_service,
            iso_time(start),
            first_seen,
            last_seen,
        )
        for service in services:
            entities[("platform.service", stable_id(service))] = service_entity(
                service, service in {root_service, impacted_service}, first_seen, last_seen
            )
        if middleware:
            entities[(middleware["entity_type"], middleware["id"])] = middleware_entity(
                middleware["type"],
                middleware["instance"],
                True,
                first_seen,
                last_seen,
            )
        for parent, child in dependencies:
            key = (stable_id(parent), "calls", stable_id(child))
            relations[key] = relation(
                "platform.service",
                stable_id(parent),
                "platform.service",
                stable_id(child),
                "calls",
                f"{parent} calls {child}",
                first_seen,
                last_seen,
            )
        for service in sorted({root_service, impacted_service}):
            key = (stable_id(scenario_id), "impacts", stable_id(service))
            relations[key] = relation(
                "platform.incident",
                stable_id(scenario_id),
                "platform.service",
                stable_id(service),
                "impacts",
                f"{scenario_id} impacts {service}",
                first_seen,
                last_seen,
            )
        if middleware:
            dependency_key = (
                stable_id(root_service),
                "depends_on",
                middleware["id"],
            )
            relations[dependency_key] = relation(
                "platform.service",
                stable_id(root_service),
                middleware["entity_type"],
                middleware["id"],
                "depends_on",
                f"{root_service} depends on {middleware['type']} {middleware['instance']}",
                first_seen,
                last_seen,
            )
            cause_key = (stable_id(scenario_id), "caused_by", middleware["id"])
            relations[cause_key] = relation(
                "platform.incident",
                stable_id(scenario_id),
                middleware["entity_type"],
                middleware["id"],
                "caused_by",
                f"{scenario_id} caused by {middleware['type']} {middleware['instance']}",
                first_seen,
                last_seen,
            )

        injected_traces = inject_trace(
            spans,
            item["source_trace_id"],
            synthetic_trace_id,
            item["target_span_id"],
            fault_type,
        )
        source_logs = logs_by_trace[item["source_trace_id"]] or logs_by_service[root_service]
        injected_logs = inject_logs(
            scenario_id,
            fault_type,
            item["source_trace_id"],
            synthetic_trace_id,
            root_service,
            start,
            source_logs,
        )
        injected_metrics = inject_metrics(scenario_id, fault_type, root_service, start)
        all_traces.extend(injected_traces)
        all_logs.extend(injected_logs)
        all_metrics.extend(injected_metrics)

        scenarios.append(
            {
                "scenario_id": scenario_id,
                "title": title,
                "fault_type": fault_type,
                "severity": FAULT_TYPES[fault_type]["severity"],
                "source_trace_id": item["source_trace_id"],
                "synthetic_trace_id": synthetic_trace_id,
                "start_time": iso_time(start),
                "end_time": iso_time(end),
                "root_cause_service": root_service,
                "root_cause_middleware": middleware,
                "impacted_service": impacted_service,
                "services": services,
                "dependencies": [
                    {"from": parent, "to": child}
                    for parent, child in sorted(dependencies)
                ],
                "expected_diagnosis": {
                    "symptom": FAULT_TYPES[fault_type]["title"],
                    "probable_root_cause": (
                        middleware["instance"] if middleware else root_service
                    ),
                    "root_cause_entity_type": (
                        middleware["entity_type"] if middleware else "platform.service"
                    ),
                    "blast_radius": sorted({root_service, impacted_service}),
                    "evidence": {
                        "trace_id": synthetic_trace_id,
                        "injected_span_id": item["target_span_id"],
                        "metric_names": FAULT_TYPES[fault_type]["metric_names"],
                    },
                },
            }
        )

    output = args.output_dir
    write_json(output / "sample-data" / "entities.json", list(entities.values()))
    write_json(output / "sample-data" / "relations.json", list(relations.values()))
    write_json(output / "evidence" / "logs.json", all_logs)
    write_json(output / "evidence" / "metrics.json", all_metrics)
    write_json(output / "evidence" / "traces.json", all_traces)
    write_json(output / "scenarios" / "index.json", scenarios)
    write_json(
        output / "scenarios" / "demo-scenarios.json",
        [next(s for s in scenarios if s["fault_type"] == fault) for fault in FAULT_TYPES],
    )
    for scenario in scenarios:
        write_json(output / "scenarios" / f"{scenario['scenario_id']}.json", scenario)

    manifest = {
        "sample": "mmodel-fault-samples",
        "title": "MModel Controlled Fault Samples",
        "description": "Deterministic fault samples derived from exported log, metric, and trace data.",
        "schema_pack": "examples/incident-investigation",
        "additional_schema_pack": "outputs/mmodel-fault-samples/model-pack",
        "data_source": str(args.data_dir),
        "generation": {
            "script": "scripts/generate_mmodel_fault_samples.py",
            "trace_scan_limit": args.trace_scan_limit,
            "log_scan_limit": args.log_scan_limit,
            "per_type": args.per_type,
        },
        "counts": {
            "scenarios": len(scenarios),
            "entities": len(entities),
            "relations": len(relations),
            "logs": len(all_logs),
            "metrics": len(all_metrics),
            "traces": len(all_traces),
        },
        "files": {
            "entities": "sample-data/entities.json",
            "relations": "sample-data/relations.json",
            "scenarios": "scenarios/index.json",
            "demo_scenarios": "scenarios/demo-scenarios.json",
            "logs": "evidence/logs.json",
            "metrics": "evidence/metrics.json",
            "traces": "evidence/traces.json",
        },
        "limitations": [
            "Fault signals are controlled synthetic mutations of exported telemetry.",
            "The samples validate the MModel closed loop but are not production incident ground truth.",
        ],
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--trace-scan-limit", type=int, default=180_000)
    parser.add_argument("--log-scan-limit", type=int, default=300_000)
    parser.add_argument("--per-type", type=int, default=4)
    args = parser.parse_args()
    manifest = generate(args)
    print(json.dumps(manifest["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
