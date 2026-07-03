import re
from typing import Any


TYPE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("dependency_unavailable", (" code = unavailable ", "service unavailable", "connection refused", "failed to connect", "deadline exceeded", "name resolver error", "zero addresses")),
    ("network_packet_loss_latency", ("packet loss", "tcp retransmit", "tcp.retransmits", "network delay", "sockettimeoutexception")),
    ("nginx_upstream_timeout", ("upstream timed out", "nginx.http.status.504", "nginxupstreamtimeout")),
    ("nginx_connection_exhaustion", ("worker connections", "nginx.connections.active", "nginxworkerconnectionexhausted")),
    ("mysql_max_connections", ("too many connections", "mysql.connections.current", "max connections")),
    ("mysql_table_lock", ("metadata lock", "mysql.threads.waiting_for_table_lock", "waiting for table")),
    ("mysql_row_lock", ("row lock", "lock wait timeout", "mysql.innodb.row_lock_waits")),
    ("mysql_slow_query", ("mysql slow query", "select sleep", "mysql.query.duration", "querytimeoutexception")),
    ("redis_lock_stuck", ("distributed lock", "lockacquisitionexception", "redis.lock.wait.timeout")),
    ("redis_bigkey_blocking", ("big key", "bigkey", "redis.network.egress", "readtimedout", "read time out")),
    ("redis_keys_command", (" keys ", "redis cpu", "redis.cpu.usage", "keys command")),
    ("redis_slow_lua", ("slow lua", "lua script", "redis.command.latency", "rediscommandtimeoutexception")),
    ("redis_node_down", ("redis node down", "unable to connect to redis", "redisconnectionfailureexception", "redis.client.connection.errors")),
    ("connection_pool_exhaustion", ("connection pool exhausted", "pool exhausted", "db.pool.active.connections", "poolexhaustedexception")),
    ("thread_pool_exhaustion", ("thread pool", "rejectedexecutionexception", "executor.queue.size")),
    ("frequent_full_gc", ("full gc", "jvm.gc.full_gc")),
    ("memory_leak", ("memory leak", "java heap space", "outofmemoryerror", "jvm.memory.heap.used")),
    ("high_cpu", ("high cpu", "cpu intensive", "container.cpu.usage.percent")),
    ("error_loop", ("error loop", "frequent runtime", "http.server.errors.5xx")),
    ("slow_interface", ("slow interface", "slowrequest", "latency anomaly", "latency budget", "http.server.duration")),
]

EXCEPTION_RE = re.compile(
    r"([A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*(?:Exception|Error|Timeout|Exhausted|SlowRequest|PacketLoss)[A-Za-z0-9_$]*)"
)


def classify_root_cause_type(text: str, metric_name: str = "") -> str:
    haystack = f" {text} {metric_name} ".lower()
    for root_type, needles in TYPE_RULES:
        if any(needle in haystack for needle in needles):
            return root_type
    return "service_exception"


def extract_exception_type(text: str) -> str | None:
    match = EXCEPTION_RE.search(text or "")
    return match.group(1) if match else None


def is_propagation_text(text: str, service: str = "") -> bool:
    lower = (text or "").lower()
    svc = (service or "").lower()
    return (
        "propagated symptom" in lower
        or "observed symptom" in lower
        or "feignexception" in lower
        or "nestedservletexception" in lower
        or svc in {"api-gateway", "gateway"}
    )


def normalize_api(name: str) -> str:
    if not name:
        return ""
    if ":" in name and name.split(":", 1)[0] in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
        return name.split(":", 1)[1]
    return name


def normalize_service_name(name: str) -> str:
    token = (name or "").strip()
    if not token:
        return ""
    token = token.split(".")[-1]
    if token.endswith("Service") and len(token) > len("Service"):
        token = token[:-len("Service")]
    if not token:
        return ""
    token = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", token)
    token = token.replace("_", "-")
    return token.lower()


def extract_rpc_target_service(*values: str) -> str:
    for value in values:
        token = (value or "").strip()
        if not token:
            continue
        if "/" in token:
            token = token.split("/", 1)[0]
        elif not token.endswith("Service") and ".Service" not in token:
            continue
        normalized = normalize_service_name(token)
        if normalized:
            return normalized
    return ""


def metric_threshold(metric_name: str) -> float | None:
    thresholds = {
        "container.cpu.usage.percent": 95,
        "jvm.memory.heap.used.percent": 95,
        "jvm.gc.full_gc.duration.p99": 1000,
        "executor.queue.size": 500,
        "db.pool.active.connections": 45,
        "http.server.errors.5xx.rate": 5,
        "http.server.duration.p95": 1000,
        "http.server.duration.p99": 3000,
        "http.client.errors.rate": 5,
        "redis.client.connection.errors": 10,
        "redis.command.latency.p99": 1000,
        "redis.cpu.usage.percent": 90,
        "redis.lock.wait.timeout.count": 10,
        "redis.network.egress.bytes_per_second": 50000000,
        "mysql.query.duration.p99": 3000,
        "mysql.innodb.row_lock_waits": 100,
        "mysql.threads.waiting_for_table_lock": 10,
        "mysql.connections.current": 400,
        "nginx.connections.active": 3000,
        "nginx.http.status.504.rate": 5,
        "node.network.tcp.retransmits": 100,
    }
    return thresholds.get(metric_name)


def value_as_float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def confidence_from_score(score: float) -> str:
    if score >= 0.78:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"