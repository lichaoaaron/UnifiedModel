"""Quick test of entity-centered RED aggregation against live OpenSearch."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Load .env
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.isfile(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)

from app.adapters.opensearch_adapter import OpenSearchAdapter

adapter = OpenSearchAdapter()
print("Querying entity RED metrics via OpenSearch aggregations...")
result = adapter.query_entity_red_metrics()

print(f"\nTotal entities: {result.get('total_entities')}")
print(f"Total error spans (global): {result.get('total_error_span_count')}")
print(f"Warnings: {result.get('warnings')}")

items = result.get("items", [])
items.sort(key=lambda x: x["anomaly_score"], reverse=True)

print(f"\n{'Rank':<5} {'Service':<25} {'Requests':>10} {'Errors':>8} {'Err%':>8} {'P95(ms)':>10} {'Score':>8}")
print("-" * 80)
for rank, item in enumerate(items[:15], 1):
    svc = item["service_name"][:24]
    req = item["request_count"]
    err = item["error_count"]
    rate = f"{item['error_rate']:.4f}"
    p95 = f"{item['p95_latency_ms']:.1f}"
    score = f"{item['anomaly_score']:.4f}"
    print(f"{rank:<5} {svc:<25} {req:>10} {err:>8} {rate:>8} {p95:>10} {score:>8}")

# Highlight real anomalies
print("\n--- Services with significant error rates ---")
significant = [i for i in items if i["error_rate"] >= 0.01]
if significant:
    for item in significant:
        print(f"  {item['service_name']}: error_rate={item['error_rate']:.2%} "
              f"({item['error_count']}/{item['request_count']}) "
              f"p95={item['p95_latency_ms']}ms score={item['anomaly_score']}")
else:
    print("  None! All services appear healthy.")
    print("  (productCatalogFailure may not be active yet)")
