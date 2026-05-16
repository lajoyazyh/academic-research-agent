# Academic Agent API 接口文档

本文档为评估平台（Eval Platform）及其他前端调用方提供 Academic Agent 的接口调用指南。可以基于这些 HTTP API 通过异步调用启动 Agent 并轮询状态/结果，也可以同步获取。

服务默认运行在 `http://127.0.0.1:8000`。

---

## 1. 基础信息接口

### 1.1 健康检查 (Health Check)
用于检测服务是否正常运行。

- **URL**: `/api/health`
- **Method**: `GET`
- **Response**:
```json
{
  "status": "ok"
}
```

---

## 2. Agent 运行接口（核心）

由于 Agent 调研过程可能长达数分钟，推荐使用**异步调用**方式（`/api/run/start` + 轮询 `/api/run/{run_id}`）。如果你需要阻塞等待结果，也可以使用同步接口。

### 2.1 异步启动 Agent (Start Run)
发起一个异步的文献调研任务，立刻返回一个 `run_id`，不阻塞。

- **URL**: `/api/run/start`
- **Method**: `POST`
- **Headers**: `Content-Type: application/json`
- **Request Body**:
```json
{
  "topic": "你想查询的学术主题，例如：大语言模型 Agent 内存机制",
  "max_loops": 20
}
```
*参数说明*：
- `topic` (string): 搜索话题
- `max_loops` (int): 允许 Agent 进行大模型思考和工具调用的最大循环轮数（推荐默认 20，取值范围 1~60）。

- **Response**:
```json
{
  "run_id": "8fb7c86a123b..."
}
```

### 2.2 查询异步任务状态 (Get Run Status)
通过 `run_id` 轮询查询任务的实时进度、当前思考节点及最终结果。

- **URL**: `/api/run/{run_id}`
- **Method**: `GET`
- **Response**:
```json
{
  "run_id": "8fb7c86a123b...",
  "topic": "大语言模型 Agent 内存机制",
  "status": "running", // 可能的值: "running", "done", "error"
  "phase": "researcher", // 当前所处的阶段，例如 "queued", "researcher", "done"
  "error": "", // 失败时的错误信息
  "researcher_result": "...", // 调研过程保存的原始笔记 markdown 内容（任务完成后有值）
  "writer_result": "...", // 最终输出的文献综述 markdown 内容（任务完成后有值）
  "output_file": "/path/to/最终综述文件.md", 
  "traces": [
    // 一个长数组，记录大模型每次循环的调用轨迹和内部思考
    {
      "step": 1,
      "thought": "我需要先调用 arxiv_search 工具...",
      "tool_name": "arxiv_search",
      "tool_input": "...",
      "tool_result": "..."
    }
  ]
}
```
*特别说明*：`traces` 字段极大地便利了评估平台进行**运行数据评估**，它可以完整重现大模型的每一步推理与工具调用细节。

### 2.3 同步运行 Agent (Sync Run)
【警告】：该接口会一直阻塞，直到整个调研与长文本生成结束（通常需要几十秒到几分钟不等），可能触发前端网络超时，一般推荐用于脚本批量测试。

- **URL**: `/api/run`
- **Method**: `POST`
- **Request Body**: (同 `/api/run/start`)
- **Response**: 等价于状态变为 "done" 后的 `Get Run Status` 大部分字段。
```json
{
  "topic": "大语言模型 Agent 内存机制",
  "researcher_result": "...",
  "writer_result": "...",
  "traces": [...],
  "output_file": "..."
}
```

---

## 3. 历史记录与产出文件接口

系统会将所有的产出（笔记、综述、下载的 PDF 等）保存在本地的 `documents` 目录下。这些接口用于访问历史结果。

### 3.1 获取所有历史运行记录列表
- **URL**: `/api/agent/history`
- **Method**: `GET`
- **Response**:
```json
[
  {
    "filename": "大语言模型_20260501_123456", 
    "size": 10245 // 最终综述或笔记的文件大小
  },
  {
    "filename": "图神经网络综述_20260501_100000",
    "size": 8942
  }
]
```

### 3.2 获取某次历史记录的详细内容
- **URL**: `/api/agent/history/{filename}`
- **Method**: `GET`
- **Path Parameter**: `filename` - 形如 `大语言模型_20260501_123456` 的文件夹名称
- **Response**:
```json
{
  "filename": "大语言模型_20260501_123456",
  "content": "组合后的包含综述和笔记的完整内容",
  "writer_result": "单纯的最终综述正文内容",
  "researcher_result": "单纯的收集到的研究笔记内容",
  "papers": [
    "2311.01234.pdf",
    "2402.05678.pdf"
  ]
}
```
*参数说明*：`papers` 是当前文件夹下载存储的所有本地论文 PDF 的文件名列表。

### 3.3 访问本地 PDF 原文
如果大模型在调研过程中成功下载到了 PDF，可以通过该接口获取对应文献的二进制文件。

- **URL**: `/api/agent/document/{filename}/papers/{pdf_name}`
- **Method**: `GET`
- **Path Parameter**: 
  - `filename`: 任务目录名
  - `pdf_name`: PDF文件名，带 `.pdf` 后缀
- **Response**: `application/pdf` 文件流。