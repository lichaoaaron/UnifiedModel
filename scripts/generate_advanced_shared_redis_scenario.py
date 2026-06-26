#!/usr/bin/env python
"""
Generate an advanced MModel fault sample pack with a complex shared-Redis scenario.

Design goals
------------
- Keep the existing `outputs/mmodel-fault-samples` pack unchanged.
- Produce a separate `outputs/mmodel-fault-samples-advanced` pack.
- Reuse the existing sample model-pack and entity graph so the scenario stays
  compatible with the current UnifiedModel / MModel demo chain.
- Add one harder scenario where two entry flows degrade at the same time, both
  converge to the same Redis dependency, and multiple non-root candidates exist.

This scenario is intentionally designed so that:
- Trace-only inspection yields multiple plausible candidates.
- Log-only inspection is noisy and does not directly leak the answer.
- Metric-only inspection shows multiple degraded services.
- Object-centered convergence is needed to stabilize root-cause and impact scope.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASE_OUTPUT = ROOT / "outputs" / "mmodel-fault-samples"
ADVANCED_OUTPUT = ROOT / "outputs" / "mmodel-fault-samples-advanced"

SCENARIO_ID = "fault-shared-redis-contention-001"
FAULT_TYPE = "shared_redis_contention"
TITLE = "Shared Redis contention across user validation and account update"
SCENARIO_START = "2026-06-03T01:05:45.556Z"
SCENARIO_END = "2026-06-03T01:13:45.556Z"
PRIMARY_TRACE_ID = hashlib.md5(f"{SCENARIO_ID}:order".encode("utf-8")).hexdigest()
SECONDARY_TRACE_ID = hashlib.md5(f"{SCENARIO_ID}:coupon".encode("utf-8")).hexdigest()

REDIS_INSTANCE = "10.252.199.142:6389"
REDIS_ENTITY_ID = "a824e83ca293bcb0d98d076498213492"
REDIS_ENTITY_TYPE = "platform.redis"

SERVICE_IDS = {
    "ais-amc": "c816e0060f094cc2d5d546337919483a",
    "ais-application-service": "eda4ed002b6f98a9ff9ba251f23bf97f",
    "ais-configure": "d88dade5a33efa4d2708f4e7e49df246",
    "ais-gold": "6b779ccaf180841b1e4ff646d80408dc",
    "ais-mmj-service": "a29f9f20d51bc8ac777bc0672fbe3945",
    "ais-pmc": "ed1576363f55fd4202c4b3301eab6d35",
    "csc-cm-it": "49c3942131c536919668a0796b95b1c9",
    "iam-manage": "6b70075b7307bca4fb596a3a84c96375",
}


def stable_id(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def iso_time(start: str, delta_secs: float = 0.0) -> str:
    dt = parse_time(start) + timedelta(seconds=delta_secs)
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def epoch_seconds(value: str) -> int:
    return int(parse_time(value).timestamp())


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def copy_base_pack() -> None:
    if ADVANCED_OUTPUT.exists():
        shutil.rmtree(ADVANCED_OUTPUT)
    shutil.copytree(BASE_OUTPUT, ADVANCED_OUTPUT)


def relation_record(src_type: str, src_id: str, dest_type: str, dest_id: str, relation_type: str, display_name: str, ts: str) -> dict[str, Any]:
    first = epoch_seconds(ts)
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
        "__first_observed_time__": first,
        "__last_observed_time__": first + 480,
        "__keep_alive_seconds__": 3600,
        "display_name": display_name,
    }


def incident_entity() -> dict[str, Any]:
    incident_id = stable_id(SCENARIO_ID)
    first = epoch_seconds(SCENARIO_START)
    return {
        "__domain__": "platform",
        "__entity_type__": "platform.incident",
        "__entity_id__": incident_id,
        "__category__": "entity",
        "__method__": "Update",
        "__first_observed_time__": first,
        "__last_observed_time__": first + 480,
        "__keep_alive_seconds__": 3600,
        "id": incident_id,
        "display_name": TITLE,
        "severity": "P0",
        "status": "investigating",
        "impacted_service": "multiple-entry-services",
        "detected_at": SCENARIO_START,
        "oncall_responder": "mmodel-advanced-sample-generator",
        "escalation_channel": "#mmodel-fault-samples-advanced",
        "initial_hypothesis": "Simultaneous gateway degradations with a likely shared dependency bottleneck",
        "customer_impact": "Synthetic advanced incident for object-centered root-cause and impact-scope validation",
    }


def scenario_payload() -> dict[str, Any]:
    return {
        "scenario_id": SCENARIO_ID,
        "title": TITLE,
        "fault_type": FAULT_TYPE,
        "severity": "P0",
        "source_trace_id": PRIMARY_TRACE_ID,
        "synthetic_trace_id": PRIMARY_TRACE_ID,
        "supporting_trace_ids": [PRIMARY_TRACE_ID, SECONDARY_TRACE_ID],
        "start_time": SCENARIO_START,
        "end_time": SCENARIO_END,
        "root_cause_service": "ais-amc",
        "root_cause_middleware": {
            "type": "redis",
            "entity_type": REDIS_ENTITY_TYPE,
            "instance": REDIS_INSTANCE,
            "id": REDIS_ENTITY_ID,
        },
        "impacted_service": "multiple-entry-services",
        "entry_points": [
            {
                "service": "csc-cm-it",
                "api": "/csc/services/UserInfoValidate",
                "trace_id": PRIMARY_TRACE_ID,
            },
            {
                "service": "ais-configure",
                "api": "/ais/app/open/appAccount/updateLastAccessDate",
                "trace_id": SECONDARY_TRACE_ID,
            },
        ],
        "services": [
            "ais-amc",
            "ais-application-service",
            "ais-configure",
            "ais-gold",
            "ais-mmj-service",
            "ais-pmc",
            "csc-cm-it",
            "iam-manage",
        ],
        "dependencies": [
            {"from": "csc-cm-it", "to": "ais-amc"},
            {"from": "csc-cm-it", "to": "ais-application-service"},
            {"from": "ais-configure", "to": "ais-amc"},
            {"from": "ais-configure", "to": "ais-gold"},
            {"from": "ais-gold", "to": "iam-manage"},
            {"from": "ais-application-service", "to": "ais-pmc"},
            {"from": "ais-amc", "to": REDIS_INSTANCE},
        ],
        "expected_diagnosis": {
            "symptom": "User validation and account update both become slow with partial failures in the same time window",
            "probable_root_cause": REDIS_INSTANCE,
            "root_cause_entity_type": REDIS_ENTITY_TYPE,
            "blast_radius": [
                "csc-cm-it",
                "ais-configure",
                "ais-amc",
                "ais-application-service",
            ],
            "evidence": {
                "trace_id": PRIMARY_TRACE_ID,
                "supporting_trace_ids": [SECONDARY_TRACE_ID],
                "injected_span_ids": ["advredis0005", "advredis0012"],
                "metric_names": [
                    "redis_commands_duration_seconds_total",
                    "redis_commands_rejected_calls_total",
                    "service_request_latency_ms",
                    "service_error_rate",
                ],
            },
        },
        "merely_observed_nodes": [
            {
                "service": "ais-pmc",
                "reason": "Appears in the user-validation trace as a downstream side call but stays healthy and does not share the Redis bottleneck.",
                "node_type": "merely_observed_node",
            },
            {
                "service": "ais-mmj-service",
                "reason": "Appears in the account-update trace path but only serves a fast feature-flag read and should not be counted in impact scope.",
                "node_type": "merely_observed_node",
            },
            {
                "service": "iam-manage",
                "reason": "Shows a nearby Redis read on a different instance and is easy to over-count without object-level dependency pruning.",
                "node_type": "merely_observed_node",
            },
        ],
        "noise_nodes": [
            {
                "service": "csc-cm-it",
                "reason": "Entry service has the highest user-facing latency in one branch and can be misidentified as root cause in trace-only inspection.",
                "node_type": "competing_candidate",
            },
            {
                "service": "ais-configure",
                "reason": "The second entry service shows retries and queue pressure, which makes it look like an independent failure domain.",
                "node_type": "competing_candidate",
            },
            {
                "service": "ais-application-service",
                "reason": "Shows high latency and WARN logs as a propagated symptom that can be mistaken for the shared bottleneck.",
                "node_type": "cascaded_slow_misleading",
            },
            {
                "service": "ais-gold",
                "reason": "Carries coupon-flow noise and a nearby IAM lookup, making the path look broader than the true impact set.",
                "node_type": "competing_candidate",
            },
        ],
        "object_centered_story": {
            "why_plain_observability_is_hard": [
                "Two user-facing APIs degrade in the same time window but with different local symptoms.",
                "Both traces contain multiple slow or warning-producing services, not just the shared Redis call.",
                "A nearby IAM Redis read on another instance creates an additional false shared-cache narrative.",
            ],
            "why_mmodel_should_help": [
                "Object topology converges both entry flows on ais-amc and then on the same redis entity 10.252.199.142:6389.",
                "Impact scope should exclude merely observed nodes such as ais-pmc, ais-mmj-service, and the unrelated IAM Redis read.",
                "Candidate root cause should prefer the shared Redis dependency over the highest-latency entry service.",
            ],
        },
        "hardening": {
            "advanced": True,
            "version": "v1",
            "intent": "Multi-entry shared dependency scenario designed to demonstrate that object-centered convergence outperforms raw telemetry scanning for root-cause and impact analysis.",
        },
    }


def trace_spans() -> list[dict[str, Any]]:
    return [
        {
            "traceId": PRIMARY_TRACE_ID,
            "spanId": "advredis0001",
            "parentSpanId": "",
            "kind": "SPAN_KIND_SERVER",
            "serviceName": "csc-cm-it",
            "name": "POST:/csc/services/UserInfoValidate",
            "startTime": iso_time(SCENARIO_START, 0.0),
            "endTime": iso_time(SCENARIO_START, 4.2),
            "durationInNanos": 4_200_000_000,
            "status.code": 1,
            "status.message": "UserInfoValidate degraded under downstream contention",
            "resource.attributes.service@name": "csc-cm-it",
            "sample.scenario_id": SCENARIO_ID,
            "sample.scenario_fault_type": FAULT_TYPE,
        },
        {
            "traceId": PRIMARY_TRACE_ID,
            "spanId": "advredis0002",
            "parentSpanId": "advredis0001",
            "kind": "SPAN_KIND_CLIENT",
            "serviceName": "csc-cm-it",
            "name": "POST:/amc/open/token/validate",
            "startTime": iso_time(SCENARIO_START, 0.1),
            "endTime": iso_time(SCENARIO_START, 3.6),
            "durationInNanos": 3_500_000_000,
            "status.code": 1,
            "status.message": "Waiting for shared dependency-backed validation context",
            "resource.attributes.service@name": "csc-cm-it",
            "sample.scenario_id": SCENARIO_ID,
            "sample.scenario_fault_type": FAULT_TYPE,
            "sample.noise_type": "entry_service_competing_candidate",
        },
        {
            "traceId": PRIMARY_TRACE_ID,
            "spanId": "advredis0003",
            "parentSpanId": "advredis0001",
            "kind": "SPAN_KIND_CLIENT",
            "serviceName": "csc-cm-it",
            "name": "POST:/ais/app/open/app/getAppListByAppCode",
            "startTime": iso_time(SCENARIO_START, 0.2),
            "endTime": iso_time(SCENARIO_START, 2.9),
            "durationInNanos": 2_700_000_000,
            "status.code": 1,
            "status.message": "Config fan-out also degraded, but not the shared root bottleneck",
            "resource.attributes.service@name": "csc-cm-it",
            "sample.scenario_id": SCENARIO_ID,
            "sample.scenario_fault_type": FAULT_TYPE,
            "sample.noise_type": "cascaded_slow_misleading",
        },
        {
            "traceId": PRIMARY_TRACE_ID,
            "spanId": "advredis0004",
            "parentSpanId": "advredis0002",
            "kind": "SPAN_KIND_SERVER",
            "serviceName": "ais-amc",
            "name": "POST:/amc/open/token/validate",
            "startTime": iso_time(SCENARIO_START, 0.25),
            "endTime": iso_time(SCENARIO_START, 3.55),
            "durationInNanos": 3_300_000_000,
            "status.code": 1,
            "status.message": "AMC delayed while waiting for shared Redis validation data",
            "resource.attributes.service@name": "ais-amc",
            "sample.scenario_id": SCENARIO_ID,
            "sample.scenario_fault_type": FAULT_TYPE,
        },
        {
            "traceId": PRIMARY_TRACE_ID,
            "spanId": "advredis0005",
            "parentSpanId": "advredis0004",
            "kind": "SPAN_KIND_CLIENT",
            "serviceName": "ais-amc",
            "name": "Redisson/EVAL",
            "startTime": iso_time(SCENARIO_START, 0.35),
            "endTime": iso_time(SCENARIO_START, 3.45),
            "durationInNanos": 3_100_000_000,
            "status.code": 2,
            "status.message": "Redis saturation and rejected calls on shared cluster",
            "span.attributes.db@type": "Redis",
            "span.attributes.db@instance": REDIS_INSTANCE,
            "resource.attributes.service@name": "ais-amc",
            "sample.scenario_id": SCENARIO_ID,
            "sample.scenario_fault_type": FAULT_TYPE,
            "sample.injected_fault": True,
        },
        {
            "traceId": PRIMARY_TRACE_ID,
            "spanId": "advredis0006",
            "parentSpanId": "advredis0003",
            "kind": "SPAN_KIND_SERVER",
            "serviceName": "ais-application-service",
            "name": "POST:/ais/app/open/app/getAppListByAppCode",
            "startTime": iso_time(SCENARIO_START, 0.30),
            "endTime": iso_time(SCENARIO_START, 2.75),
            "durationInNanos": 2_450_000_000,
            "status.code": 1,
            "status.message": "Downstream configuration read slowed by propagated contention",
            "resource.attributes.service@name": "ais-application-service",
            "sample.scenario_id": SCENARIO_ID,
            "sample.scenario_fault_type": FAULT_TYPE,
            "sample.noise_type": "cascaded_slow_misleading",
        },
        {
            "traceId": PRIMARY_TRACE_ID,
            "spanId": "advredis0007",
            "parentSpanId": "advredis0006",
            "kind": "SPAN_KIND_CLIENT",
            "serviceName": "ais-application-service",
            "name": "GET:/pmc/policy/cache/reload",
            "startTime": iso_time(SCENARIO_START, 0.55),
            "endTime": iso_time(SCENARIO_START, 0.67),
            "durationInNanos": 120_000_000,
            "status.code": 0,
            "status.message": "",
            "resource.attributes.service@name": "ais-application-service",
            "sample.scenario_id": SCENARIO_ID,
            "sample.scenario_fault_type": FAULT_TYPE,
            "sample.noise_type": "merely_observed",
        },
        {
            "traceId": SECONDARY_TRACE_ID,
            "spanId": "advredis0008",
            "parentSpanId": "",
            "kind": "SPAN_KIND_SERVER",
            "serviceName": "ais-configure",
            "name": "/ais/app/open/appAccount/updateLastAccessDate",
            "startTime": iso_time(SCENARIO_START, 8.0),
            "endTime": iso_time(SCENARIO_START, 11.9),
            "durationInNanos": 3_900_000_000,
            "status.code": 1,
            "status.message": "Account update degraded under shared dependency contention",
            "resource.attributes.service@name": "ais-configure",
            "sample.scenario_id": SCENARIO_ID,
            "sample.scenario_fault_type": FAULT_TYPE,
        },
        {
            "traceId": SECONDARY_TRACE_ID,
            "spanId": "advredis0009",
            "parentSpanId": "advredis0008",
            "kind": "SPAN_KIND_CLIENT",
            "serviceName": "ais-configure",
            "name": "POST:/authn/check/prelogin",
            "startTime": iso_time(SCENARIO_START, 8.1),
            "endTime": iso_time(SCENARIO_START, 10.9),
            "durationInNanos": 2_800_000_000,
            "status.code": 1,
            "status.message": "Entry service queues and retries while waiting for AMC",
            "resource.attributes.service@name": "ais-configure",
            "sample.scenario_id": SCENARIO_ID,
            "sample.scenario_fault_type": FAULT_TYPE,
            "sample.noise_type": "entry_service_competing_candidate",
        },
        {
            "traceId": SECONDARY_TRACE_ID,
            "spanId": "advredis0010",
            "parentSpanId": "advredis0008",
            "kind": "SPAN_KIND_CLIENT",
            "serviceName": "ais-configure",
            "name": "GET:/ais/app/open/gold/app/getAppAndAccountInfo",
            "startTime": iso_time(SCENARIO_START, 8.2),
            "endTime": iso_time(SCENARIO_START, 10.6),
            "durationInNanos": 2_400_000_000,
            "status.code": 1,
            "status.message": "Account-update path fans out to gold and looks independently degraded",
            "resource.attributes.service@name": "ais-configure",
            "sample.scenario_id": SCENARIO_ID,
            "sample.scenario_fault_type": FAULT_TYPE,
            "sample.noise_type": "cascaded_slow_misleading",
        },
        {
            "traceId": SECONDARY_TRACE_ID,
            "spanId": "advredis0011",
            "parentSpanId": "advredis0009",
            "kind": "SPAN_KIND_SERVER",
            "serviceName": "ais-amc",
            "name": "POST:/authn/check/prelogin",
            "startTime": iso_time(SCENARIO_START, 8.25),
            "endTime": iso_time(SCENARIO_START, 10.95),
            "durationInNanos": 2_700_000_000,
            "status.code": 1,
            "status.message": "AMC delayed while resolving auth prelogin state from shared Redis",
            "resource.attributes.service@name": "ais-amc",
            "sample.scenario_id": SCENARIO_ID,
            "sample.scenario_fault_type": FAULT_TYPE,
        },
        {
            "traceId": SECONDARY_TRACE_ID,
            "spanId": "advredis0012",
            "parentSpanId": "advredis0011",
            "kind": "SPAN_KIND_CLIENT",
            "serviceName": "ais-amc",
            "name": "Redisson/EVAL",
            "startTime": iso_time(SCENARIO_START, 8.35),
            "endTime": iso_time(SCENARIO_START, 10.85),
            "durationInNanos": 2_500_000_000,
            "status.code": 2,
            "status.message": "Redis saturation and rejected calls on shared cluster",
            "span.attributes.db@type": "Redis",
            "span.attributes.db@instance": REDIS_INSTANCE,
            "resource.attributes.service@name": "ais-amc",
            "sample.scenario_id": SCENARIO_ID,
            "sample.scenario_fault_type": FAULT_TYPE,
            "sample.injected_fault": True,
        },
        {
            "traceId": SECONDARY_TRACE_ID,
            "spanId": "advredis0013",
            "parentSpanId": "advredis0010",
            "kind": "SPAN_KIND_CLIENT",
            "serviceName": "ais-gold",
            "name": "GET:/imc/user/open/detail",
            "startTime": iso_time(SCENARIO_START, 8.45),
            "endTime": iso_time(SCENARIO_START, 9.40),
            "durationInNanos": 950_000_000,
            "status.code": 1,
            "status.message": "IAM lookup slow but not on the saturated Redis instance",
            "resource.attributes.service@name": "ais-gold",
            "sample.scenario_id": SCENARIO_ID,
            "sample.scenario_fault_type": FAULT_TYPE,
            "sample.noise_type": "competing_candidate",
        },
        {
            "traceId": SECONDARY_TRACE_ID,
            "spanId": "advredis0014",
            "parentSpanId": "advredis0013",
            "kind": "SPAN_KIND_CLIENT",
            "serviceName": "iam-manage",
            "name": "Jedis/get",
            "startTime": iso_time(SCENARIO_START, 8.50),
            "endTime": iso_time(SCENARIO_START, 8.58),
            "durationInNanos": 80_000_000,
            "status.code": 0,
            "status.message": "",
            "span.attributes.db@type": "Redis",
            "span.attributes.db@instance": "10.252.199.188:6379",
            "resource.attributes.service@name": "iam-manage",
            "sample.scenario_id": SCENARIO_ID,
            "sample.scenario_fault_type": FAULT_TYPE,
            "sample.noise_type": "merely_observed_different_redis",
        },
        {
            "traceId": SECONDARY_TRACE_ID,
            "spanId": "advredis0015",
            "parentSpanId": "advredis0008",
            "kind": "SPAN_KIND_CLIENT",
            "serviceName": "ais-configure",
            "name": "GET:/mmj/config/feature-flags",
            "startTime": iso_time(SCENARIO_START, 8.55),
            "endTime": iso_time(SCENARIO_START, 8.67),
            "durationInNanos": 120_000_000,
            "status.code": 0,
            "status.message": "",
            "resource.attributes.service@name": "ais-configure",
            "sample.scenario_id": SCENARIO_ID,
            "sample.scenario_fault_type": FAULT_TYPE,
            "sample.noise_type": "merely_observed",
        },
    ]


def log_records() -> list[dict[str, Any]]:
    severity_map = {"DEBUG": 5, "INFO": 9, "WARN": 13, "ERROR": 17}

    def rec(
        service: str,
        severity: str,
        body: str,
        offset_secs: float,
        trace_id: str,
        noise_type: str | None = None,
        injected_fault: bool = False,
    ) -> dict[str, Any]:
        return {
            "traceId": trace_id,
            "spanId": "",
            "severityText": severity,
            "severityNumber": severity_map[severity],
            "time": iso_time(SCENARIO_START, offset_secs),
            "observedTimestamp": iso_time(SCENARIO_START, offset_secs + 0.05),
            "serviceName": service,
            "body": body,
            "resource.attributes.service@name": service,
            "log.attributes.trace_id": trace_id,
            "log.attributes.severity_text": severity,
            "sample.scenario_id": SCENARIO_ID,
            "sample.injected_fault": injected_fault,
            **({"sample.noise_type": noise_type} if noise_type else {}),
        }

    return [
        rec("csc-cm-it", "WARN", "UserInfoValidate thread pool queue reached 280; downstream validation context unresolved.", 18.0, PRIMARY_TRACE_ID, "competing_candidate"),
        rec("csc-cm-it", "ERROR", "UserInfoValidate partial failure after waiting on shared validation context.", 31.0, PRIMARY_TRACE_ID, "competing_candidate"),
        rec("ais-configure", "WARN", "updateLastAccessDate retry budget nearly exhausted while waiting for authn/prelogin.", 28.0, SECONDARY_TRACE_ID, "competing_candidate"),
        rec("ais-configure", "ERROR", "updateLastAccessDate degraded due to upstream dependency timeout and queue pressure.", 44.0, SECONDARY_TRACE_ID, "competing_candidate"),
        rec("ais-application-service", "WARN", "Config fan-out latency exceeded 2300ms; suspect downstream cache pressure.", 24.0, PRIMARY_TRACE_ID, "cascaded_slow_misleading"),
        rec("ais-gold", "WARN", "Promotion rule lookup slowed by nearby IAM dependency but retried successfully.", 37.0, SECONDARY_TRACE_ID, "competing_candidate"),
        rec("ais-amc", "WARN", "Shared order/coupon state lookup latency exceeded threshold before Redis rejection surfaced.", 26.0, PRIMARY_TRACE_ID, "shared_dependency_symptom"),
        rec("ais-amc", "ERROR", "Redis connection pool exhausted while executing shared EVAL command for validation context.", 33.0, PRIMARY_TRACE_ID, None, True),
        rec("ais-amc", "ERROR", "Redis connection pool exhausted while executing shared EVAL command for account update decision.", 46.0, SECONDARY_TRACE_ID, None, True),
        rec("iam-manage", "INFO", "User detail Redis read completed on independent cache instance without queueing.", 39.0, SECONDARY_TRACE_ID, "merely_observed"),
        rec("ais-mmj-service", "INFO", "Feature-flag read completed normally; no backlog on mmj path.", 42.0, SECONDARY_TRACE_ID, "merely_observed"),
        rec("ais-pmc", "INFO", "Policy cache reload completed in normal range during order-submit degradation.", 22.0, PRIMARY_TRACE_ID, "merely_observed"),
    ]


def metric_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    start = "2026-06-03T01:02:45.556Z"
    fault_window = [False, False, False, True, True, True, True, True, False]

    def add_series(
        name: str,
        service: str,
        values: list[float],
        flags: list[bool],
        noise_type: str = "companion_metric",
    ) -> None:
        for i, (value, injected) in enumerate(zip(values, flags)):
            records.append(
                {
                    "unit": "",
                    "exemplars": [],
                    "kind": "GAUGE",
                    "name": name,
                    "flags": 0,
                    "description": "Advanced shared Redis contention companion metric",
                    "startTime": iso_time(start),
                    "time": iso_time(start, i * 60),
                    "serviceName": service,
                    "value": value,
                    "resource.attributes.service@name": service,
                    "sample.scenario_id": SCENARIO_ID,
                    "sample.injected_fault": injected,
                    "sample.noise_type": noise_type,
                }
            )

    add_series("service_request_latency_ms", "csc-cm-it", [180, 190, 205, 780, 2200, 2550, 2430, 980, 210], fault_window)
    add_series("service_error_rate", "csc-cm-it", [0.01, 0.02, 0.02, 0.08, 0.31, 0.37, 0.34, 0.12, 0.02], fault_window)
    add_series("thread_pool_blocked_threads", "csc-cm-it", [3, 4, 5, 18, 52, 61, 57, 21, 5], fault_window)

    add_series("service_request_latency_ms", "ais-configure", [170, 180, 175, 690, 2050, 2380, 2260, 910, 205], fault_window)
    add_series("service_error_rate", "ais-configure", [0.01, 0.01, 0.02, 0.05, 0.22, 0.29, 0.25, 0.10, 0.02], fault_window)
    add_series("thread_pool_blocked_threads", "ais-configure", [2, 3, 3, 14, 41, 49, 46, 18, 4], fault_window)

    add_series("service_request_latency_ms", "ais-amc", [210, 225, 230, 840, 2650, 3040, 2970, 1180, 240], fault_window)
    add_series("service_error_rate", "ais-amc", [0.02, 0.02, 0.03, 0.12, 0.43, 0.49, 0.47, 0.18, 0.03], fault_window)

    add_series("service_request_latency_ms", "ais-application-service", [160, 170, 165, 520, 1480, 1720, 1680, 640, 190], fault_window)
    add_series("service_request_latency_ms", "ais-gold", [140, 145, 150, 420, 1120, 1310, 1250, 520, 165], fault_window)

    add_series(
        "redis_commands_duration_seconds_total",
        "ais-amc",
        [0.18, 0.20, 0.21, 0.85, 2.40, 2.95, 2.78, 1.05, 0.22],
        fault_window,
        "redis_confirmation_metric",
    )
    add_series(
        "redis_commands_rejected_calls_total",
        "ais-amc",
        [0, 0, 0, 3, 19, 31, 27, 7, 0],
        fault_window,
        "redis_confirmation_metric",
    )

    add_series("service_request_latency_ms", "ais-pmc", [96, 95, 98, 99, 97, 98, 97, 95, 96], [False] * 9, "merely_observed_metric")
    add_series("service_request_latency_ms", "ais-mmj-service", [102, 101, 103, 104, 102, 103, 102, 101, 102], [False] * 9, "merely_observed_metric")
    add_series("service_request_latency_ms", "iam-manage", [130, 128, 129, 150, 165, 158, 152, 136, 131], [False] * 9, "different_cache_noise_metric")

    return records


def append_entities() -> None:
    path = ADVANCED_OUTPUT / "sample-data" / "entities.json"
    data = read_json(path)
    incident = incident_entity()
    if not any(item.get("__entity_id__") == incident["__entity_id__"] for item in data):
        data.append(incident)
    write_json(path, data)


def append_relations() -> None:
    path = ADVANCED_OUTPUT / "sample-data" / "relations.json"
    data = read_json(path)
    incident_id = stable_id(SCENARIO_ID)
    new_records = [
        relation_record("platform.incident", incident_id, "platform.service", SERVICE_IDS["csc-cm-it"], "impacts", f"{SCENARIO_ID} impacts csc-cm-it", SCENARIO_START),
        relation_record("platform.incident", incident_id, "platform.service", SERVICE_IDS["ais-configure"], "impacts", f"{SCENARIO_ID} impacts ais-configure", SCENARIO_START),
        relation_record("platform.incident", incident_id, "platform.service", SERVICE_IDS["ais-amc"], "impacts", f"{SCENARIO_ID} impacts ais-amc", SCENARIO_START),
        relation_record("platform.incident", incident_id, "platform.service", SERVICE_IDS["ais-application-service"], "impacts", f"{SCENARIO_ID} impacts ais-application-service", SCENARIO_START),
        relation_record("platform.incident", incident_id, "platform.redis", REDIS_ENTITY_ID, "caused_by", f"{SCENARIO_ID} caused by redis {REDIS_INSTANCE}", SCENARIO_START),
    ]
    existing = {(r.get("__src_entity_id__"), r.get("__relation_type__"), r.get("__dest_entity_id__")) for r in data}
    for record in new_records:
        key = (record["__src_entity_id__"], record["__relation_type__"], record["__dest_entity_id__"])
        if key not in existing:
            data.append(record)
    write_json(path, data)


def append_evidence() -> None:
    traces_path = ADVANCED_OUTPUT / "evidence" / "traces.json"
    logs_path = ADVANCED_OUTPUT / "evidence" / "logs.json"
    metrics_path = ADVANCED_OUTPUT / "evidence" / "metrics.json"

    traces = read_json(traces_path)
    logs = read_json(logs_path)
    metrics = read_json(metrics_path)

    trace_ids = {item.get("spanId") for item in traces}
    for span in trace_spans():
        if span["spanId"] not in trace_ids:
            traces.append(span)

    log_keys = {(item.get("time"), item.get("serviceName"), item.get("body")) for item in logs}
    for record in log_records():
        key = (record["time"], record["serviceName"], record["body"])
        if key not in log_keys:
            logs.append(record)

    metric_keys = {(item.get("time"), item.get("serviceName"), item.get("name")) for item in metrics}
    for record in metric_records():
        key = (record["time"], record["serviceName"], record["name"])
        if key not in metric_keys:
            metrics.append(record)

    write_json(traces_path, traces)
    write_json(logs_path, logs)
    write_json(metrics_path, metrics)


def append_scenarios() -> None:
    index_path = ADVANCED_OUTPUT / "scenarios" / "index.json"
    demo_path = ADVANCED_OUTPUT / "scenarios" / "advanced-demo-scenarios.json"
    scenario_path = ADVANCED_OUTPUT / "scenarios" / f"{SCENARIO_ID}.json"

    index_data = read_json(index_path)
    payload = scenario_payload()
    index_data = [item for item in index_data if item.get("scenario_id") != SCENARIO_ID]
    index_data.append(payload)
    write_json(index_path, index_data)
    write_json(scenario_path, payload)
    write_json(demo_path, [payload])


def write_readme() -> None:
    readme = f"""# MModel Advanced Fault Samples

This pack extends `outputs/mmodel-fault-samples` with one harder object-centered scenario:

- `{SCENARIO_ID}`: shared Redis contention across two real-style 4A entry flows

Why this scenario exists:

- Two user-facing APIs degrade in the same time window.
- Several services look suspicious from trace, log, and metric views.
- A nearby IAM Redis read on a different instance creates an additional false candidate.
- The intended demonstration is that object-centered convergence should prefer the shared Redis entity `{REDIS_INSTANCE}` over the noisiest entry service.

Files:

- `sample-data/entities.json`: base entities plus one new incident entity
- `sample-data/relations.json`: base relations plus new incident impact / caused_by relations
- `evidence/traces.json`: base traces plus two synthetic multi-entry traces
- `evidence/logs.json`: base logs plus noisy and confirming logs
- `evidence/metrics.json`: base metrics plus shared-contention companion metrics
- `scenarios/{SCENARIO_ID}.json`: scenario metadata and expected diagnosis
- `scenarios/advanced-demo-scenarios.json`: lightweight pointer list for advanced demos

Suggested demo prompt:

`time={SCENARIO_START} api=/csc/services/UserInfoValidate symptom=User validation and account update both become slow with partial failures`
"""
    (ADVANCED_OUTPUT / "README.md").write_text(readme, encoding="utf-8")


def update_manifest() -> None:
    manifest_path = ADVANCED_OUTPUT / "manifest.json"
    manifest = read_json(manifest_path)
    entities = read_json(ADVANCED_OUTPUT / "sample-data" / "entities.json")
    relations = read_json(ADVANCED_OUTPUT / "sample-data" / "relations.json")
    logs = read_json(ADVANCED_OUTPUT / "evidence" / "logs.json")
    metrics = read_json(ADVANCED_OUTPUT / "evidence" / "metrics.json")
    traces = read_json(ADVANCED_OUTPUT / "evidence" / "traces.json")
    scenarios = read_json(ADVANCED_OUTPUT / "scenarios" / "index.json")

    manifest["sample"] = "mmodel-fault-samples-advanced"
    manifest["title"] = "MModel Advanced Fault Samples"
    manifest["description"] = "Advanced controlled fault samples with stronger ambiguity and shared-dependency convergence requirements."
    manifest.setdefault("generation", {})
    manifest["generation"]["script"] = "scripts/generate_advanced_shared_redis_scenario.py"
    manifest["counts"] = {
        "scenarios": len(scenarios),
        "entities": len(entities),
        "relations": len(relations),
        "logs": len(logs),
        "metrics": len(metrics),
        "traces": len(traces),
    }
    manifest.setdefault("files", {})
    manifest["files"]["advanced_demo_scenarios"] = "scenarios/advanced-demo-scenarios.json"
    limitations = manifest.get("limitations", [])
    extra = "Advanced samples intentionally include competing candidates and merely observed nodes to test object-centered convergence."
    if extra not in limitations:
        limitations.append(extra)
    manifest["limitations"] = limitations
    write_json(manifest_path, manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate advanced shared Redis fault samples")
    parser.parse_args()

    copy_base_pack()
    append_entities()
    append_relations()
    append_evidence()
    append_scenarios()
    write_readme()
    update_manifest()
    print(f"Generated advanced sample pack at: {ADVANCED_OUTPUT}")


if __name__ == "__main__":
    main()
