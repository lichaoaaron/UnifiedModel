#!/usr/bin/env python
"""
Harden database lock-wait scenario (fault-database-lock-wait-001) with realistic noise.

Scope
-----
Only updates outputs/mmodel-fault-samples evidence and scenario metadata for
fault-database-lock-wait-001. Does not touch UnifiedModel/data, Redis scenarios,
or protocol/orchestrator logic.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "outputs" / "mmodel-fault-samples" / "evidence"
SCENARIOS_DIR = ROOT / "outputs" / "mmodel-fault-samples" / "scenarios"

SCENARIO_ID = "fault-database-lock-wait-001"
TRACE_ID = "879cb583129ec5cabc0cc90495498ec8"

ROOT_SPAN = "78df83b9a28d7137"  # csc-cm-it root span
BALANCER_OPEN_APP = "73df83b9a28d7137"
BALANCER_USER_DETAIL = "6cdf83b9a28d7137"

START_ISO = "2026-06-03T01:01:45.658Z"


def _iso(ts_str: str, delta_secs: float = 0.0) -> str:
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    dt += timedelta(seconds=delta_secs)
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _noise_trace_spans() -> list[dict]:
    return [
        {
            "traceId": TRACE_ID,
            "spanId": "db01aa02bb03cc04",
            "parentSpanId": ROOT_SPAN,
            "kind": "SPAN_KIND_CLIENT",
            "serviceName": "ais-configure",
            "name": "POST:/ais/configure/web/runtime/configRefresh",
            "startTime": _iso(START_ISO, 0.2),
            "endTime": _iso(START_ISO, 3.2),
            "durationInNanos": 3_000_000_000,
            "status.code": 1,
            "status.message": "Runtime config refresh delayed by downstream dependency",
            "traceGroupFields": {"endTime": _iso(START_ISO, 3.2)},
            "traceGroup": "POST:/ais/configure/web/runtime/configRefresh",
            "droppedLinksCount": 0,
            "droppedEventsCount": 0,
            "droppedAttributesCount": 0,
            "traceState": "",
            "links": [],
            "events": [],
            "resource.attributes.service@name": "ais-configure",
            "sample.scenario_fault_type": "database_lock_wait",
            "sample.noise_type": "cascaded_slow_misleading",
        },
        {
            "traceId": TRACE_ID,
            "spanId": "db02aa03bb04cc05",
            "parentSpanId": BALANCER_OPEN_APP,
            "kind": "SPAN_KIND_SERVER",
            "serviceName": "ais-amc",
            "name": "POST:/amc/open/token/validate",
            "startTime": _iso(START_ISO, 0.35),
            "endTime": _iso(START_ISO, 2.95),
            "durationInNanos": 2_600_000_000,
            "status.code": 1,
            "status.message": "Token validation delayed; waiting for repository response",
            "traceGroupFields": {"endTime": _iso(START_ISO, 2.95)},
            "traceGroup": "POST:/amc/open/token/validate",
            "droppedLinksCount": 0,
            "droppedEventsCount": 0,
            "droppedAttributesCount": 0,
            "traceState": "",
            "links": [],
            "events": [],
            "resource.attributes.service@name": "ais-amc",
            "sample.scenario_fault_type": "database_lock_wait",
            "sample.noise_type": "cascaded_slow_misleading",
        },
        {
            "traceId": TRACE_ID,
            "spanId": "db03aa04bb05cc06",
            "parentSpanId": "db02aa03bb04cc05",
            "kind": "SPAN_KIND_CLIENT",
            "serviceName": "ais-amc",
            "name": "HikariCP/Connection/getConnection",
            "startTime": _iso(START_ISO, 0.5),
            "endTime": _iso(START_ISO, 2.4),
            "durationInNanos": 1_900_000_000,
            "status.code": 1,
            "status.message": "Connection pool acquisition waited beyond threshold",
            "traceGroupFields": {"endTime": _iso(START_ISO, 2.4)},
            "traceGroup": "HikariCP/Connection/getConnection",
            "droppedLinksCount": 0,
            "droppedEventsCount": 0,
            "droppedAttributesCount": 0,
            "traceState": "",
            "links": [],
            "events": [],
            "resource.attributes.service@name": "ais-amc",
            "sample.scenario_fault_type": "database_lock_wait",
            "sample.noise_type": "pool_contention_candidate",
        },
        {
            "traceId": TRACE_ID,
            "spanId": "db04aa05bb06cc07",
            "parentSpanId": BALANCER_USER_DETAIL,
            "kind": "SPAN_KIND_SERVER",
            "serviceName": "iam-manage",
            "name": "POST:/imc/user/open/detail",
            "startTime": _iso(START_ISO, 0.22),
            "endTime": _iso(START_ISO, 0.34),
            "durationInNanos": 120_000_000,
            "status.code": 0,
            "status.message": "",
            "traceGroupFields": {"endTime": _iso(START_ISO, 0.34)},
            "traceGroup": "POST:/imc/user/open/detail",
            "droppedLinksCount": 0,
            "droppedEventsCount": 0,
            "droppedAttributesCount": 0,
            "traceState": "",
            "links": [],
            "events": [],
            "resource.attributes.service@name": "iam-manage",
            "sample.scenario_fault_type": "database_lock_wait",
            "sample.noise_type": "merely_observed",
        },
        {
            "traceId": TRACE_ID,
            "spanId": "db05aa06bb07cc08",
            "parentSpanId": ROOT_SPAN,
            "kind": "SPAN_KIND_SERVER",
            "serviceName": "ais-pmc",
            "name": "GET:/pmc/policy/cache/reload",
            "startTime": _iso(START_ISO, 0.28),
            "endTime": _iso(START_ISO, 0.43),
            "durationInNanos": 150_000_000,
            "status.code": 0,
            "status.message": "",
            "traceGroupFields": {"endTime": _iso(START_ISO, 0.43)},
            "traceGroup": "GET:/pmc/policy/cache/reload",
            "droppedLinksCount": 0,
            "droppedEventsCount": 0,
            "droppedAttributesCount": 0,
            "traceState": "",
            "links": [],
            "events": [],
            "resource.attributes.service@name": "ais-pmc",
            "sample.scenario_fault_type": "database_lock_wait",
            "sample.noise_type": "merely_observed",
        },
    ]


def _noise_log_records() -> list[dict]:
    sev = {"DEBUG": 5, "INFO": 9, "WARN": 13, "ERROR": 17}

    def rec(service: str, level: str, body: str, offset: float, noise_type: str) -> dict:
        return {
            "traceId": TRACE_ID,
            "spanId": "",
            "severityText": level,
            "severityNumber": sev[level],
            "time": _iso(START_ISO, offset),
            "observedTimestamp": _iso(START_ISO, offset + 0.05),
            "serviceName": service,
            "body": body,
            "resource.attributes.service@name": service,
            "log.attributes.trace_id": TRACE_ID,
            "log.attributes.severity_text": level,
            "sample.scenario_id": SCENARIO_ID,
            "sample.injected_fault": False,
            "sample.noise_type": noise_type,
        }

    return [
        rec("ais-amc", "WARN", "Connection pool wait exceeded 1600ms; active=78 idle=2 pending=11.", 20.0, "competing_candidate"),
        rec("ais-amc", "ERROR", "Repository transaction blocked waiting for lock owner session; fallback path triggered.", 36.0, "competing_candidate"),
        rec("ais-amc", "WARN", "Thread executor queue length reached 320; request timeout risk increased.", 52.0, "competing_candidate"),
        rec("ais-configure", "WARN", "Retrying DAO operation after timeout: select config profile by tenant.", 28.0, "competing_candidate"),
        rec("ais-configure", "ERROR", "Service response degraded: upstream token validation exceeded SLA after retries.", 48.0, "competing_candidate"),
        rec("ais-configure", "INFO", "Transaction interceptor switching to READ_COMMITTED for retry workflow.", 61.0, "cascaded_info"),
        rec("csc-cm-it", "WARN", "SQL execution latency elevated; lock owner not released yet for target row set.", 40.0, "db_confirmation_soft"),
        rec("csc-cm-it", "DEBUG", "PreparedStatement executeWithFlags retry attempt 2 for same SQL template.", 58.0, "db_confirmation_soft"),
        rec("ais-pmc", "INFO", "Policy cache warm-up completed in 120ms; no backlog detected.", 18.0, "merely_observed"),
        rec("iam-manage", "INFO", "User detail query completed in normal range; no lock contention seen in this path.", 24.0, "merely_observed"),
    ]


def _noise_metric_records() -> list[dict]:
    records: list[dict] = []
    start = "2026-06-03T00:58:45.658Z"

    def add_series(name: str, service: str, values: list[float], flags: list[bool], noise_type: str = "companion_metric") -> None:
        for i, (v, f) in enumerate(zip(values, flags)):
            records.append(
                {
                    "unit": "",
                    "exemplars": [],
                    "kind": "GAUGE",
                    "name": name,
                    "flags": 0,
                    "description": "Database hardening companion metric",
                    "startTime": _iso(start),
                    "time": _iso(start, i * 60),
                    "serviceName": service,
                    "value": v,
                    "resource.attributes.service@name": service,
                    "sample.scenario_id": SCENARIO_ID,
                    "sample.injected_fault": f,
                    "sample.noise_type": noise_type,
                }
            )

    fault_win = [False, False, False, True, True, True, True, True, False]

    add_series("service_request_latency_ms", "ais-amc", [220, 230, 215, 920, 2600, 3100, 2850, 1050, 260], fault_win)
    add_series("service_error_rate", "ais-amc", [0.02, 0.03, 0.02, 0.10, 0.34, 0.41, 0.39, 0.15, 0.03], fault_win)
    add_series("connection_pool_wait_ms", "ais-amc", [8, 10, 9, 35, 120, 165, 140, 45, 11], fault_win)

    add_series("service_request_latency_ms", "ais-configure", [180, 190, 185, 620, 1450, 1720, 1600, 700, 210], fault_win)
    add_series("thread_pool_blocked_threads", "ais-configure", [4, 5, 4, 18, 45, 52, 49, 20, 6], fault_win)

    add_series("service_request_latency_ms", "ais-pmc", [96, 95, 97, 98, 96, 99, 97, 95, 96], [False] * 9, "merely_observed_metric")

    return records


def _harden_traces(path: Path, dry_run: bool) -> int:
    data: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    existing = {x.get("spanId") for x in data}
    new_spans = [s for s in _noise_trace_spans() if s["spanId"] not in existing]
    if not new_spans:
        print("[traces] Already hardened, no new spans to add.")
        return 0
    print(f"[traces] add {len(new_spans)} spans")
    if not dry_run:
        data.extend(new_spans)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(new_spans)


def _harden_logs(path: Path, dry_run: bool) -> int:
    data: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    exists = [x for x in data if x.get("sample.scenario_id") == SCENARIO_ID and x.get("sample.noise_type")]
    if exists:
        print(f"[logs] Already hardened ({len(exists)} noise logs found).")
        return 0
    new_logs = _noise_log_records()
    print(f"[logs] add {len(new_logs)} logs")
    if not dry_run:
        data.extend(new_logs)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(new_logs)


def _harden_metrics(path: Path, dry_run: bool) -> int:
    data: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    exists = [x for x in data if x.get("sample.scenario_id") == SCENARIO_ID and x.get("sample.noise_type")]
    if exists:
        print(f"[metrics] Already hardened ({len(exists)} noise metrics found).")
        return 0
    new_metrics = _noise_metric_records()
    print(f"[metrics] add {len(new_metrics)} metric points")
    if not dry_run:
        data.extend(new_metrics)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(new_metrics)


def _harden_scenario(path: Path, dry_run: bool) -> None:
    obj: dict = json.loads(path.read_text(encoding="utf-8"))
    if obj.get("hardening", {}).get("database_noise_v1"):
        print("[scenario] Already patched.")
        return

    obj["merely_observed_nodes"] = [
        {
            "service": "ais-pmc",
            "reason": "Appears in trace but no lock-wait evidence and stable latency in same window.",
            "node_type": "merely_observed_node",
        },
        {
            "service": "iam-manage",
            "reason": "Participates in nearby calls but has normal logs/latency and no lock-wait indicators.",
            "node_type": "merely_observed_node",
        },
    ]
    obj["noise_nodes"] = [
        {
            "service": "ais-amc",
            "reason": "Shows high RT, pool wait and thread pressure that can be mistaken as root cause without object-model context.",
            "node_type": "competing_candidate",
        },
        {
            "service": "ais-configure",
            "reason": "Shows retries and blocked threads as propagated effect rather than primary DB lock source.",
            "node_type": "competing_candidate",
        },
    ]
    obj["hardening"] = {
        "database_noise_v1": True,
        "intent": "Increase false candidates at app/pool/dao layers while preserving database lock-wait as stable root-cause entity.",
    }

    print("[scenario] patch merely_observed_nodes/noise_nodes/hardening")
    if not dry_run:
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Harden Database scenario evidence")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    t = _harden_traces(EVIDENCE_DIR / "traces.json", args.dry_run)
    l = _harden_logs(EVIDENCE_DIR / "logs.json", args.dry_run)
    m = _harden_metrics(EVIDENCE_DIR / "metrics.json", args.dry_run)
    _harden_scenario(SCENARIOS_DIR / f"{SCENARIO_ID}.json", args.dry_run)

    print(f"Done: +{t} spans, +{l} logs, +{m} metrics")
    if args.dry_run:
        print("Dry-run only, no files written.")


if __name__ == "__main__":
    main()
