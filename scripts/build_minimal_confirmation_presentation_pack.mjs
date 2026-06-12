import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath =
  "C:/Users/chaoJ/Desktop/UnifiedModel/outputs/cmcc4a_expert_minimal_confirmation_pack.optimized.xlsx";
const outputPath =
  "C:/Users/chaoJ/Desktop/UnifiedModel/outputs/cmcc4a_expert_minimal_confirmation_pack.presentation_ready.v4.xlsx";

const headerFill = "#1F4E78";
const headerFont = "#FFFFFF";
const mustFill = "#E2F0D9";
const shouldFill = "#FFF2CC";
const deferFill = "#F2F2F2";
const noteFill = "#DDEBF7";
const borderColor = "#B7C9D6";

function setHeader(range) {
  range.format = {
    fill: headerFill,
    font: { bold: true, color: headerFont },
    wrapText: true,
    horizontalAlignment: "center",
    verticalAlignment: "center",
    borders: { preset: "all", style: "thin", color: borderColor },
  };
}

function setBody(range, fill) {
  range.format = {
    fill,
    wrapText: true,
    verticalAlignment: "top",
    borders: { preset: "all", style: "thin", color: borderColor },
  };
}

function markRow(sheet, rowNumber, fill) {
  setBody(sheet.getRange(`A${rowNumber}:P${rowNumber}`), fill);
}

function markRowTo(sheet, rowNumber, endCol, fill) {
  setBody(sheet.getRange(`A${rowNumber}:${endCol}${rowNumber}`), fill);
}

const blob = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(blob);

const guide = workbook.worksheets.getItem("0_请专家确认_最小版");
guide.getRange("A1:B6").values = [
  ["项目", "填写说明"],
  ["目标", "这版只服务一个目标：尽快拿到可以支撑 8 月底领导演示的最小专家结论。"],
  [
    "本次只做",
    "优先确认 1 条能讲通的故障链路，围绕 service / gateway / redis / database / business_system 做最小闭环，不追求一次补全所有对象。",
  ],
  [
    "演示必填",
    "1. 核心实体：service、database、redis、gateway。2. 核心关系：business_system->service、service->database、service->redis、gateway->service。3. 高频 serviceName 对照。4. Q1/Q3/Q5 给出结论。",
  ],
  [
    "确认原则",
    "不要求专家先确认“对象中文名”。优先确认：是否独立建模、对象边界、主键字段、与可观测字段的对应关系。中文名只作为可选展示名。",
  ],
  [
    "填写示例",
    "serviceName 对照列建议这样填：1. 对应对象：认证服务 2. 并入对象：platform-api 3. 暂无法判断，原因：缺少系统说明。不要只写“看不懂”或留空。",
  ],
];
guide.getRange("A1:B1").format.rowHeightPx = 28;
guide.getRange("A2:A6").format.font = { bold: true };
setHeader(guide.getRange("A1:B1"));
setBody(guide.getRange("A2:B3"), noteFill);
setBody(guide.getRange("A4:B4"), mustFill);
setBody(guide.getRange("A5:B5"), deferFill);
setBody(guide.getRange("A6:B6"), shouldFill);
guide.getRange("A:A").format.columnWidthPx = 130;
guide.getRange("B:B").format.columnWidthPx = 760;
guide.freezePanes.freezeRows(1);

const entity = workbook.worksheets.getItem("1_核心实体确认");
setHeader(entity.getRange("A1:P1"));
entity.getRange("C1").values = [["display_name（可选展示名）"]];
entity.getRange("K2:K7").values = [
  ["请重点确认：是否应独立建模、对象边界、候选主键、与观测字段的对应关系是否正确。展示名可后补。"],
  ["请重点确认：是否建议一期入模；若入模，主键和观测字段是否稳定。"],
  ["请重点确认：是否应独立建模、对象边界、候选主键、与观测字段的对应关系是否正确。展示名可后补。"],
  ["请重点确认：是否应独立建模、对象边界、候选主键、与观测字段的对应关系是否正确。展示名可后补。"],
  ["请重点确认：如果本次故障链路涉及 MQ，候选主键和观测字段映射是否稳定。"],
  ["请重点确认：是否应独立建模、对象边界、候选主键、与观测字段的对应关系是否正确。展示名可后补。"],
];
entity.getRange("I2:I7").values = [
  ["演示必填"],
  ["可暂缓"],
  ["演示必填"],
  ["演示必填"],
  ["建议补齐"],
  ["演示必填"],
];
entity.getRange("J2:J7").values = [
  ["优先确认是否独立建模、边界、主键、观测字段映射；展示名可后补"],
  ["若一期不入模，请直接写“建议一期不入模”"],
  ["直接确认主键层级和观测映射；cluster / instance 二选一"],
  ["直接确认实例层级、命名口径和 trace/metric 映射"],
  ["如当前没有故障链路依赖，可放到第二批"],
  ["先确认网关实例/上游目标与观测字段映射，route 细化可后置"],
];
markRow(entity, 2, mustFill);
markRow(entity, 3, deferFill);
markRow(entity, 4, mustFill);
markRow(entity, 5, mustFill);
markRow(entity, 6, shouldFill);
markRow(entity, 7, mustFill);
entity.getRange("A:P").format.wrapText = true;
entity.getRange("A:A").format.columnWidthPx = 74;
entity.getRange("B:B").format.columnWidthPx = 165;
entity.getRange("C:C").format.columnWidthPx = 110;
entity.getRange("D:H").format.columnWidthPx = 180;
entity.getRange("I:J").format.columnWidthPx = 130;
entity.getRange("K:P").format.columnWidthPx = 160;
entity.freezePanes.freezeRows(1);

const relation = workbook.worksheets.getItem("2_核心关系确认");
setHeader(relation.getRange("A1:O1"));
relation.getRange("I2:I6").values = [
  ["演示必填：先确认业务入口到服务"],
  ["演示必填：缓存依赖关系"],
  ["演示必填：数据库依赖关系"],
  ["建议补齐：若本次链路涉及消息"],
  ["待验证：当前网关到服务的观测数据还未采集"],
];
relation.getRange("E6:H6").values = [[
  "当前未从观测数据中采到可稳定支撑 gateway->service 的字段",
  "待补采集后确认，例如 backend / upstream / gateway实例字段",
  "先记录为待验证项，不作为本轮演示必达关系",
  "当前缺观测数据，不能仅凭经验确认",
]];
relation.getRange("J6:J6").values = [[
  "请重点确认：当前先不落这条实例关系，待采到观测数据后再确认方向和字段。",
]];
markRowTo(relation, 2, "O", mustFill);
markRowTo(relation, 3, "O", mustFill);
markRowTo(relation, 4, "O", mustFill);
markRowTo(relation, 5, "O", shouldFill);
 markRowTo(relation, 6, "O", deferFill);
relation.getRange("A:O").format.wrapText = true;
relation.getRange("A:A").format.columnWidthPx = 220;
relation.getRange("B:C").format.columnWidthPx = 145;
relation.getRange("D:D").format.columnWidthPx = 92;
relation.getRange("E:H").format.columnWidthPx = 180;
relation.getRange("I:O").format.columnWidthPx = 165;
relation.freezePanes.freezeRows(1);

const serviceMap = workbook.worksheets.getItem("3_serviceName对照确认");
setHeader(serviceMap.getRange("A1:L1"));
serviceMap.getRange("E1").values = [["专家填写：对应哪个对象"]];
serviceMap.getRange("G1").values = [["填写示例"]];
serviceMap.getRange("G2:G21").values = [
  ["例：对应对象：认证服务"],
  ["例：对应对象：配置服务"],
  ["例：对应对象：统一身份管理服务"],
  ["例：对应对象：AMC服务"],
  ["例：对应对象：PMC服务"],
  ["例：对应对象：应用服务"],
  ["例：对应对象：渠道集成服务"],
  ["例：暂无法判断，原因：缺少模块说明"],
  ["例：并入对象：ais-mmj-service"],
  ["例：对应对象：短信消息队列"],
  ["例：对应对象：金库服务"],
  ["例：暂无法判断，原因：缺少模块说明"],
  ["例：对应对象：短信任务服务"],
  ["例：暂无法判断，原因：缺少模块说明"],
  ["例：对应对象：AGW控制台"],
  ["例：对应对象：OGW控制台"],
  ["例：暂无法判断，原因：低频且缺少说明"],
  ["例：暂无法判断，原因：低频且缺少说明"],
  ["例：暂无法判断，原因：低频且缺少说明"],
  ["例：对应对象：统一接入网关"],
];
serviceMap.getRange("F2:F21").values = [
  ["演示必填：优先确认；不是只填中文名，要判断映射对象"],
  ["演示必填：优先确认；不是只填中文名，要判断映射对象"],
  ["演示必填：优先确认；不是只填中文名，要判断映射对象"],
  ["演示必填：优先确认；不是只填中文名，要判断映射对象"],
  ["演示必填：优先确认；不是只填中文名，要判断映射对象"],
  ["演示必填：优先确认；不是只填中文名，要判断映射对象"],
  ["演示必填：优先确认；不是只填中文名，要判断映射对象"],
  ["演示必填：优先确认；不是只填中文名，要判断映射对象"],
  ["演示必填：优先确认；不是只填中文名，要判断映射对象"],
  ["建议补齐：若明确是 MQ，可直接写对应对象"],
  ["建议补齐：有时间再确认"],
  ["建议补齐：有时间再确认"],
  ["建议补齐：有时间再确认"],
  ["建议补齐：有时间再确认"],
  ["建议补齐：有时间再确认"],
  ["建议补齐：有时间再确认"],
  ["可暂缓：低频项"],
  ["可暂缓：低频项"],
  ["可暂缓：低频项"],
  ["演示必填：优先确认；通常对应网关对象"],
];
for (const row of [2, 3, 4, 5, 6, 7, 8, 9, 10, 21]) {
  markRowTo(serviceMap, row, "L", mustFill);
}
for (const row of [11, 12, 13, 14, 15, 16, 17]) {
  markRowTo(serviceMap, row, "L", shouldFill);
}
for (const row of [18, 19, 20]) {
  markRowTo(serviceMap, row, "L", deferFill);
}
serviceMap.getRange("A:L").format.wrapText = true;
serviceMap.getRange("A:A").format.columnWidthPx = 72;
serviceMap.getRange("B:B").format.columnWidthPx = 180;
serviceMap.getRange("C:C").format.columnWidthPx = 88;
serviceMap.getRange("D:D").format.columnWidthPx = 112;
serviceMap.getRange("E:L").format.columnWidthPx = 160;
serviceMap.freezePanes.freezeRows(1);

const questions = workbook.worksheets.getItem("4_关键问题结论");
questions.getRange("A1:M7").values = [
  ["ID","Topic","对应sheet","Question","Why It Matters","Owner","专家操作建议","需重点确认什么","专家处理结果","如需修改，请写修改后的值","如需补充，请写补充内容","修改/补充说明","专家备注/待确认"],
  ["Q1","统一命名","主要对应 3_serviceName对照确认；也影响 1_核心实体确认","专家对象名和真实 serviceName 还没一一对齐，例如“认证服务/金库服务/GDC/self服务”分别对应哪些实际 serviceName 需要确认","直接影响 entity_set 命名和 data_link 映射","专家+工程","演示必填：请直接给结论","请尽量直接给结论；如果暂时不能定，请写清楚还缺什么信息。","待确认",null,null,null,null],
  ["Q2","账号实体是否现在入模","主要对应 1_核心实体确认","userId/accountId 在专家判断里很重要，但当前抽样观测数据里还没有明显稳定的结构化字段","决定是否现在就落 cmcc4a.account","专家+工程","可暂缓：若一期不入模可先留结论","请尽量直接给结论；如果暂时不能定，请写清楚还缺什么信息。","待确认",null,null,null,null],
  ["Q3","Redis/DB/MQ 主键层级","主要对应 1_核心实体确认；也影响 2_核心关系确认","Redis、数据库、MQ 实体到底按 cluster、instance、dbName、topic、consumerGroup 还是 jobName 建模，需要统一粒度","影响主键稳定性和关系稳定性","工程+中间件专家","演示必填：统一主键层级","请尽量直接给结论；如果暂时不能定，请写清楚还缺什么信息。","待确认",null,null,null,null],
  ["Q4","网关建模粒度","主要对应 1_核心实体确认；也影响 2_核心关系确认","一期先不默认建 route 子实体，先按 gateway 实例/上游目标粗粒度建模；后续拿到稳定路由字段再细化。","避免在缺少稳定 route 观测字段时过度建模","工程","已确认：不默认建 route 子实体","本轮按粗粒度处理即可；若后续补到稳定 route 字段，再单独升级。","已确认","不默认建 route 子实体",null,"按当前结论执行",null],
  ["Q5","生产查询入口","对应 1/2/3 落地前提；偏 dataset/datalink","目前只知道本地导出路径，还缺生产上的 OpenSearch/Prom/APM 查询入口、索引名、时间字段","影响 storage 和 storage_link 落地","工程","演示必填：必须补到可查询入口","请尽量直接给结论；如果暂时不能定，请写清楚还缺什么信息。","待确认",null,null,null,null],
  ["Q6","示例内容清理","对应 1/2/3 全部","专家表里仍有少量示例/模板内容，正式入模前需要删掉","避免错误知识进入本体","专家","可暂缓：正式落模前清理即可","请尽量直接给结论；如果暂时不能定，请写清楚还缺什么信息。","待确认",null,null,null,null],
];
setHeader(questions.getRange("A1:M1"));
markRowTo(questions, 2, "M", mustFill);
markRowTo(questions, 3, "M", deferFill);
markRowTo(questions, 4, "M", mustFill);
markRowTo(questions, 5, "M", shouldFill);
markRowTo(questions, 6, "M", mustFill);
markRowTo(questions, 7, "M", deferFill);
questions.getRange("A:M").format.wrapText = true;
questions.getRange("A:A").format.columnWidthPx = 60;
questions.getRange("B:B").format.columnWidthPx = 120;
questions.getRange("C:C").format.columnWidthPx = 210;
questions.getRange("D:F").format.columnWidthPx = 220;
questions.getRange("G:M").format.columnWidthPx = 170;
questions.freezePanes.freezeRows(1);

const checklist = workbook.worksheets.add("5_演示准入清单");
checklist.getRange("A1:D11").values = [
  ["模块", "演示必达结果", "当前填写动作", "完成判定"],
  ["核心实体", "service / database / redis / gateway 口径确认", "只改这 4 类的主键、范围、观测字段映射；中文名可后补", "专家处理结果不为空"],
  ["核心关系", "先确认 3 条已具备观测依据的关系", "只改入口服务、缓存、数据库关系；gateway->service 待补采集", "关键关系已确认或已标注待验证"],
  ["serviceName 对照", "至少确认 8-10 个高频 serviceName", "优先处理绿色行；按“对应对象 / 并入对象 / 暂无法判断”模板填写", "高频行已完成对象映射"],
  ["关键问题 Q1", "专家对象名和真实 serviceName 对齐", "给出可落模型的统一命名", "有明确结论"],
  ["关键问题 Q3", "Redis/DB/MQ 主键层级统一", "先按最稳定粒度定", "有明确结论"],
  ["关键问题 Q4", "已确认不默认建 route 子实体", "按粗粒度 gateway 建模执行", "已确认"],
  ["关键问题 Q5", "拿到生产查询入口", "补 OpenSearch / Prom / APM 的入口、索引名、时间字段", "后续补齐也可"],
  ["可暂缓项", "account、低频服务、示例清理、展示中文名", "若暂不处理请直接写“二期”", "都已标注暂缓原因"],
  ["颜色说明", "绿色=演示必填", "黄色=建议补齐", "灰色=可暂缓"],
  ["回传口径", "不空着，不模糊", "不确定就写缺什么信息", "能支持一次完整演示问答"],
];
setHeader(checklist.getRange("A1:D1"));
setBody(checklist.getRange("A2:D7"), mustFill);
setBody(checklist.getRange("A8:D8"), shouldFill);
setBody(checklist.getRange("A9:D9"), deferFill);
setBody(checklist.getRange("A10:D10"), noteFill);
setBody(checklist.getRange("A11:D11"), shouldFill);
checklist.getRange("A:D").format.wrapText = true;
checklist.getRange("A:A").format.columnWidthPx = 110;
checklist.getRange("B:D").format.columnWidthPx = 240;
checklist.freezePanes.freezeRows(1);

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);

console.log(outputPath);
