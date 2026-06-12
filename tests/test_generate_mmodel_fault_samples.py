import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "generate_mmodel_fault_samples.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "generate_mmodel_fault_samples", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class InjectTraceSubsetTests(unittest.TestCase):
    def test_inject_trace_keeps_parent_closure_for_target_chain(self):
        module = load_module()
        source_spans = []
        for index in range(99):
            source_spans.append(
                {
                    "traceId": "source-trace",
                    "spanId": f"root-{index}",
                    "parentSpanId": "",
                    "serviceName": f"svc-{index}",
                    "links": [],
                }
            )
        source_spans.extend(
            [
                {
                    "traceId": "source-trace",
                    "spanId": "target-root",
                    "parentSpanId": "",
                    "serviceName": "svc-target",
                    "links": [],
                },
                {
                    "traceId": "source-trace",
                    "spanId": "target-parent",
                    "parentSpanId": "target-root",
                    "serviceName": "svc-target",
                    "links": [],
                },
                {
                    "traceId": "source-trace",
                    "spanId": "target-span",
                    "parentSpanId": "target-parent",
                    "serviceName": "svc-target",
                    "links": [],
                },
            ]
        )

        injected = module.inject_trace(
            source_spans=source_spans,
            source_trace_id="source-trace",
            synthetic_trace_id="synthetic-trace",
            target_span_id="target-span",
            fault_type="downstream_timeout",
        )

        self.assertEqual(len(injected), 100)
        injected_ids = {span["spanId"] for span in injected}
        self.assertIn("target-root", injected_ids)
        self.assertIn("target-parent", injected_ids)
        self.assertIn("target-span", injected_ids)

        for span in injected:
            parent_span_id = span.get("parentSpanId")
            if parent_span_id:
                self.assertIn(parent_span_id, injected_ids)

    def test_choose_scenarios_skips_targets_with_incomplete_ancestry(self):
        module = load_module()
        traces = {
            "trace-a": [
                {
                    "traceId": "trace-a",
                    "spanId": "broken-target",
                    "parentSpanId": "missing-parent",
                    "serviceName": "svc-a",
                    "kind": "SPAN_KIND_CLIENT",
                    "links": [],
                },
                {
                    "traceId": "trace-a",
                    "spanId": "complete-root",
                    "parentSpanId": "",
                    "serviceName": "svc-a",
                    "kind": "SPAN_KIND_SERVER",
                    "links": [],
                },
                {
                    "traceId": "trace-a",
                    "spanId": "complete-target",
                    "parentSpanId": "complete-root",
                    "serviceName": "svc-b",
                    "kind": "SPAN_KIND_CLIENT",
                    "links": [],
                },
            ]
        }

        selected = module.choose_scenarios(traces, per_type=1)

        downstream = next(
            item for item in selected if item["fault_type"] == "downstream_timeout"
        )
        self.assertEqual(downstream["target_span_id"], "complete-target")


if __name__ == "__main__":
    unittest.main()
