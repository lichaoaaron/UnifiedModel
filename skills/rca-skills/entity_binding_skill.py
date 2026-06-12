"""
EntityBindingSkill: maps trace/log/metric fields to MModel entities.
Reads backend/data/mmodel/runtime_domain_model.yaml (via OntologyConfigAdapter) and binding_rules.yaml.
examples/ontology/umodel_data/ is UModel reference material and is NOT used for entity binding.
"""
import time as _time
from datetime import datetime, timezone
from app.skills.base_skill import BaseSkill
from app.models.context import DiagnosisContext
from app.models.diagnosis import SkillResult
from app.adapters import observability_adapter as adapter
from app.adapters.ontology_config_adapter import OntologyConfigAdapter
from app.adapters.binding_rule_adapter import BindingRuleAdapter
from app.rules.binding_rules import extract_ip_after_at


class EntityBindingSkill(BaseSkill):
    skill_name = "EntityBindingSkill"
    tool_name = "MModelSkill/bind_entities"
    title = "实体绑定"

    def run(self, ctx: DiagnosisContext) -> SkillResult:
        t0 = _time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()
        execution_log = []

        # ── Step 1: Load ontology config ────────────────────────────────
        execution_log.append("读取 MModel 本体配置（backend/data/mmodel/runtime_domain_model.yaml）")
        onto = OntologyConfigAdapter()
        entity_types = onto.load_entity_types()
        relation_types = onto.load_relation_types()
        type_names = [et["name"] for et in entity_types]
        execution_log.append(f"识别 {len(entity_types)} 种实体类型：{', '.join(type_names)}")

        # ── Step 2: Load binding rules ───────────────────────────────────
        execution_log.append("读取 specs/02_data/binding_rules.yaml")
        br = BindingRuleAdapter()
        binding_names = br.list_binding_names()
        execution_log.append(f"加载 {len(binding_names)} 条绑定规则")

        # ── Step 3: Apply binding rules on trace/log/metric ─────────────
        execution_log.append("应用绑定规则：trace.serviceName → Service")
        services: set[str] = set()
        instances: set[str] = set()
        interfaces: set[str] = set()
        containers: set[str] = set()

        for span in adapter.get_traces(query_context=ctx.query_context, data_dir=ctx.data_dir, case_id=ctx.case_id):
            svc = span.get("resource.attributes.service@name") or span.get("serviceName", "")
            if svc:
                services.add(svc)
            inst_raw = span.get("resource.attributes.service@instance@id", "")
            if inst_raw:
                ip = extract_ip_after_at(inst_raw)
                if ip:
                    instances.add(ip)
            name = span.get("name", "")
            if name and name.startswith(("GET:", "POST:", "PUT:", "DELETE:")):
                path = name.split(":", 1)[1]
                interfaces.add(path)

        for log in adapter.get_logs(query_context=ctx.query_context, data_dir=ctx.data_dir, case_id=ctx.case_id):
            svc = log.get("resource.attributes.service@name", "")
            if svc:
                services.add(svc)

        for metric in adapter.get_metrics(query_context=ctx.query_context, data_dir=ctx.data_dir, case_id=ctx.case_id):
            svc = metric.get("resource.attributes.compose_service", "")
            if svc:
                services.add(svc)
            ctr = metric.get("resource.attributes.container@name", "")
            if ctr:
                containers.add(ctr)

        execution_log.append("绑定 {services}（Service 实体，来自观测数据）")
        execution_log.append(f"绑定 {', '.join(sorted(instances))} （Instance 实体）" if instances else "Instance 实体（来自观测数据或本体配置）")
        execution_log.append(f"绑定 {', '.join(sorted(interfaces))}（Interface 实体）" if interfaces else "Interface 实体（来自观测数据或本体配置）")

        execution_log.append("完成 Service, Instance, Interface, Container 绑定")

        bindings = []
        for s in sorted(services):
            bindings.append({"entity_type": "Service", "name": s})
        for i in sorted(instances):
            bindings.append({"entity_type": "Instance", "ip": i})
        for iface in sorted(interfaces):
            bindings.append({"entity_type": "Interface", "path": iface})
        for ctr in sorted(containers):
            bindings.append({"entity_type": "Container", "name": ctr})

        ctx.entity_result = {
            "services": sorted(services),
            "instances": sorted(instances),
            "interfaces": sorted(interfaces),
            "containers": sorted(containers),
            "businesses": [],
            "business_flows": [],
            "bindings": bindings,
        }

        duration_ms = max(1, int((_time.monotonic() - t0) * 1000))
        finished_at = datetime.now(timezone.utc).isoformat()

        evidence = [
            f"本体来源：backend/data/mmodel/runtime_domain_model.yaml（仅类型/关系定义），"
            f"识别 {len(entity_types)} 种实体类型、{len(relation_types)} 种关系类型",
            f"读取 binding_rules.yaml，加载 {len(binding_names)} 条绑定规则",
            f"trace.serviceName → {', '.join(sorted(services))}（Service 实体，来自观测数据）",
            f"trace.service@instance@id → {', '.join(sorted(instances)) or '来自观测数据或本体配置'}（Instance 实体）",
            f"trace.span.name → {', '.join(sorted(interfaces)) or '来自观测数据或本体配置'}（Interface 实体）",
        ]
        return SkillResult(
            skill_name=self.skill_name,
            tool_name=self.tool_name,
            title=self.title,
            status="success",
            summary=(
                f"识别出 {len(services)} 个服务、{len(instances)} 个实例、"
                f"{len(interfaces)} 个接口实体，基于 MModel 本体（{len(entity_types)} 种实体类型）完成绑定。"
            ),
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            input={
                "domain_model_file": "backend/data/mmodel/runtime_domain_model.yaml",
                "binding_rules_file": "specs/02_data/binding_rules.yaml",
                "sources": ["trace", "log", "metric"],
            },
            output=ctx.entity_result,
            evidence=evidence,
            execution_log=execution_log,
            explanation=(
                "读取 MModel 本体配置和绑定规则，将 trace/log/metric 字段映射到实体层。"
                "默认只输出本次观测数据中出现的运行态实体，不补入全局业务本体实例。"
            ),
        )
