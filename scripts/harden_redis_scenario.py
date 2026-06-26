#!/usr/bin/env python
"""
Harden Redis saturation scenario (fault-redis-saturation-001) with realistic noise.

What this script does
---------------------
- Adds competing "misleading slow" trace spans so that the injected Redis ERR span
  is no longer the trivially obvious single error in the trace.
- Adds application-side warning/error logs on non-Redis services to simulate
  cascaded symptoms that could look like root causes without object-model context.
- Adds companion service-level metrics so that ais-configure and ais-gold appear
  to be candidates at the metric layer too.
- Adds a merely-observed ais-mmj-service span and metrics to test impact-scope
  pruning.
- Patches the scenario JSON with an explicit `merely_observed_nodes` list.

What this script does NOT do
-----------------------------
- Does not remove the real Redis ERR span or the Redis error logs.
- Does not change case_id, symptom, api, scenario metadata primary identifiers.
- Does not touch any other scenario in the evidence files.
- Does not touch C:/Users/chaoJ/Desktop/UnifiedModel/data.

Usage
-----
    python scripts/harden_redis_scenario.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "outputs" / "mmodel-fault-samples" / "evidence"
SCENARIOS_DIR = ROOT / "outputs" / "mmodel-fault-samples" / "scenarios"

SCENARIO_ID = "fault-redis-saturation-001"
TRACE_ID = "b4718bd204144788216a9e8eef57e289"

# Parent span from ais-configure (the entry to the whole trace)
CONFIGURE_ROOT_SPAN = "5aa29781280567aa"
# Parent span of ais-amc (the service that calls Redis)
AMC_PARENT_SPAN = "58a29781280567aa"
# The real injected Redis ERR span
REDIS_ERR_SPAN = "3883052abcab8d36"

START_ISO = "2026-06-03T01:00:04.895Z"


def _iso(ts_str: str, delta_secs: float = 0.0) -> str:
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    dt += timedelta(seconds=delta_secs)
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _noise_trace_spans() -> list[dict]:
    """
    Returns 5 noise/misleading spans to add to the Redis scenario trace.

    Design intent
    -------------
    span_1  ais-configure  WARN (code=1) 2600ms client call
        Misleading: ais-configure is the entry service and appears to have a
        slow config-sync call with WARN status. Without object context, this
        looks like ais-configure might be the bottleneck.

    span_2  ais-configure  WARN (code=1) 1900ms client call to ais-amc login
        Misleading: another slow call from ais-configure into ais-amc, making
        ais-configure look like a cascaded failure source.

    span_3  ais-application-service  WARN (code=1) 1700ms
        Misleading: ais-application-service also shows a slow call with WARN,
        increasing the number of "suspicious" services visible in the trace.

    span_4  ais-mmj-service  OK 110ms (server span)
        Merely observed: ais-mmj-service gets a request from ais-configure but
        responds normally. Should NOT be in the core impact scope.

    span_5  iam-manage  OK 85ms Redis read
        Merely observed: iam-manage performs a normal Redis read (Jedis/get),
        not the error instance. Should NOT be counted as impacted by Redis
        saturation.
    """
    return [
        # span_1: slow misleading config-sync on ais-configure
        {
            "traceId": TRACE_ID,
            "spanId": "aa01bb02cc03dd04",
            "parentSpanId": CONFIGURE_ROOT_SPAN,
            "kind": "SPAN_KIND_CLIENT",
            "serviceName": "ais-configure",
            "name": "POST:/ais/configure/web/configSyncCheck",
            "startTime": _iso(START_ISO, 0.3),
            "endTime": _iso(START_ISO, 2.9),
            "durationInNanos": 2_600_000_000,
            "status.code": 1,
            "status.message": "Configuration sync degraded: upstream response exceeded threshold",
            "traceGroupFields": {"endTime": _iso(START_ISO, 2.9)},
            "traceGroup": "POST:/ais/configure/web/configSyncCheck",
            "droppedLinksCount": 0,
            "droppedEventsCount": 0,
            "droppedAttributesCount": 0,
            "traceState": "",
            "links": [],
            "events": [],
            "resource.attributes.service@name": "ais-configure",
            "sample.scenario_fault_type": "redis_saturation",
            "sample.noise_type": "cascaded_slow_misleading",
        },
        # span_2: slow ais-configure → ais-amc login call (normal-looking but slow)
        {
            "traceId": TRACE_ID,
            "spanId": "aa02bb03cc04dd05",
            "parentSpanId": CONFIGURE_ROOT_SPAN,
            "kind": "SPAN_KIND_CLIENT",
            "serviceName": "ais-configure",
            "name": "POST:/authn/check/prelogin",
            "startTime": _iso(START_ISO, 0.4),
            "endTime": _iso(START_ISO, 2.3),
            "durationInNanos": 1_900_000_000,
            "status.code": 1,
            "status.message": "Pre-login check timed out waiting on downstream",
            "traceGroupFields": {"endTime": _iso(START_ISO, 2.3)},
            "traceGroup": "POST:/authn/check/prelogin",
            "droppedLinksCount": 0,
            "droppedEventsCount": 0,
            "droppedAttributesCount": 0,
            "traceState": "",
            "links": [],
            "events": [],
            "resource.attributes.service@name": "ais-configure",
            "sample.scenario_fault_type": "redis_saturation",
            "sample.noise_type": "cascaded_slow_misleading",
        },
        # span_3: slow ais-application-service call (cascaded downstream)
        {
            "traceId": TRACE_ID,
            "spanId": "aa03bb04cc05dd06",
            "parentSpanId": "be26ef73e0db32a1",
            "kind": "SPAN_KIND_CLIENT",
            "serviceName": "ais-application-service",
            "name": "POST:/open/gold/app/getAppConfig",
            "startTime": _iso(START_ISO, 0.5),
            "endTime": _iso(START_ISO, 2.2),
            "durationInNanos": 1_700_000_000,
            "status.code": 1,
            "status.message": "Connection pool wait: downstream cache not responding",
            "traceGroupFields": {"endTime": _iso(START_ISO, 2.2)},
            "traceGroup": "POST:/open/gold/app/getAppConfig",
            "droppedLinksCount": 0,
            "droppedEventsCount": 0,
            "droppedAttributesCount": 0,
            "traceState": "",
            "links": [],
            "events": [],
            "resource.attributes.service@name": "ais-application-service",
            "sample.scenario_fault_type": "redis_saturation",
            "sample.noise_type": "cascaded_slow_misleading",
        },
        # span_4: ais-mmj-service normal response (merely observed)
        {
            "traceId": TRACE_ID,
            "spanId": "aa04bb05cc06dd07",
            "parentSpanId": CONFIGURE_ROOT_SPAN,
            "kind": "SPAN_KIND_SERVER",
            "serviceName": "ais-mmj-service",
            "name": "GET:/mmj/config/feature-flags",
            "startTime": _iso(START_ISO, 0.2),
            "endTime": _iso(START_ISO, 0.31),
            "durationInNanos": 110_000_000,
            "status.code": 0,
            "status.message": "",
            "traceGroupFields": {"endTime": _iso(START_ISO, 0.31)},
            "traceGroup": "GET:/mmj/config/feature-flags",
            "droppedLinksCount": 0,
            "droppedEventsCount": 0,
            "droppedAttributesCount": 0,
            "traceState": "",
            "links": [],
            "events": [],
            "resource.attributes.service@name": "ais-mmj-service",
            "sample.scenario_fault_type": "redis_saturation",
            "sample.noise_type": "merely_observed",
        },
        # span_5: iam-manage normal Redis read (merely observed — not the error instance)
        {
            "traceId": TRACE_ID,
            "spanId": "aa05bb06cc07dd08",
            "parentSpanId": "bb485d06143f2200",
            "kind": "SPAN_KIND_CLIENT",
            "serviceName": "iam-manage",
            "name": "Jedis/get",
            "startTime": _iso(START_ISO, 0.15),
            "endTime": _iso(START_ISO, 0.235),
            "durationInNanos": 85_000_000,
            "status.code": 0,
            "status.message": "",
            "span.attributes.db@type": "Redis",
            "span.attributes.db@instance": "10.252.199.188:6379",
            "traceGroupFields": {"endTime": _iso(START_ISO, 0.235)},
            "traceGroup": "Jedis/get",
            "droppedLinksCount": 0,
            "droppedEventsCount": 0,
            "droppedAttributesCount": 0,
            "traceState": "",
            "links": [],
            "events": [],
            "resource.attributes.service@name": "iam-manage",
            "sample.scenario_fault_type": "redis_saturation",
            "sample.noise_type": "merely_observed_different_redis",
        },
    ]


def _noise_log_records() -> list[dict]:
    """
    Returns 10 noise/misleading log records for the Redis scenario.

    Design intent
    -------------
    - 4 logs on ais-configure: WARN/ERROR about thread pool saturation and
      timeout to downstream. Without object context, these scream "ais-configure
      is the root cause."
    - 2 logs on ais-application-service: WARN about connection pool pressure.
    - 2 logs on ais-gold: INFO/WARN about retry and slow response.
    - 2 logs on ais-mmj-service: INFO level (merely observed, no errors).

    The real Redis JedisConnectionException logs on ais-amc are preserved
    (not removed). They become the confirmation signal when combined with the
    Redis entity/metric context.
    """
    base_trace = TRACE_ID
    start = START_ISO

    def rec(service: str, severity: str, body: str, offset_secs: float, noise_type: str) -> dict:
        sev_map = {"DEBUG": 5, "INFO": 9, "WARN": 13, "WARNING": 13, "ERROR": 17}
        t = _iso(start, offset_secs)
        return {
            "traceId": base_trace,
            "spanId": "",
            "severityText": severity,
            "severityNumber": sev_map.get(severity, 9),
            "time": t,
            "observedTimestamp": _iso(start, offset_secs + 0.05),
            "serviceName": service,
            "body": body,
            "resource.attributes.service@name": service,
            "log.attributes.trace_id": base_trace,
            "log.attributes.severity_text": severity,
            "sample.scenario_id": SCENARIO_ID,
            "sample.injected_fault": False,
            "sample.noise_type": noise_type,
        }

    return [
        # ais-configure: thread pool saturation (misleading root cause candidate)
        rec(
            "ais-configure", "WARN",
            "Thread pool utilization at 89% (89/100 workers active). Accepting new requests may fail under continued load.",
            65.0, "competing_candidate",
        ),
        rec(
            "ais-configure", "WARN",
            "Remote call to ais-amc exceeded soft timeout (2000ms). Retrying (attempt 1/2).",
            80.0, "competing_candidate",
        ),
        rec(
            "ais-configure", "ERROR",
            "Request processing degraded: upstream authn check returned non-200 status after retry exhaustion.",
            100.0, "competing_candidate",
        ),
        rec(
            "ais-configure", "WARN",
            "Connection pool saturation detected on outbound client pool: waiting threads=8, available=2.",
            120.0, "competing_candidate",
        ),
        # ais-application-service: connection pool noise
        rec(
            "ais-application-service", "WARN",
            "Hikari connection pool wait exceeded 1500ms; pool size may be insufficient for current concurrency.",
            70.0, "cascaded_warning",
        ),
        rec(
            "ais-application-service", "WARN",
            "Slow response from downstream cache layer. Request latency P99 currently 2400ms (threshold 500ms).",
            90.0, "cascaded_warning",
        ),
        # ais-gold: retry and slow downstream
        rec(
            "ais-gold", "INFO",
            "Retrying request to ais-application-service (attempt 2/3). Previous attempt timed out at 3000ms.",
            75.0, "cascaded_info",
        ),
        rec(
            "ais-gold", "WARN",
            "Downstream ais-application-service response time elevated: avg 1800ms over last 60s.",
            95.0, "cascaded_warning",
        ),
        # ais-mmj-service: normal healthy logs (merely observed)
        rec(
            "ais-mmj-service", "INFO",
            "Feature flag cache refresh completed. 24 flags updated.",
            30.0, "merely_observed",
        ),
        rec(
            "ais-mmj-service", "INFO",
            "Health check OK. All downstream dependencies responding within SLA.",
            60.0, "merely_observed",
        ),
    ]


def _noise_metric_records() -> list[dict]:
    """
    Returns companion service-level metrics for the Redis scenario.

    Design intent
    -------------
    - ais-configure RT and error rate rise significantly (misleading — these are
      consequences of Redis pressure propagating upstream).
    - ais-gold RT rises moderately (cascaded secondary effect).
    - ais-amc connection_pool_wait rises (corroborates Redis pressure on ais-amc).
    - ais-mmj-service RT stays flat (confirms it is merely observed).

    The three canonical Redis metrics on ais-amc are preserved unchanged.
    These companion metrics raise the noise level so that a simple "find the
    highest spike" heuristic would land on ais-configure, not Redis.
    """
    start = "2026-06-03T00:57:04.895Z"
    records = []

    def pts(name: str, service: str, values: list[float], fault_flags: list[bool]) -> None:
        for i, (v, fault) in enumerate(zip(values, fault_flags)):
            records.append({
                "unit": "",
                "exemplars": [],
                "kind": "GAUGE",
                "name": name,
                "flags": 0,
                "description": "Hardening noise metric for Redis scenario — service-level companion signal",
                "startTime": _iso(start, 0),
                "time": _iso(start, i * 60),
                "serviceName": service,
                "value": v,
                "resource.attributes.service@name": service,
                "sample.scenario_id": SCENARIO_ID,
                "sample.injected_fault": fault,
                "sample.noise_type": "companion_metric",
            })

    # ais-configure: RT spikes hard (looks like root cause at metric layer alone)
    pts("service_request_latency_ms", "ais-configure",
        [210, 230, 220, 850, 2400, 2800, 2600, 900, 240],
        [False, False, False, True, True, True, True, True, False])

    # ais-configure: error rate rises
    pts("service_error_rate", "ais-configure",
        [0.02, 0.02, 0.03, 0.12, 0.38, 0.45, 0.41, 0.14, 0.03],
        [False, False, False, True, True, True, True, True, False])

    # ais-gold: moderate RT rise (secondary effect)
    pts("service_request_latency_ms", "ais-gold",
        [155, 160, 150, 320, 620, 700, 650, 310, 170],
        [False, False, False, True, True, True, True, True, False])

    # ais-amc: connection pool wait rises (corroborates Redis pressure on ais-amc)
    pts("redis_connection_pool_wait_ms", "ais-amc",
        [6, 7, 6, 18, 45, 52, 48, 20, 8],
        [False, False, False, True, True, True, True, True, False])

    # ais-mmj-service: flat (merely observed)
    pts("service_request_latency_ms", "ais-mmj-service",
        [95, 97, 96, 94, 98, 99, 97, 95, 96],
        [False, False, False, False, False, False, False, False, False])

    return records


def harden_traces(path: Path, dry_run: bool) -> int:
    data: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    existing_ids = {s.get("spanId") for s in data}
    noise = [s for s in _noise_trace_spans() if s["spanId"] not in existing_ids]
    if not noise:
        print(f"[traces] Nothing to add (already hardened or all IDs collide).")
        return 0
    print(f"[traces] Adding {len(noise)} noise/misleading spans for {SCENARIO_ID}")
    for s in noise:
        print(f"  + {s['spanId']} {s['serviceName']:<30} {s['durationInNanos']//1_000_000:>6}ms  code={s['status.code']}  noise={s.get('sample.noise_type','')}")
    if not dry_run:
        data.extend(noise)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(noise)


def harden_logs(path: Path, dry_run: bool) -> int:
    data: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    # Check if already hardened
    existing_noise = [r for r in data if r.get("sample.scenario_id") == SCENARIO_ID and r.get("sample.noise_type")]
    if existing_noise:
        print(f"[logs] Already hardened ({len(existing_noise)} noise records found). Skipping.")
        return 0
    noise = _noise_log_records()
    print(f"[logs] Adding {len(noise)} noise logs for {SCENARIO_ID}")
    for r in noise:
        print(f"  + [{r['severityText']:5}] {r['serviceName']:<32} noise={r.get('sample.noise_type','')}  body={r['body'][:60]}...")
    if not dry_run:
        data.extend(noise)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(noise)


def harden_metrics(path: Path, dry_run: bool) -> int:
    data: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    existing_noise = [r for r in data if r.get("sample.scenario_id") == SCENARIO_ID and r.get("sample.noise_type")]
    if existing_noise:
        print(f"[metrics] Already hardened ({len(existing_noise)} noise records found). Skipping.")
        return 0
    noise = _noise_metric_records()
    print(f"[metrics] Adding {len(noise)} companion metric points for {SCENARIO_ID}")
    services = {}
    for r in noise:
        services.setdefault(r["serviceName"], set()).add(r["name"])
    for svc, names in sorted(services.items()):
        print(f"  + {svc}: {sorted(names)}")
    if not dry_run:
        data.extend(noise)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(noise)


def harden_scenario_json(path: Path, dry_run: bool) -> None:
    data: dict = json.loads(path.read_text(encoding="utf-8"))
    if "merely_observed_nodes" in data:
        print(f"[scenario] Already has merely_observed_nodes. Skipping patch.")
        return

    data["merely_observed_nodes"] = [
        {
            "service": "ais-mmj-service",
            "reason": "Called by ais-configure but has no direct Redis dependency and responds normally during the incident window.",
            "node_type": "merely_observed_node",
        },
        {
            "service": "iam-manage",
            "reason": "Appears in trace and calls a different Redis instance (10.252.199.188:6379), not the saturated one. Its own operations complete normally.",
            "node_type": "merely_observed_node",
        },
    ]
    data["noise_nodes"] = [
        {
            "service": "ais-configure",
            "reason": "Entry service shows high RT and WARN/ERROR logs as a consequence of Redis propagation upstream. Without object-topology context, it looks like a root cause candidate.",
            "node_type": "cascaded_slow_misleading",
        },
        {
            "service": "ais-application-service",
            "reason": "Shows elevated RT and pool pressure as a downstream consequence. A naive scan of slow spans would flag this service.",
            "node_type": "cascaded_slow_misleading",
        },
    ]
    data["hardening"] = {
        "applied": True,
        "version": "v1",
        "intent": "High-noise scenario: misleading cascaded slow spans and logs added to require object-centered convergence for correct root-cause identification.",
    }
    print(f"[scenario] Patching {path.name} with merely_observed_nodes, noise_nodes, hardening metadata.")
    if not dry_run:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Harden Redis fault scenario evidence data")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing files")
    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN — no files will be modified ===\n")

    traces_added = harden_traces(EVIDENCE_DIR / "traces.json", args.dry_run)
    logs_added = harden_logs(EVIDENCE_DIR / "logs.json", args.dry_run)
    metrics_added = harden_metrics(EVIDENCE_DIR / "metrics.json", args.dry_run)
    harden_scenario_json(SCENARIOS_DIR / f"{SCENARIO_ID}.json", args.dry_run)

    print(f"\nDone: +{traces_added} spans, +{logs_added} logs, +{metrics_added} metric points")
    if args.dry_run:
        print("No files written (dry-run mode).")
    else:
        print("Evidence files updated.")


if __name__ == "__main__":
    main()
