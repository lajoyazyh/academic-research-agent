# Agent 系统详细设计说明书 (Detailed Design Document)

## 1. 系统总体架构与拓扑

面向复杂的学术科研工作流程，Agent 需要极大层度的自治性与防偏离特性。本系统采取 **Plan-and-Execute (宏观规划)** 复合 **ReAct (微观执行)** 与 **Reflexion (兜底反思)** 的混合结构。它通过一套基于状态（State）控制的数据总线，将核心循环、外部物理工具集合与异步前端大盘连接起来。

### 1.1 架构层级流转图
```mermaid
graph TD
    User[用户/评测平台] -->|下发研究议题| MasterController
    subgraph Core Engine (core/)
        Plan[Plan 阶段: 显式任务拆解]
        StateMem[Memory 记忆存储区]
        ReAct[ReAct 主体推理流]
        Reflexion[Reflexion 容错机/状态机]
        
        Plan --> StateMem
        ReAct <--> StateMem
        ReAct <--> Reflexion
    end
    subgraph Tools Cluster (tools/)
        TB_ArXiv[arXiv 全站工具集]
        TB_S2[Semantic Scholar 工具集]
        TB_CR[Crossref DOI 工具集]
        TB_PDF[PDF清洗工具]
        TB_IO[本地读写与笔记工具]
    end
    ReAct -.->|工具调度路由| Tools Cluster
    TB_IO -.->|正则截获:自动存档PDF| TB_ArXiv
    ReAct -->|FINISH信号触发| WriterAgent[Review 生成器]
```

---

## 2. 核心控制流详细设计 (`core/agent.py`)

### 2.1 主控类 (`AcademicAgent`)
- **工作区隔离机制**：执行 `run()` 初始化时，动态生成 `documents/{topic}_{timestamp}/` 独立沙箱目录，并内建 `papers/` 子文件夹用于存放所有的原始 PDF，避免不同代理运行造成的文件污染。
- **全局状态池**：内部维护 `self.memory`（对话记录历史栈）、`self.notes`（内部缓存的有效笔记数）、`self.error_streak`（连续错误计数器）。

### 2.2 推理生命周期 (Lifecycle)
1. **启动与规划 (`_plan`)**：调用大模型，要求强制生成 300 字以内的检索规划（包含：关键词发散、数据库选择组合、备选策略）。此计划强制插入 `self.memory` 第一个 System/User 节点后，作为整个执行周期的“灯塔”。
2. **ReAct 获取行动 (`_react_loop`)**：
   - 进入 `while not FINISH and step < MAX_STEPS:` 循环。
   - 装载所有 Tools 描述及其 `args_schema` 到 Prompt。
   - 命令 LLM 返回 JSON 字典结构：`{"thought": "...", "action": "...", "action_input": {...}}`。
3. **行动路由执行 (`_execute_tool`)**：利用 Python 反射找到对应函数类并执行，将反馈记作 `Observation`。
4. **综述综合撰写 (`_write_review`)**：一旦检索达到预期，循环退出。触发副 Agent——专职的论文写手模型，读取目录下的合并笔记文件，强制输出符合学术排版的 `final_review.md`。

---

## 3. 全局外部工具池详细设计 (`tools/` 全景)

外部工具是 Agent 接触物理世界的载体，全部继承自 `core.tools.BaseTool`，定义了严禁更改的统一规范接口 `execute(**kwargs)`。

### 3.1 arXiv 学术库体系 (`arxiv_tools.py`)
主要处理物理/计算机/数学等预印本获取。
- `arxiv_search`: 接收 `query` 和 `max_results`。针对 arXiv 严格的限流机制，内置了全局信号量，保证所有请求带有最低 **5s 延迟阻塞**防屏蔽。
- `arxiv_fetch`: 精确获取特定 arXiv ID 论文的完整元数据（作者、摘要、日期）。
- `arxiv_pdf_reader`: 在线抓取 arXiv PDF 并在内存中转码解析。
- `arxiv_download_pdf`: 提供将指定论文实体文件落盘至沙箱 `papers/` 文件夹的能力。

### 3.2 Semantic Scholar 高阶语义库体系 (`semantic_scholar_tools.py`)
用于获取包含丰富引用关系的综合文献。
- `semantic_scholar_search`: 对接 `/graph/v1/paper/search` 端点。设计中考虑到该 API 对未绑 Key 请求存在极高的 HTTP 429 报错率，实现了 **指数退避重试 (Exponential Backoff)** 策略（拦截429后等待逐步增加的时间，直至熔断）。
- `semantic_scholar_fetch`: 获取带引用计数（Citation Count）的论文条目。

### 3.3 Crossref DOI 档案工具 (`crossref_tools.py`)
兜底文献库，用于精确查找某些缺乏开源 PDF 档案但有准确引用序列的老旧或非开源文章。
- `crossref_search` 与 `crossref_fetch_doi`：支持通过 DOI 直接抽取元数据。

### 3.4 PDF解析清洗器 (`pdf_tools.py`)
- **PyMuPDF 引擎**：拦截 `arxiv_pdf_reader` 下载时的脏数据，自动剔除页眉页脚、图表乱码和异常换行符（Chunking），以大段纯净文本喂回大语言模型，避免多余 Token 损耗。

### 3.5 I/O 留存与隐藏拦截器 (`file_tools.py` 与 Action Hook)
- `append_note`: 提供将提炼出的研究事实（Findings）记录至 `research_notes.md` 的接口。
- **💡 隐藏质检拦截器 (Auto-Download PDF Trigger)**：针对大模型容易“遗忘”主动存储原文献的问题，系统特别设计了监听后门：在主控 `agent.py` 执行完 `append_note` 工具后，使用正则表达式 `re.search(r'\d{4}\.\d{4,5}', ...) ` 扫描笔记正文。若存在 arXiv 编号，**系统静默在后台触发 `arxiv_download_pdf`**，强行补齐产物列表。

---

## 4. 基础通信设施与修补层 (`llms/client.py`)

在对接 `eval_platform` Ragas 框架及本地直连时，国内 LLM 供应商存在接口校验严苛的问题，故引入**动态打桩 (Monkey Patching)**：

### 4.1 Langchain/Ragas 兼容性重写
- **问题**：Langchain/Ragas 评估时会将超长小数精度传入（如 `temperature: 1e-08`），并且携带额外字段（如 `name`），会导致智谱 GLM-4 抛出 `400 - 1210 参数非法` 彻底宕机。
- **解决方案**：在客户端初始化阶段，覆写 `openai.AsyncOpenAI.chat.completions.create` 级别的方法。
  1. **请求体清洗 (Sanitize Payload)**：拦截 `kwargs`，通过白名单映射，强制过滤 `name`、未授权的 `response_format` 等非法字段。
  2. **下限夹逼钳制**：通过 `if data.get("temperature", 0) < 0.01: data["temperature"] = 0.01` 截断极值。确保全平台底层通信稳固。

---

## 5. 记忆流与鲁棒反馈状态机 (`memory.py` & Reflexion)

### 5.1 响应解析自愈体系 (`utils/parser.py`)
- 使用强正则策略：即便大模型在回答时夹带说明式废话（如“好的，我将调用如下工具：```json {...} ```”），解析器使用 `r'\{.*\}'` 进行跨行提取，重组 Python 字典。若解析完全崩溃，抛出异常交由 L1 Reflexion。

### 5.2 错误分级反馈状态机 (Reflexion)
- **L1 级容错：格式轻微偏离**：当 JSON 提取异常或幻觉出不存在的 `action_name` 时，代码返回 `Observation: Action XXX not found, please strictly return valid JSON and Tool names.` 让模型当场重试。
- **L2 级容错：逻辑死锁迷失**：当模型因为某个偏僻关键词导致搜索反复无果，触发连续失败 3 次检测（`self.error_streak >= 3`），引擎强制注入反思提示：`系统警告：你已连续遭遇 3 次无效结果。必须更换搜索词或放弃该角度。`
- **L3 级品控：自主验收失败**：Agent 试图输出退出指令（FINISH）时，主控引擎拦截。若检查到 `self.notes < MIN_REQUIRED_NOTES`，拒绝退出，伪造一个 `Observation: 你还需要更多资料。` 强迫大模型继续工作。

---

## 6. 前后端交互通信设计 (`frontend/` & `web_app.py`)

为了将命令行内的封闭黑盒过程转化为可演示的监控大盘：
- **FastAPI 异步架构**：后端以 Fast API 启动挂载应用。
- **SSE 流式通讯接口** (`/api/stream`，Server-Sent Events)：内部大模型执行时利用 Python 生成器 `yield` 关键字，将 `Thought`、`Action`、`Observation` 以 JSON 日志流实时推送到前端 JS。
- **Web UI 隔离沙箱**：前端看板分为左侧“执行流历史板”（动态滚动）、右上“科研笔记沉淀区”、右下“参考资料库”。前端通过定期拉取接口异步更新生成的 Markdown 视图与文献表格框。
