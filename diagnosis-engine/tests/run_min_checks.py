import os
import sys
import json
import yaml

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.adapters import local_json_adapter as adapter

print('Running minimal checks...')

p = os.path.join(REPO_ROOT, 'data', 'mmodel', 'runtime_domain_model.yaml')
if not os.path.isfile(p):
    print('FAIL: runtime_domain_model.yaml missing at', p)
    sys.exit(2)
with open(p, 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f) or {}

print('entity_types present:', 'entity_types' in data)
print('relation_types present:', 'relation_types' in data)
print('entities present (should be False or empty):', bool(data.get('entities')))
print('relations present (should be False or empty):', bool(data.get('relations')))

# Check adapter traces
try:
    index_path = os.path.join(REPO_ROOT, 'examples', 'evaluation_cases', 'basic_root_cause_19', 'index.json')
    case_id = json.load(open(index_path, encoding='utf-8'))[0]['case_id']
    traces = adapter.get_traces(case_id=case_id)
    print('traces loaded:', isinstance(traces, list), 'count=', len(traces))
    services = set()
    for s in traces:
        src = s.get('_source', s)
        svc = src.get('serviceName') or src.get('resource.attributes.service@name')
        if svc:
            services.add(svc)
    print('services found from traces:', services)
    if not services:
        print('FAIL: No services extracted from trace observability data')
        sys.exit(3)
except Exception as e:
    print('FAIL: adapter.get_traces() raised', e)
    sys.exit(4)

print('All minimal checks passed')
sys.exit(0)
