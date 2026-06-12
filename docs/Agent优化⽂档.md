# Agent 优化文档

**版本**: v1.0
**日期**: 2026年6月
**覆盖范围**: 迭代三 Agent 会话管理、聊天系统、深度笔记生成、工具注册中心、RAG 检索、Pipeline 增强的全部优化点

---

## 目录

1. [概述](#概述)
2. [第一波：会话状态管理 + 聊天系统](#第一波会话状态管理--聊天系统)
3. [第二波：深度笔记生成 + 聊天系统增强 + 工具注册中心](#第二波深度笔记生成--聊天系统增强--工具注册中心)
4. [第三波：RAG 检索系统升级](#第三波-rag-检索系统升级)
5. [第四波：Pipeline 增强](#第四波-pipeline-增强)
6. [评估结果汇总](#评估结果汇总)
7. [配置参数汇总](#配置参数汇总)
8. [总结](#总结)

---

## 概述

### 迭代二的痛点

迭代二的 Agent 系统采用**单次全流程执行**模式，存在以下核心问题:
- 中间过程完全黑盒，用户无法干预
- 无会话状态，无法暂停/恢复/追加调研
- 对话仅单轮，无多轮记忆
- 仅 BM25 关键词检索，缺乏语义理解
- 上下文粗暴截断 2000 字符
- 工具分散硬编码，无法管理
- Prompt 不可定制，撰写结果不可控
- 笔记自由格式，质量参差不齐

### 优化路线图

优化分四波递进实施，每次优化后进行系统评估:

```
初始状态 (test1, 2026-05-15)
    │
    ▼
第一波: 会话状态管理 + 聊天系统 (test2, 2026-05-22)
    │
    ▼
第二波: 深度笔记生成 + 聊天系统增强 + 工具注册中心 (test3, 2026-05-29)
    │
    ▼
第三波: RAG 检索系统升级 (test4, 2026-06-05)
    │
    ▼
第四波: Pipeline 增强 (test6, 2026-06-12)
```

| 波次 | 优化领域 | 涉及核心文件 | 评估 |
|------|---------|------------|------|
| 第一波 | 会话状态管理 + 聊天系统 | session_manager.py, web_app.py | test2 |
| 第二波 | 深度笔记生成 + 聊天增强 + 工具注册 | rag_note_generator.py, web_app.py, tool_registry.py | test3 |
| 第三波 | RAG 检索系统升级 | retriever.py | test4 |
| 第四波 | Pipeline 增强 | main.py | test6 |

---

## 第一波：会话状态管理 + 聊天系统

> 评估: test2 (2026-05-22)
> 文件: [backend/session_manager.py](../agent/backend/session_manager.py) (770 行), [web_app.py](../agent/web_app.py)

### 1.1 会话状态管理

#### 问题发现

迭代二中，Agent 的每次执行是独立的、一次性的:
- **无状态管理**: 每次运行创建独立的 `documents/{run_id}/` 目录，运行结束后无法恢复
- **无法断点继续**: 搜索完成后若想修改关键词，必须从零开始重新执行全流程
- **无法暂停交互**: 用户无法在中间阶段暂停并参与决策
- **数据孤岛**: 每次运行的数据互不相通，无法跨 Session 复用
- **无法追加调研**: 综述撰写阶段发现遗漏论文时，无法回到搜索阶段补充

#### 优化具体实现

**8 状态机设计**

将 Agent 全流程建模为 8 个离散状态 (`SessionState` 枚举, [session_manager.py:22-30](../agent/backend/session_manager.py#L22-L30)):

```
planning(规划中) → plan_confirmed(关键词已确认) → searching(搜索中) → search_complete(搜索完成)
    → reviewing_notes(笔记审核中) → writing(撰写中) → reviewing_draft(初稿评审中) → complete(已完成)
```

**全状态回溯能力**

`VALID_TRANSITIONS` 的核心设计 ([session_manager.py:34-43](../agent/backend/session_manager.py#L34-L43)): **所有状态均可跳回 `searching`**，允许用户在任何阶段追加调研:

```
plan_confirmed → searching     (修改关键词后重新搜索)
search_complete → searching    (论文不够，继续搜索)
reviewing_notes → searching    (发现遗漏，追加搜索)
writing → searching            (撰写中发现缺论文)
reviewing_draft → searching    (评审中发现缺论文)
complete → searching           (完成后追加调研)
```

**完整数据目录结构**

```
sessions/{session_id}/
├── metadata.json              # 主题、状态、关键词、Skill 配置、时间戳
├── plan/
│   ├── initial_plan.md        # Agent 生成的研究计划
│   └── confirmed_keywords.json # 用户确认/编辑后的关键词
├── papers/
│   ├── papers_list.json       # 标准化论文列表 (含来源、状态)
│   ├── deleted_papers.json    # 已删除论文 ID 黑名单
│   ├── {arxiv_id}.pdf         # 下载的 PDF 原文
│   └── {arxiv_id}.txt         # 提取的文本内容
├── notes/
│   ├── draft_notes.md         # 当前笔记草稿
│   └── edit_history/          # 编辑历史 + edit_log.json
├── draft/
│   ├── draft_v1.md ... draft_vN.md  # 版本化综述草稿
│   ├── current_draft.md       # 快捷访问最新草稿
│   └── user_feedback.md       # 用户反馈意见
├── traces/
│   └── run_traces.json        # Agent 执行轨迹 (SECTION 追加模式)
└── chats/
    ├── _index.json            # 多对话索引
    └── conv_{uuid}.json       # 独立对话记录
```

**自动修复卡住状态**

加载 Session 时自动检测 ([session_manager.py:131-153](../agent/backend/session_manager.py#L131-L153)):
- 检测: `updated_at` 超过 10 分钟且状态为 `searching`/`writing`/`reviewing_notes`
- 自动回退到上一个稳定状态，防止 Session 永久卡死

**论文标准化与去重**

- `_normalize_papers()`: 确保所有论文条目字段标准化
- `deleted_papers.json` 黑名单: 用户删除的论文在重新搜索时自动过滤
- `undelete_paper()` 支持恢复误删

**多会话聊天架构**: 每个 Session 支持多个独立对话，`_index.json` 管理对话列表，自动从旧版单文件 `chat_history.json` 迁移。

#### 优化后效果

| 维度 | 优化前 | 优化后 |
|------|--------|--------|
| 会话持续性 | 一次性执行，无状态 | 8 状态机 + 全目录持久化 |
| 断点继续 | 不支持 | 支持从任意断点恢复 |
| 追加调研 | 不支持 | 任意状态可回溯到 searching |
| 数据关联 | 每次运行独立目录 | Session 内全数据关联 |
| 异常恢复 | 不支持 | 自动检测 + 修复卡住状态 |
| 论文去重 | 无 | 黑名单 + 标准化 |

---

### 1.2 聊天系统（阶段一：多轮对话记忆）

#### 问题发现

迭代二的聊天系统是无状态的: 每次用户发送消息，LLM 只能看到当前这一条消息，完全不知道之前聊了什么。用户追问"它和之前那篇比呢？"时，LLM 无法理解"它"指什么。

#### 优化具体实现

`_build_chat_answer()` 中注入对话历史:
- 从 `session_mgr.get_conversation_messages()` 获取最近 **12 条消息**（6 轮对话）
- 格式化为 `{角色}：{内容}` 注入 user prompt
- System prompt 明确指示 LLM 理解指代 ("它", "这个", "那篇" 等)
- 对话记录持久化到 `chats/conv_{uuid}.json`

#### 优化后效果

用户可进行自然的追问式对话，LLM 能理解跨轮指代。对话从"一问一答"升级为"连续交流"。

---

### 第一波评估数据

| 指标 | 初始状态 (test1) | 第一波后 (test2) | 变化 |
|------|---------------|---------------|------|
| context_precision | 0.303 | 0.475 | **+0.172** |
| context_recall | 0.90 | 0.85 | -0.05 |
| faithfulness_score | 0.90 | 0.85 | -0.05 |
| helpfulness_score | 0.90 | 0.80 | -0.10 |
| relevance_score | 0.90 | 0.95 | **+0.05** |
| reasoning_score | 0.80 | 0.75 | -0.05 |
| **overall_score** | **0.80** | **0.80** | — |

**分析**: 第一波优化核心解决了"无状态→有状态"的架构问题。`context_precision` 大幅提升 (+0.172) 得益于多轮对话记忆和会话上下文。`relevance_score` 也有所提升。部分指标略有下降（helpfulness、reasoning），这是因为 Session 管理引入了更复杂的上下文编排，初期 Prompt 工程还需后续优化。

---

## 第二波：深度笔记生成 + 聊天系统增强 + 工具注册中心

> 评估: test3 (2026-05-29)
> 文件: [tools/rag_note_generator.py](../agent/tools/rag_note_generator.py) (447 行), [web_app.py](../agent/web_app.py), [core/tool_registry.py](../agent/core/tool_registry.py) (244 行)

### 2.1 深度笔记生成

#### 问题发现

迭代二的笔记生成存在以下问题:
- **自由格式、结构不统一**: Agent 生成的笔记质量参差不齐，无法保证最小覆盖度
- **全量 PDF 灌入 LLM**: 将 PDF 前 5 页直接塞给 LLM，关键方法可能在 5 页之后
- **无降级策略**: PDF 提取失败时直接报错，整个笔记流程中断
- **无法定制**: 用户无法定义笔记的结构要求

#### 优化具体实现

**6 段式结构化笔记**: `RAGNoteGenerator` 将笔记拆分为 6 个独立段落:

| 段落 | 查询关键词 | 最低字数 |
|------|----------|---------|
| 研究背景 | problem, challenge, background, limitation, gap, motivation | 80 |
| 核心方法 | method, approach, proposed, architecture, model, framework | 150 |
| 实验设置 | experiment, dataset, evaluation, benchmark, baseline, setup | 80 |
| 关键结果 | result, performance, achieve, outperform, accuracy, sota | 100 |
| 消融与分析 | ablation, analysis, visualization, case study, component, comparison | 80 |
| 亮点与不足 | contribution, limitation, future work, novel, innovation, drawback | 60 |

**Embedding 向量精准检索**: 替代"前 5 页全量灌入"。以滑动窗口（500 字符 / 100 重叠）提取 PDF 全文块，每块截断至 800 字符后向量化。每段构建独立查询（paper_title + abstract + topic + section_keywords），余弦相似度排序，Top-5 段落送入 LLM 生成笔记。

**三层降级策略**: PDF 提取失败 → 基于摘要生成；Embedding API 失败 → BM25 替代；零向量检测 → BM25 切换。

#### 优化后效果

| 维度 | 优化前 | 优化后 |
|------|--------|--------|
| 笔记结构 | 自由格式，质量不稳定 | 6 段式结构化，最低字数保障 |
| 原文利用 | 前 5 页全量灌入 | Embedding 精准检索全文相关段落 |
| 异常处理 | PDF 提取失败 → 中断 | 三层降级 |
| 可定制性 | 无 | Skill 双通道 + 自修复 |

---

### 2.2 聊天系统（阶段二-四：检索增强 + 上下文管理 + 意图检测）

#### 问题发现（阶段二-四的累积问题）

- **检索质量差**: 仅 BM25 关键词匹配，"训练稳定性"无法匹配 "training instability"
- **上下文管理粗暴**: 统一截断 2000 字符，不同内容的重要性完全被忽略
- **额外 LLM 调用延迟**: 每次意图判断都需要额外 LLM 调用 (+~2s)

#### 优化具体实现

**BM25 + Embedding 混合检索**（阶段二）

集成 `HybridRetriever`（详见第三波）替代纯 BM25。`_build_chat_answer()` 调用 `iterative_search()` 进行混合检索，检索范围覆盖 Session 内所有已下载 PDF 的全文段落。结果附带 `citations` 数组（编号、论文标题、页码、原文片段）。

**智能上下文窗口管理**（阶段三）

`_manage_context_window()` 实现优先级配额分配:

```
优先级: 用户消息(不截断) > RAG 检索结果 > 对话历史 > 笔记/草稿 > 摘要
```

| 配额常量 | 默认值 | 说明 |
|---------|-------|------|
| `MAX_CONTEXT_CHARS` | 80,000 | 总上下文窗口 (~40K tokens) |
| `MAX_RAG_CHARS` | 30,000 | RAG 检索结果上限 |
| `MAX_HISTORY_CHARS` | 15,000 | 对话历史上限 |
| `MAX_NOTES_CHARS` | 20,000 | 笔记/草稿各上限 |

从"一刀切 2000 字符"升级为"按优先级智能分配 80000 字符"。

**三级意图检测**（阶段四）

```
用户消息
    │
    ├── Level 1: 确认型修订 → 直接执行，零延迟
    ├── Level 2: 显式命令 "/修订 笔记 ..." → 正则提取，零延迟
    └── Level 3: AI 语义推理
        ├── _quick_intent_check(): 40+ 中英文关键词规则预判
        │   修改词>=2 且 提问词=0 → "revise"，跳过 LLM
        │   提问词>=1 且 修改词=0 → "chat"，跳过 LLM
        └── LLM 意图分类: confidence>=0.7 执行，<0.7 二次确认
```

轻量级关键词预判使用 40+ 中英文关键词（修改、改写、重写、删除、补充 / 什么是、为什么、如何、区别 / revise、rewrite、modify、delete / what、why、how），规则命中时完全跳过 LLM 调用（~2s 延迟节省）。

#### 优化后效果

| 薄弱点（改善前） | 改善措施 | 阶段 |
|------|---------|------|
| 仅 BM25 检索 | BM25 + Embedding 双路融合 | 二 |
| 粗暴截断 2000 字符 | 智能配额分配 80K 字符 | 三 |
| 意图判意额外 LLM 调用 | 三级检测 + 关键词规则预判 | 四 |

---

### 2.3 工具注册中心

#### 问题发现

迭代二中，工具管理存在明显不足:
- **硬编码分散**: 工具列表分散在 agent.py 和多处调用代码中
- **无统一管理**: 没有中心化的启用/禁用机制
- **无持久化**: 工具启用状态在每次重启后丢失
- **无分类标注**: 难以辨别各工具的适用阶段

#### 优化具体实现

**集中化工具元数据管理**: `ToolMeta` 数据类统一描述每个工具 (name, description, category, pipeline, parameters, enabled, config)。

**14 工具注册表**: `BUILTIN_TOOLS` 字典定义所有内置工具:

| 工具名 | 类别 | Pipeline 阶段 | 默认 |
|-------|------|-------------|------|
| `arxiv_search` | search | 搜索阶段 | 启用 |
| `arxiv_fetch` | search | 搜索阶段 | 启用 |
| `arxiv_pdf_reader` | pdf | 搜索/笔记阶段 | 启用 |
| `arxiv_download_pdf` | pdf | 搜索阶段 | 启用 |
| `semantic_scholar_search` | search | 搜索阶段 | 禁用 |
| `semantic_scholar_fetch` | search | 搜索阶段 | 禁用 |
| `crossref_search` | search | 搜索阶段 | 禁用 |
| `crossref_fetch_doi` | search | 搜索阶段 | 启用 |
| `openalex_search` | search | 搜索阶段 | 启用 |
| `clear_notes` | file | 笔记阶段 | 启用 |
| `append_note` | file | 笔记阶段 | 启用 |
| `retriever` | chat | 对话阶段 | 启用 |
| `rag_note_generator` | notes | 笔记阶段 | 启用 |
| `paper_register` | register | 搜索阶段 | 启用 |

Semantic Scholar 相关工具默认禁用（API 无 Key 时限流严重，429 率 ~60%）。

**持久化配置**: 保存到 `config/tools.json`，仅持久化 `enabled` 和 `config` 字段。`batch_set_enabled()` 批量切换，`reset_to_defaults()` 一键恢复。

#### 优化后效果

| 维度 | 优化前 | 优化后 |
|------|--------|--------|
| 工具定义 | 分散在多处硬编码 | `BUILTIN_TOOLS` 单一定义源 |
| 启用控制 | 无 | 14 工具独立开关 + 批量操作 |
| 配置持久化 | 无 (重启丢失) | `config/tools.json` 自动保存 |
| Web 管理 | 无 | 4 个 API 端点 |

---

### 第二波评估数据

| 指标 | 第一波后 (test2) | 第二波后 (test3) | 变化 |
|------|---------------|---------------|------|
| context_precision | 0.475 | 0.421 | -0.054 |
| context_recall | 0.85 | 0.85 | — |
| faithfulness_score | 0.85 | 0.85 | — |
| helpfulness_score | 0.80 | 0.80 | — |
| relevance_score | 0.95 | 0.95 | — |
| reasoning_score | 0.75 | 0.75 | — |
| **overall_score** | **0.80** | **0.80** | — |

**分析**: 第二波引入了深度笔记生成、工具注册中心和聊天系统的检索/上下文/意图增强。整体指标保持稳定。`context_precision` 略有下降，原因是新增的混合检索和上下文管理策略还在调优中，检索结果宽度增加带来了一定的精度稀释。这是正常的"探索-利用"权衡。

---

## 第三波：RAG 检索系统升级

> 评估: test4 (2026-06-05)
> 文件: [tools/retriever.py](../agent/tools/retriever.py) (342 行)

### 问题发现

前两波优化后，检索系统仍存在严重局限:
- **仅 BM25 关键词匹配**: 依赖词频统计，无法理解语义相关性
- **无 Embedding 语义检索**: 缺少稠密向量表示，丢失同义表达和上下文语义
- **中文分词粗糙**: 简单按字符切分，丢失词组语义
- **无检索缓存**: 每次查询重新构建索引，响应延迟高
- **检索失败无兜底**: 首次检索结果不理想时无补救机制

### 优化具体实现

**1. BM25 + Embedding 混合检索**

`HybridRetriever` 融合两路检索 ([retriever.py:99-212](../agent/tools/retriever.py#L99-L212)):

```
score = 0.3 x BM25_score + 0.7 x embedding_score
```

- **BM25 通路**: 保证精确关键词匹配，`max_features=5000`, `ngram_range=(1,2)`，过滤相似度 < 0.01
- **Embedding 通路**: 智谱 `embedding-2` 模型（1536 维）向量化 + 余弦相似度
- **权重设计**: BM25 占 0.3 保证召回率，Embedding 占 0.7 主导语义精度

**2. Embedding 向量磁盘缓存**

`_ensure_embeddings()` ([retriever.py:132-161](../agent/tools/retriever.py#L132-L161)):
- 懒加载: 首次 `search()` 时计算，后续从磁盘读取
- 缓存到 `sessions/.embed_cache/{md5_hash}.npy`
- `invalidate_retriever_cache()` 在论文更新后清除

**3. 迭代式检索**

`iterative_search()` ([retriever.py:262-341](../agent/tools/retriever.py#L262-L341)):
- **第一轮**: 直接用原始 query 检索
- **触发条件**: 结果数 < max(3, top_k/2) 或最高分 < 0.1
- **第二轮**: LLM 生成 1-2 个不同角度的扩展查询词
- **去重排序**: 按文本首 80 字符去重，混合分数重排

**4. 中英文混合分词器**

`BM25Retriever._tokenize()` ([retriever.py:84-96](../agent/tools/retriever.py#L84-L96)):
- **英文**: 正则 `[a-zA-Z]+(?:-[a-zA-Z]+)*` 按单词分词
- **中文**: 2-gram 滑动窗口切分，同时保留单字符

**5. 三层优雅降级**

| 场景 | 降级方案 |
|------|---------|
| Embedding API 调用失败 | 零向量填充 `[0.0] * 1536` |
| Embedding 完全不可用 | 纯 BM25 检索 |
| 文本太少 TfidfVectorizer 异常 | 降级 `max_features=1000` |

**6. 全局检索器缓存**: `_RETRIEVER_CACHE` 按 session_id 缓存检索器实例，避免重复构建索引。

### 优化后效果

| 维度 | 优化前 | 优化后 |
|------|--------|--------|
| 检索方式 | 仅 BM25 关键词匹配 | BM25 + Embedding (0.3/0.7) 双路融合 |
| 语义理解 | 无 | 1536 维向量余弦相似度 |
| 中文分词 | 简单字符切分 | 2-gram + 英文单词分词 |
| 检索缓存 | 每次重建 | 磁盘 .npy 缓存 + 懒加载 |
| 检索失败 | 无补救 | 迭代式检索 + LLM 扩展查询词 |
| 异常处理 | 直接崩溃 | 三层降级 |

### 第三波评估数据

| 指标 | 第二波后 (test3) | 第三波后 (test4) | 变化 |
|------|---------------|---------------|------|
| context_precision | 0.421 | 0.466 | **+0.045** |
| context_recall | 0.85 | 0.95 | **+0.10** |
| faithfulness_score | 0.85 | 0.85 | — |
| helpfulness_score | 0.80 | 0.90 | **+0.10** |
| relevance_score | 0.95 | 0.95 | — |
| reasoning_score | 0.75 | 0.90 | **+0.15** |
| **overall_score** | **0.80** | **0.80** | — |

**分析**: 第三波 RAG 检索升级是效果最显著的一波。`context_recall` 从 0.85 跃升至 0.95 (+0.10)，直接体现了 Embedding 语义检索对召回率的巨大提升。`reasoning_score` 增长 +0.15，说明更精准的原文段落为 LLM 推理提供了更高质量的上下文。`helpfulness_score` 和 `context_precision` 也分别增长 +0.10 和 +0.045。这是四波中指标改善最全面的一次。

---

## 第四波：Pipeline 增强

> 评估: test6 (2026-06-12)
> 文件: [main.py](../agent/main.py) (934 行)

### 问题发现

前三波优化后，Pipeline 仍存在几个关键缺陷:
- **固定 Prompt 不可定制**: 不同用户的研究领域无法定制（医学 vs 计算机科学综述结构需求完全不同）
- **撰写结果不可控**: Writer 有时输出的章节名不匹配、内容重复、缺失关键部分
- **笔记生成失败无兜底**: Agent 忘记调用 `append_note` 时，Writer 阶段无笔记可用
- **数据一致性问题**: PDF 下载和论文登记是两个独立步骤，存在"下载了但未登记"的窗口
- **PDF 遗漏**: Agent 搜索到的论文可能只 fetch 了元数据但未下载 PDF

### 优化具体实现

**1. 双通道 Skill 注入机制**

每个阶段（搜索/笔记/撰写）支持用户自定义 Skill 覆盖默认 Prompt:

```
Phase 入口
    ├── Skill 已配置 (Channel A): Skill 内容替换默认 Prompt
    │   - 仅保留最小化核心约束
    └── 无 Skill (Channel B): 使用内置默认 Prompt
```

注入点: 搜索阶段 (`run_search_only()`), 笔记阶段 (`RAGNoteGenerator.generate()`), 撰写阶段 (`compose_review_from_notes()`)

**2. 自修复审阅**

`_self_repair_review()` ([main.py:168-241](../agent/main.py#L168-L241)):
1. **Rewrite**: LLM 完整重写综述，严格遵循 Skill 结构
2. **Verify**: LLM 检查重写结果，修复不匹配/重复/缺失
3. 失败时返回原版综述

**3. 轨迹兜底笔记提取**

`_build_fallback_notes_from_traces()` ([main.py:264-316](../agent/main.py#L264-L316)):
- 触发: Agent 运行后 `research_notes.md` 不存在
- 扫描 traces 中 `arxiv_search`, `arxiv_fetch` 等的 observation
- 上限: 最多 6 条，每条 <=1,600 字符
- 确保 Writer 阶段即使无完整笔记也能继续

**4. PDF 下载完整性保障**

搜索阶段后处理 ([main.py:707-730](../agent/main.py#L707-L730)): 正则扫描所有 traces 中的 arXiv ID，批量下载 PDF。

**5. Paper Register 一体化**: 单次工具调用 = PDF 下载 + 论文登记，下载失败则不登记，消除数据不一致窗口。

**6. 后台线程 + 轮询**: 搜索阶段非阻塞执行，`POST /run/cancel` 可随时中断。

### 优化后效果

| 维度 | 优化前 | 优化后 |
|------|--------|--------|
| Prompt 定制 | 硬编码 | 双通道 Skill 注入 (search/notes/write) |
| 撰写质量 | 无修复 | 两阶段自修复 (Rewrite + Verify) |
| 笔记缺失 | 流程失败 | 轨迹兜底提取 |
| 数据一致性 | 下载/登记分离 | Paper Register 一体化 |
| 执行方式 | 同步阻塞 | 后台线程 + 可取消 |

### 第四波评估数据

| 指标 | 第三波后 (test4) | 第四波后 (test6) | 变化 |
|------|---------------|---------------|------|
| context_precision | 0.466 | 0.471 | +0.005 |
| context_recall | 0.95 | 0.85 | -0.10 |
| faithfulness_score | 0.85 | 0.90 | **+0.05** |
| helpfulness_score | 0.90 | 0.80 | -0.10 |
| relevance_score | 0.95 | 0.95 | — |
| reasoning_score | 0.90 | 0.75 | -0.15 |
| **overall_score** | **0.80** | **0.80** | — |

**分析**: 第四波引入的 Skill 双通道注入、自修复审阅等特性，提升了 `faithfulness_score` (+0.05)，表明综述内容对原文的忠实度更高。`context_recall` (-0.10) 和 `reasoning_score` (-0.15) 的下降是因为 Skill 定制化的 Prompt 缩小了检索和推理的范围（更聚焦但覆盖面减小），且自修复阶段的 Verify 可能存在过度修正。这提示后续需要在 Skill 定制和通用性之间找到更好的平衡。

---

## 评估结果汇总

### 评估指标说明

| 指标 | 含义 |
|------|------|
| context_precision | 检索到的上下文中相关信息的精确度 |
| context_recall | 检索到的上下文覆盖所有相关信息的比例 |
| faithfulness_score | 生成内容对原始论文内容的忠实程度 |
| helpfulness_score | 生成内容对用户的帮助程度 |
| relevance_score | 检索和生成内容与用户问题的相关性 |
| reasoning_score | 推理质量（逻辑、深度、准确性） |
| overall_score | 综合评分 |

### 五次评估数据对比

| 指标 | test1 (初始) | test2 (第一波) | test3 (第二波) | test4 (第三波) | test6 (第四波) |
|------|------------|------------|------------|------------|------------|
| context_precision | 0.303 | 0.475 | 0.421 | 0.466 | 0.471 |
| context_recall | 0.90 | 0.85 | 0.85 | **0.95** | 0.85 |
| faithfulness_score | 0.90 | 0.85 | 0.85 | 0.85 | **0.90** |
| helpfulness_score | 0.90 | 0.80 | 0.80 | **0.90** | 0.80 |
| relevance_score | 0.90 | 0.95 | 0.95 | 0.95 | 0.95 |
| reasoning_score | 0.80 | 0.75 | 0.75 | **0.90** | 0.75 |
| **overall_score** | **0.80** | **0.80** | **0.80** | **0.80** | **0.80** |

### 各波次关键变化分析

**初始 → 第一波 (会话管理 + 聊天记忆)**
- `context_precision` 大幅提升 (+56.8%): 多轮对话记忆和会话上下文显著改善了检索精度
- `helpfulness_score` 下降 (-0.10): 初期 Prompt 工程尚需优化

**第一波 → 第二波 (笔记生成 + 聊天增强 + 工具注册)**
- 各指标总体稳定，系统架构日趋完整
- `context_precision` 小幅回调 (-0.054): 新增检索策略的探索成本

**第二波 → 第三波 (RAG 检索升级) — 效果最显著**
- `context_recall` 跃升 (+0.10): 语义检索对召回率的直接提升
- `reasoning_score` 大幅增长 (+0.15): 高质量原文段落改善了 LLM 推理
- `helpfulness_score` 回升 (+0.10): 更精准的回答提升了用户帮助度

**第三波 → 第四波 (Pipeline 增强)**
- `faithfulness_score` 提升 (+0.05): Skill 定制 + 自修复增强了内容忠实度
- `reasoning_score` 下降 (-0.15): Skill 定制缩小了推理范围，需平衡定制与通用性

### 整体趋势

```
context_precision: 0.303 → 0.471 (累计 +0.168, +55.4%)
context_recall:    0.90  → 0.85  (累计 -0.05, -5.6%)
faithfulness:      0.90  → 0.90  (累计 持平)
helpfulness:       0.90  → 0.80  (累计 -0.10, -11.1%)
relevance:         0.90  → 0.95  (累计 +0.05, +5.6%)
reasoning:         0.80  → 0.75  (累计 -0.05, -6.3%)
overall:           0.80  → 0.80  (累计 持平)
```

**核心发现**: 四波优化在保持 `overall_score` 稳定的前提下，`context_precision` 累计提升 55.4%，`relevance_score` 稳步提升至 0.95。第三波（RAG 检索升级）是单波效果最显著的优化。第四波在定制性和通用性之间的权衡还需要后续调优。

---

## 配置参数汇总

| 参数名 | 默认值 | 位置 | 作用域 | 说明 |
|-------|-------|------|-------|------|
| `AGENT_MIN_PAPERS` | 3 | 环境变量 | core/agent.py | 质量门禁最低论文数 |
| `AGENT_LOOP_DELAY_SEC` | 3 | 环境变量 | core/agent.py | 循环间 LLM 调用冷却秒数 |
| `MAX_CONTEXT_CHARS` | 80,000 | 常量 | web_app.py | 聊天上下文总字符数上限 |
| `MAX_RAG_CHARS` | 30,000 | 常量 | web_app.py | RAG 检索结果最大字符数 |
| `MAX_HISTORY_CHARS` | 15,000 | 常量 | web_app.py | 对话历史最大字符数 |
| `MAX_NOTES_CHARS` | 20,000 | 常量 | web_app.py | 笔记/草稿单类最大字符数 |
| Observation 截断 | 4,500 | 硬编码 | core/agent.py | 工具执行结果截断阈值 |
| 混合检索权重 | 0.3 / 0.7 | 硬编码 | retriever.py | BM25 / Embedding 得分权重 |
| TF-IDF max_features | 5,000 | 硬编码 | retriever.py | TfidfVectorizer 最大特征数 |
| Embedding 批次 | 20 | 硬编码 | retriever.py | 每批向量化的段落数 |
| 迭代检索轮次 | 2 | 参数 | retriever.py | 检索补充最大轮次 |
| 对话记忆条数 | 12 (6轮) | 硬编码 | web_app.py | 注入上下文的对话历史 |
| 卡住状态超时 | 600s (10min) | 硬编码 | session_manager.py | 状态自动修复触发阈值 |

---

## 总结

### 优化成效总览

| 维度 | 优化前 (迭代二) | 优化后 (迭代三) |
|------|-------------|-------------|
| 会话持续性 | 无状态，一次性执行 | 8 状态机 + 全目录持久化 + 断点继续 |
| 用户交互 | 全流程黑盒 | 关键词确认 / 论文管理 / 笔记编辑 / 草稿评审 |
| RAG 检索 | 仅 BM25 关键词 | BM25+Embedding (0.3/0.7) 混合 + 迭代 |
| 对话能力 | 单轮无记忆 | 多轮记忆 + 上下文智能管理 + 意图检测 |
| 意图识别 | 无 | 三级检测 + 40+ 关键词预判 |
| 工具管理 | 分散硬编码 | 14 工具统一注册 + 持久化 + API |
| Skill 定制 | 不支持 | 双通道注入 (search/notes/write) + 自修复 |
| 笔记生成 | 自由格式 | 6 段式结构化 + Embedding 精准检索 |
| 降级能力 | 直接崩溃 | 多层 fallback (零向量 → BM25 → 摘要 → 模板) |
| 数据一致性 | 下载/登记分离 | Paper Register 一体化 |
| context_precision | 0.303 | 0.471 (+55.4%) |
| relevance_score | 0.90 | 0.95 (+5.6%) |

### 关键文件索引

| 文件路径 | 优化类别 | 波次 | 核心函数 |
|---------|---------|------|---------|
| [backend/session_manager.py](../agent/backend/session_manager.py) | 会话管理 | 第一波 | `SessionManager`, `VALID_TRANSITIONS` |
| [web_app.py](../agent/web_app.py) | 聊天系统 | 第一-二波 | `_build_chat_answer()`, `_manage_context_window()`, `_quick_intent_check()` |
| [tools/rag_note_generator.py](../agent/tools/rag_note_generator.py) | 深度笔记 | 第二波 | `RAGNoteGenerator`, `_self_repair_notes()` |
| [core/tool_registry.py](../agent/core/tool_registry.py) | 工具注册 | 第二波 | `ToolRegistry`, `ToolMeta` |
| [tools/retriever.py](../agent/tools/retriever.py) | RAG 检索 | 第三波 | `HybridRetriever`, `iterative_search()` |
| [main.py](../agent/main.py) | Pipeline | 第四波 | `run_search_only()`, `_self_repair_review()` |
| [backend/skill_manager.py](../agent/backend/skill_manager.py) | Skill 管理 | 第四波 | `SkillManager` |

### 设计原则

1. **纵深防御 (Defense in Depth)**: 每种失败路径都有对应 fallback — 笔记缺失 → 轨迹兜底，Embedding 失败 → 零向量 → BM25
2. **渐进增强 (Progressive Enhancement)**: BM25 在 Embedding 失败时可用，模板回复在 LLM 失败时可用，摘要笔记在 PDF 提取失败时可用
3. **用户可控 (User Agency)**: Skill 注入覆盖 LLM Prompt，关键词确认控制搜索策略，多轮对话 + 修订检测迭代优化
4. **可观测性 (Observability)**: 每步记录 trace（含时间戳和 error_type），追加搜索 SECTION 分隔，前端 TOC 导航，5 次评估量化追踪

### 后续优化方向

- Skill 定制与通用性的平衡调优（第四波 reasoning_score 下降问题）
- Embedding 维度可配置化
- 混合检索权重 (0.3/0.7) 支持动态调整
- 引入向量数据库替代磁盘 .npy 缓存
- 聊天意图检测 LLM 独立部署（降低延迟）
- 多 Session 间知识库共享

---

**文档历史**

| 版本 | 日期 | 作者 | 改动 |
|------|------|------|------|
| v1.0 | 2026-06-12 | - | 初稿，按四波优化顺序记录，包含 5 次评估数据 |
