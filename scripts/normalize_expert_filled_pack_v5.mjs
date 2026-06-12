import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath =
  "C:/Users/chaoJ/Desktop/UnifiedModel/outputs/cmcc4a_expert_minimal_confirmation_pack.presentation_ready.v5.xlsx";
const outputPath =
  "C:/Users/chaoJ/Desktop/UnifiedModel/outputs/cmcc4a_expert_minimal_confirmation_pack.presentation_ready.v6.xlsx";

const inputBlob = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(inputBlob);

const guide = workbook.worksheets.getItem("0_请专家确认_最小版");
guide.getRange("A1:B6").values = [
  ["项目", "填写说明"],
  ["目标", "这版只服务一个目标：尽快拿到可以支撑 8 月底领导演示的最小专家结论。"],
  ["本次只做", "优先确认 1 条能讲通的故障链路，围绕 service / gateway / redis / database / business_system 做最小闭环，不追求一次补全所有对象。"],
  ["演示必填", "1. serviceName 直接作为具体对象。2. 核心实体：service、database、redis、gateway。3. 核心关系优先确认 service->redis、service->database。4. Q2/Q3/Q4 给出明确结论。"],
  ["确认原则", "不要求专家再逐条确认 serviceName 映射。serviceName 本身就是具体对象；一期重点确认非 service 对象的建模粒度和关系是否适合固化。"],
  ["填写结果说明", "本版已按专家原始反馈做规范化整理：已确认 / 阶段性确认 / 待业务补充 / 待工程补充 / 本轮不处理。"],
];

const entity = workbook.worksheets.getItem("1_核心实体确认");
entity.getRange("A2:P7").values = [
  ["P0","cmcc4a.service","4A服务","认证 / 登录 / 鉴权 / 资源 / 金库等应用服务","serviceName","resource.attributes.service@name","观测数据中已有大量稳定 serviceName；serviceName 本身就是具体对象。","辅助字段先仅保留服务侧稳定字段。","已确认","一期按 serviceName 直接识别 service 实体；展示名可后补。","请确认 service 是否独立建模、对象边界是否正确。","已确认",null,"一期按 serviceName 直接作为具体对象标识。",null,null],
  ["P0","cmcc4a.account","账号/用户","登录账号、鉴权账号、从账号、资源账号","userId or accountId","clientId, phone, tenantId","当前观测字段仍不稳定，且账号枚举值体量大，直接入模可能带来性能问题。","需业务改造后再评估。","一期不入模","本期不纳入模型；后续按业务改造结果再评估。","请确认是否一期入模。","已确认",null,"建议一期不纳入；需业务改造，暂未具备。",null,null],
  ["P0","cmcc4a.redis","Redis/会话缓存","Token 缓存、Session 缓存、事务锁缓存","暂不固化实例级主键（一期按资源类型）","trace: span.attributes.db@type=redis；metric: resource.attributes.service@instance@id","trace 中能看到 Redis 调用，metric 中能看到实例信息，但当前缺稳定实例级统一标识。","待后续补充稳定实例标识后，再细化到 cluster / instance。","阶段性确认","一期先按资源类型/依赖对象处理，不固化具体实例主键。","请确认一期是否先不下实例级主键结论。","阶段性确认",null,"当前不强行选择 cluster 或 instance；后续补采后再细化。",null,null],
  ["P0","cmcc4a.database","数据库","业务库、磐维数据库、MySQL/PG 实例","暂不固化实例级主键（一期按资源类型）","trace: span.attributes.db@type、db@instance、db@statement","trace 中有数据库调用和实例/语句信息，但当前还不足以统一成稳定实例级主键。","待后续补充稳定实例标识后，再细化到 instance / dbName。","阶段性确认","一期先按资源类型/依赖对象处理，不固化具体实例主键。","请确认一期是否先不下实例级主键结论。","阶段性确认",null,"当前不强行统一 instance / dbName；后续补采后再细化。",null,null],
  ["P1","cmcc4a.mq","消息队列/任务","MQ Topic、消费者组、调度任务、补偿任务","topic or consumerGroup","metric.attributes.topic, metric.attributes.group, metric.attributes.clientId, metric.attributes.cmd","当前案例调用链中无 MQ。","如后续出现 MQ 相关故障链路，再单独细化。","本轮不处理","本轮演示不纳入 MQ 对象。","请确认当前案例是否涉及 MQ。","已确认",null,"当前调用链中无 MQ，本轮不处理。",null,null],
  ["P1","cmcc4a.gateway","网关/负载均衡","入口网关、Nginx、路由、VIP","gateway 实例（不默认建 route 子实体）","metric.attributes.name, metric.attributes.url, metric.attributes.backend","网关对象存在，但当前调用链中无网关观测信息。","待后续补采集后再验证 gateway->service 实例关系。","已确认","按粗粒度处理，不默认建 route 子实体。","请确认本轮是否只保留粗粒度 gateway。","已确认",null,"当前调用链中无网关信息；本轮只保留粗粒度 gateway。",null,null],
];

const relation = workbook.worksheets.getItem("2_核心关系确认");
const relationRows = [
  ["cmcc4a.business_system_calls_cmcc4a.service","cmcc4a.business_system","cmcc4a.service","calls","专家表中已有业务入口相关描述","appId/appCode -> serviceName（待业务确认）","仍需确认业务系统命名和边界","用于回答哪个渠道调用哪个 4A 服务","待业务补充","请重点确认业务入口到服务的映射口径。","待业务补充",null,"需确认 appId/appCode 是否可稳定代表业务应用。",null,null],
  ["business_contains_interface","业务","接口","contains","固定层级关系","业务 -> 接口","无","用于表达业务和接口的包含关系","已确认","固定包含关系，可直接按 contains 表达。","确认关系方向即可。","已确认",null,"固定包含关系。",null,null],
  ["interface_exposes_service","接口","服务","contains","固定层级关系","接口 -> 服务","无","用于表达接口和服务的包含关系","已确认","固定包含关系，可直接按 contains 表达。","确认关系方向即可。","已确认",null,"固定包含关系。",null,null],
  ["service_calls_service","服务","服务","calls","trace 中可观测到运行时服务调用","运行时 trace 关系","是否适合固化为模型需按场景判断","更适合表达运行时调用，不是绝对静态关系","阶段性确认","可保留为运行时关系，不建议一开始固化为绝对静态模型关系。","请确认是否按运行时关系表达。","阶段性确认",null,"依赖具体业务/接口场景，建议运行时生成。",null,null],
  ["cmcc4a.service_use_cmcc4a.redis","cmcc4a.service","cmcc4a.redis","use","trace 中已有 Redis 调用","serviceName -> Redis 资源类型/候选实例","Redis 实体主键仍待后续细化","可用于表达服务对缓存资源的依赖","阶段性确认","可保留为运行时依赖关系；不建议当前固化为绝对静态关系。","请确认关系方向和表达方式。","阶段性确认",null,"当前更适合运行时依赖，不强行固化。",null,null],
  ["cmcc4a.service_use_cmcc4a.database","cmcc4a.service","cmcc4a.database","use","trace 中已有 db instance/statement","serviceName -> 数据库资源类型/候选实例","数据库主键层级仍待后续细化","可用于表达服务对数据库资源的依赖","阶段性确认","可保留为运行时依赖关系；不建议当前固化为绝对静态关系。","请确认关系方向和表达方式。","阶段性确认",null,"当前更适合运行时依赖，不强行固化。",null,null],
  ["cmcc4a.service_sends_to_cmcc4a.mq","cmcc4a.service","cmcc4a.mq","sends_to","metric 中存在 topic/group 字段","serviceName -> topic/consumerGroup","当前案例调用链中无 MQ","本轮演示不纳入 MQ 关系","本轮不处理","当前案例不处理 MQ 关系。","请确认当前案例是否涉及 MQ。","已确认",null,"当前调用链中无 MQ，本轮不处理。",null,null],
  ["cmcc4a.gateway_serves_cmcc4a.service","cmcc4a.gateway","cmcc4a.service","serves","当前未采到可稳定支撑 gateway->service 的观测字段","待补采 backend / upstream / gateway 实例字段","当前缺观测数据","先记录为待验证项，不作为本轮演示必达关系","待工程补充","待采到观测数据后再确认方向和字段。","请确认当前不落这条实例关系。","待工程补充",null,"当前网关到服务的观测数据未采集。",null,null],
];
relation.getRange("A2:O9").values = relationRows.map((row) => row.slice(0, 15));

let serviceSheet = workbook.worksheets.getItem("3_serviceName对照确认");
try {
  serviceSheet.name = "3_观测对象清单（serviceName）";
} catch {}
serviceSheet = workbook.worksheets.getItem("3_观测对象清单（serviceName）") || serviceSheet;
serviceSheet.getRange("A1:L21").values = [
  ["Source","Observed serviceName","Sample Count","Guessed Object Type","对象确认结论","处理方式","说明","专家处理结果","如需修改，请写修改后的值","如需补充，请写补充内容","修改/补充说明","专家备注/待确认"],
  ["log","ais-consumer",49288,"service","serviceName 直接作为具体对象","无需逐条映射","专家已确认 serviceName 本身就是具体对象。","已确认",null,null,null,null],
  ["log","ais-configure",39299,"service","serviceName 直接作为具体对象","无需逐条映射","专家已确认 serviceName 本身就是具体对象。","已确认",null,null,null,null],
  ["log","iam-manage",14852,"service","serviceName 直接作为具体对象","无需逐条映射","专家已确认 serviceName 本身就是具体对象。","已确认",null,null,null,null],
  ["log","ais-amc",14435,"service","serviceName 直接作为具体对象","无需逐条映射","专家已确认 serviceName 本身就是具体对象。","已确认",null,null,null,null],
  ["log","ais-pmc",6309,"service","serviceName 直接作为具体对象","无需逐条映射","专家已确认 serviceName 本身就是具体对象。","已确认",null,null,null,null],
  ["log","ais-application-service",4762,"service","serviceName 直接作为具体对象","无需逐条映射","专家已确认 serviceName 本身就是具体对象。","已确认",null,null,null,null],
  ["log","csc-cm-it",3728,"service","serviceName 直接作为具体对象","无需逐条映射","专家已确认 serviceName 本身就是具体对象。","已确认",null,null,null,null],
  ["log","aif-server",2270,"service","serviceName 直接作为具体对象","无需逐条映射","对象含义后续可补展示名，但不影响当前对象识别。","已确认",null,null,null,null],
  ["log","ais-mmj-service",1466,"service","serviceName 直接作为具体对象","无需逐条映射","对象含义后续可补展示名，但不影响当前对象识别。","已确认",null,null,null,null],
  ["log","csc-cm-it-mq",1265,"mq","serviceName 直接作为具体对象","本轮不处理","当前案例调用链中无 MQ，本轮演示不纳入。","已确认",null,null,null,null],
  ["log","ais-gold",813,"service","serviceName 直接作为具体对象","无需逐条映射","专家已确认 serviceName 本身就是具体对象。","已确认",null,null,null,null],
  ["log","aif-manage",506,"service","serviceName 直接作为具体对象","无需逐条映射","对象含义后续可补展示名，但不影响当前对象识别。","已确认",null,null,null,null],
  ["log","ai-sms-task",423,"service","serviceName 直接作为具体对象","无需逐条映射","对象含义后续可补展示名，但不影响当前对象识别。","已确认",null,null,null,null],
  ["log","bsc",182,"service","serviceName 直接作为具体对象","无需逐条映射","对象含义后续可补展示名，但不影响当前对象识别。","已确认",null,null,null,null],
  ["log","agw-console",154,"service","serviceName 直接作为具体对象","无需逐条映射","对象含义后续可补展示名，但不影响当前对象识别。","已确认",null,null,null,null],
  ["log","ogw-console",126,"service","serviceName 直接作为具体对象","无需逐条映射","对象含义后续可补展示名，但不影响当前对象识别。","已确认",null,null,null,null],
  ["log","ais-liteflow",47,"service","serviceName 直接作为具体对象","可暂缓补展示名","低频对象，不影响当前对象识别。","已确认",null,null,null,null],
  ["log","ais-msg-center",36,"service","serviceName 直接作为具体对象","可暂缓补展示名","低频对象，不影响当前对象识别。","已确认",null,null,null,null],
  ["log","ais-form",21,"service","serviceName 直接作为具体对象","可暂缓补展示名","低频对象，不影响当前对象识别。","已确认",null,null,null,null],
  ["log","platform-api",13,"gateway","serviceName 直接作为具体对象","无需逐条映射","可作为 gateway 对象名；当前调用链未体现网关关系。","已确认",null,null,null,null],
];

const questions = workbook.worksheets.getItem("4_关键问题结论");
questions.getRange("A2:M6").values = [
  ["Q1","统一命名","主要对应 3_观测对象清单（serviceName）；也影响 1_核心实体确认","serviceName 是否需要再映射为其他对象名，还是可直接作为具体对象。","直接影响 entity 命名和对象识别方式","专家+工程","已确认：serviceName 直接作为具体对象","本轮无需再做 serviceName 到对象名的逐条映射。","已确认",null,"serviceName 本身就是具体对象；当前 20 个对象基本覆盖 4A 对象。","按该结论执行",null],
  ["Q2","账号实体是否现在入模","主要对应 1_核心实体确认","账号实体是否在一期纳入模型。","决定是否现在就落 cmcc4a.account","专家+工程","已确认：一期不入模","本期不纳入；后续按业务改造结果再评估。","已确认",null,"建议一期不纳入；需业务改造，暂未具备。","按该结论执行",null],
  ["Q3","Redis/DB/MQ 主键层级","主要对应 1_核心实体确认；也影响 2_核心关系确认","Redis、数据库、MQ 是否现在就统一到实例级主键粒度。","影响主键稳定性和关系稳定性","工程+中间件专家","阶段性结论：一期不强行统一实例级主键","Redis/DB 一期先按资源类型处理，不固化具体实例主键；MQ 因当前调用链无观测信息，本轮不处理。","阶段性确认",null,"后续拿到稳定实例标识后，再细化到 cluster / instance / dbName / topic / consumerGroup。","按阶段性结论执行",null],
  ["Q4","网关建模粒度","主要对应 1_核心实体确认；也影响 2_核心关系确认","一期是否默认建 route 子实体。","避免在缺少稳定 route 观测字段时过度建模","工程","已确认：不默认建 route 子实体","本轮按粗粒度 gateway 处理即可；若后续补到稳定 route 字段，再单独升级。","已确认","不默认建 route 子实体",null,"按当前结论执行",null],
  ["Q5","生产查询入口","对应 1/2/3 落地前提；偏 dataset/datalink","生产上的 OpenSearch/Prom/APM 查询入口、索引名、时间字段。","影响 storage 和 storage_link 落地","工程","转工程侧补充","不在本次专家规范化表格中处理。","待工程补充",null,"后续由工程侧单独补充。","从本次专家确认范围移出",null],
];

const checklist = workbook.worksheets.getItem("5_演示准入清单");
checklist.getRange("A1:D11").values = [
  ["模块","演示必达结果","当前填写动作","完成判定"],
  ["核心实体","service / database / redis / gateway 口径确认","service 已确认；account 一期不入模；Redis/DB 先按资源类型处理；gateway 仅保留粗粒度。","已形成可执行结论"],
  ["核心关系","先确认 3 条已具备观测依据的关系","service->redis、service->database 按运行时依赖表达；gateway->service 待补采集。","关键关系已确认或已标注待验证"],
  ["观测对象清单","serviceName 直接作为具体对象","无需逐条映射；当前 20 个对象基本覆盖 4A 对象。","已确认"],
  ["关键问题 Q1","serviceName 直接作为具体对象","不再做逐条对象映射。","已确认"],
  ["关键问题 Q2","账号一期不入模","后续按业务改造结果再评估。","已确认"],
  ["关键问题 Q3","Redis/DB/MQ 先按阶段性结论处理","一期不强行统一实例级主键；MQ 本轮不处理。","阶段性确认"],
  ["关键问题 Q4","已确认不默认建 route 子实体","按粗粒度 gateway 建模执行。","已确认"],
  ["关键问题 Q5","生产查询入口由工程侧补充","不在本次专家确认表中处理。","待工程补充"],
  ["颜色说明","绿色=已确认/演示可用","黄色=阶段性确认","灰色=待工程补充/本轮不处理"],
  ["回传口径","专家结论已规范化入表","保留结论、删去口语化填法和错位说明。","可直接用于后续建模讨论"],
];

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
