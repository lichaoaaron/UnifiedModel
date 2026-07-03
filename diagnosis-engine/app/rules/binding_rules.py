"""
Binding rules: maps raw data fields to MModel entity types.
Based on specs/02_data/binding_rules.yaml
"""

BINDING_RULES = [
    {
        "name": "trace_to_service",
        "source": "trace",
        "source_field": "resource.attributes.service@name",
        "target_entity": "service",
    },
    {
        "name": "trace_to_instance",
        "source": "trace",
        "source_field": "resource.attributes.service@instance@id",
        "target_entity": "instance",
        "transform": "extract_ip_after_at",
    },
    {
        "name": "trace_to_interface",
        "source": "trace",
        "source_field": "name",
        "target_entity": "interface",
    },
    {
        "name": "log_to_service",
        "source": "log",
        "source_field": "resource.attributes.service@name",
        "target_entity": "service",
    },
    {
        "name": "metric_to_service",
        "source": "metric",
        "source_field": "resource.attributes.compose_service",
        "target_entity": "service",
    },
    {
        "name": "metric_to_container",
        "source": "metric",
        "source_field": "resource.attributes.container@name",
        "target_entity": "container",
    },
]


def extract_ip_after_at(raw: str) -> str:
    """Extract IP from patterns like 'hash@ip' or 'hash@ip:port'"""
    if "@" in raw:
        parts = raw.split("@")
        ip_part = parts[-1]
        return ip_part.split(":")[0]
    return raw
