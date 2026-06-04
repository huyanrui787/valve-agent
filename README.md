# 阀门企业智能标书与报价 Agent

两个 Agent + 一个共享企业知识底座的可运行实现。对应产品方案中的"护城河"——
**确定性核心**:选型规则引擎、报价成本引擎、标书偏离表引擎与废标自检,
全部走可解释的规则与精确查询(**规则保准确**);自然语言解析、技术方案撰写、
话术润色等"表达"任务走可插拔的 LLM Provider(**模型保表达**),默认离线 stub,
**全程无需密钥/算力即可演示**。

## 快速开始

```bash
cd ~/valve-agent
uv sync                      # 安装依赖
uv run valve-agent demo      # 端到端演示(四个"哇时刻")
uv run pytest                # 57 项测试
```

### Web 前端(正式方案)

后端 FastAPI + 前端 React(Vite)。开发时开两个终端:

```bash
# 终端 1 — API (默认 http://127.0.0.1:8000)
uv run valve-api

# 终端 2 — 前端 (默认 http://127.0.0.1:5173, 代理 /api → 后端)
cd frontend && npm install && npm run dev
```

浏览器打开 **http://127.0.0.1:5173**。侧边栏可访问:智能报价、标书应答、招标解析、知识检索。

生产一体部署(先构建前端,再由 API 托管静态资源):

```bash
cd frontend && npm run build
VALVE_API_RELOAD=0 uv run valve-api
# 访问 http://127.0.0.1:8000
```

OpenAPI 文档: http://127.0.0.1:8000/docs

## 命令

```bash
# 自然语言选型(四步规则引擎,带选型依据/淘汰证据)
uv run valve-agent select "球阀 DN200 PN40 蒸汽 250℃ 电动 API 316" --rejections

# 选型 + BOM 成本核算 + 毛利定价(成本透明、毛利可控)
uv run valve-agent quote "球阀 DN200 PN40 蒸汽 250℃ 电动 316" --qty 10 --tier A

# 技术偏离表 + 废标自检(满足/正偏离/负偏离,关键负偏离预警)
uv run valve-agent bid-compliance "球阀 DN200 PN40 蒸汽 250℃ 电动 API 316" --industry 电力

# 批量询价单:逐行选型报价,一张表分钟级出整单
uv run valve-agent batch examples/inquiry.csv --customer "某水务集团" --tier B

# 招标文件解析(PDF/Word/文本)
uv run valve-agent parse-tender examples/sample_tender.txt

# 招标解析 → 选型应答 → Word 成稿
uv run valve-agent tender-bid examples/sample_tender.txt \
  "球阀 DN200 PN40 蒸汽 250℃ 电动 API 316" -o /tmp/bid.docx

# RAG 检索(离线哈希向量;有 DASHSCOPE_API_KEY 时用 Qwen embedding)
uv run valve-agent rag-search "球阀 蒸汽 API 电力业绩"

# 报价单 Word 导出 + CRM/ERP 文件同步(联调占位)
uv run valve-agent export-quote "球阀 DN200 PN40 蒸汽 250℃ 电动 316" /tmp/quote.docx
uv run valve-agent sync-quote "球阀 DN200 PN40 蒸汽 250℃ 电动 316" --customer 某电厂 --sync-dir ./sync
uv run valve-agent sync-bid "球阀 DN200 PN40 蒸汽 250℃ 电动 API 316" --sync-dir ./sync
```

## 架构

```
src/valve_agent/
├── models/        领域模型:阀类/材质/压力枚举、Product/MaterialRule/BomTemplate、
│                  版本化价格、工况 WorkingCondition、招标要求 TenderRequirement
├── knowledge/     企业知识底座:六库内存仓库 + 阀门种子数据(7 型号/6 材质规则/
│                  版本化价格/资质/业绩)
├── engines/       确定性核心(护城河):
│                  - selection  四步选型(硬过滤→材质校验→驱动连接→排序)
│                  - quote      成本拆解→毛利定价→税费/汇率/折扣
│                  - compliance 偏离判定(满足/正偏离/负偏离 + 证据链)
│                  - waste_bid  废标自检 + 资质业绩匹配
├── llm/           可插拔 LLM:Provider 协议 + 离线 stub + Qwen + NL 工况解析
├── documents/     招标文件 PDF/Word 加载、规则解析、Word 成稿导出
├── rag/           向量检索:知识库/招标文本索引(哈希或 Qwen embedding)
├── integrations/  ERP/CRM 协议 + 文件 JSON 同步适配器(可换 HTTP 实现)
├── agents/        编排层:QuoteAgent(选型+报价+批量+同步) / BidAgent(解析+应答+导出)
├── api/           FastAPI REST(/api/*) + valve-api 启动入口
└── cli.py         typer + rich 命令行

frontend/          React + Vite 单页应用(开发端口 5173)
```

## 设计要点

- **底座先行、闭环复用**:两个 Agent 共用同一知识底座;报价确定的型号与价格
  直接回流标书应答表(demo 哇时刻四)。
- **价格版本化**:材料价格按生效日期存时间序列,报价锁定"基准日"价格,
  过期价格自动预警,避免口径漂移。
- **证据链**:选型依据、偏离判定、淘汰原因都引用产品库字段,便于人工复核,
  杜绝模型臆造参数。
- **人在环上**:所有对外产物(报价单、偏离表、技术方案)定位为初稿,供专家把关。

## 当前边界(后续迭代)

- 招标解析为规则+正则抽取,复杂版式/扫描件 PDF 需 OCR 或 LLM 结构化补强。
- RAG 为内存向量库;生产可换 pgvector / Milvus 等,embedding 已支持 Qwen(`DASHSCOPE_API_KEY`)。
- ERP/CRM 当前为文件 JSON 占位;生产实现 `CRMClient` / `ERPClient` 协议即可对接真实系统。
- 报价覆盖标准型号选型;非标定制成本核算待扩展。

> 数据为合理示意值,非真实报价。详见产品方案文档第十一节待确认问题。
