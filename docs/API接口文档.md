# Academic Research Agent API 接口文档

**版本**：v3.0  
**日期**：2026-06-18  
**Base URL**：`http://127.0.0.1:8000`

---

## 1. 健康检查与统计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/stats` | 首页工作台统计 |

---

## 2. Session 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/sessions/create` | 创建新 Session |
| GET | `/api/sessions/list` | 获取 Session 列表 |
| GET | `/api/sessions/{session_id}` | 获取 Session 完整状态 |
| PUT | `/api/sessions/{session_id}` | 更新 Session 元数据 |
| DELETE | `/api/sessions/{session_id}` | 删除 Session |
| PUT | `/api/sessions/{session_id}/state` | 更新状态，带状态机校验 |
| POST | `/api/sessions/{session_id}/state/auto-fix` | 自动修复卡住状态 |
| GET | `/api/sessions/state-machine` | 获取状态机定义 |
| PUT | `/api/sessions/{session_id}/keywords` | 保存确认后的关键词 |

### 创建 Session 示例

```json
POST /api/sessions/create
{
  "topic": "LLM Agent Memory",
  "skills": {
    "search": null,
    "notes": null,
    "write": null
  }
}
```

---

## 3. Agent 执行

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/sessions/{session_id}/run/plan` | 执行规划阶段 |
| POST | `/api/sessions/{session_id}/run/search` | 后台执行搜索阶段 |
| POST | `/api/sessions/{session_id}/run/notes` | 为选中论文生成笔记 |
| POST | `/api/sessions/{session_id}/run/notes/revise` | 根据反馈修订笔记 |
| POST | `/api/sessions/{session_id}/run/analyze` | 生成深度分析 |
| POST | `/api/sessions/{session_id}/run/write` | 生成或重写综述 |
| POST | `/api/sessions/{session_id}/run/auto` | 自动执行完整 Pipeline |
| GET | `/api/sessions/{session_id}/run/status` | 查询运行状态 |
| POST | `/api/sessions/{session_id}/run/cancel` | 取消正在运行的任务 |

### 自动执行示例

```json
POST /api/sessions/{session_id}/run/auto
{
  "topic": "LLM Agent Memory",
  "max_loops": 20
}
```

自动执行顺序：

```text
规划 -> 搜索 -> 笔记 -> 分析 -> 综述
```

---

## 4. 论文管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sessions/{session_id}/papers` | 获取论文列表 |
| DELETE | `/api/sessions/{session_id}/papers/{paper_id}` | 删除论文 |
| POST | `/api/sessions/{session_id}/papers/batch-delete` | 批量删除论文 |
| PUT | `/api/sessions/{session_id}/papers/{paper_id}/status` | 更新论文状态 |
| POST | `/api/sessions/{session_id}/papers/custom` | 通过 arXiv ID / 链接 / 元数据添加论文 |
| POST | `/api/sessions/{session_id}/papers/upload` | 上传 PDF 添加论文 |

论文状态通常包括：

- `accepted`
- `pending`
- `rejected`

---

## 5. 笔记、分析与综述

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sessions/{session_id}/notes` | 获取笔记 |
| PUT | `/api/sessions/{session_id}/notes` | 保存笔记 |
| PUT | `/api/sessions/{session_id}/analysis` | 保存分析卡片或完整分析文档 |
| GET | `/api/sessions/{session_id}/draft` | 获取综述草稿 |
| PUT | `/api/sessions/{session_id}/draft` | 保存综述草稿 |
| PUT | `/api/sessions/{session_id}/feedback` | 保存综述修改反馈 |

### 分析类型

`/run/analyze` 支持：

- `compare`
- `lineage`
- `gaps`
- `all`

---

## 6. Session 内聊天

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/sessions/{session_id}/chat` | 统一聊天入口，支持普通问答和修订协同 |
| GET | `/api/sessions/{session_id}/conversations` | 获取聊天会话列表 |
| POST | `/api/sessions/{session_id}/conversations` | 创建聊天会话 |
| GET | `/api/sessions/{session_id}/conversations/{conv_id}/messages` | 获取指定聊天消息 |
| DELETE | `/api/sessions/{session_id}/conversations/{conv_id}` | 删除聊天会话 |
| GET | `/api/sessions/{session_id}/context/stats` | 获取上下文窗口统计 |
| POST | `/api/sessions/{session_id}/context/compress` | 压缩早期对话上下文 |

### 聊天请求示例

```json
POST /api/sessions/{session_id}/chat
{
  "message": "帮我解释这几篇论文的共同方法",
  "mode": "chat",
  "conv_id": "conv_xxx"
}
```

---

## 7. 全局知识库与 Copilot

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/knowledge/stats` | 获取全局知识库统计 |
| GET | `/api/knowledge/sessions` | 获取可选知识范围 Session 摘要 |
| POST | `/api/knowledge/search` | 跨 Session 检索 |
| POST | `/api/knowledge/chat` | 全局 Copilot 问答 |
| POST | `/api/knowledge/rebuild` | 重建全局知识索引 |
| GET | `/api/copilot/sessions` | 获取 Copilot 对话列表 |
| POST | `/api/copilot/sessions` | 新建 Copilot 对话 |
| GET | `/api/copilot/sessions/{copilot_session_id}/messages` | 获取 Copilot 消息 |
| DELETE | `/api/copilot/sessions/{copilot_session_id}` | 删除 Copilot 对话 |
| PUT | `/api/copilot/sessions/{copilot_session_id}` | 重命名 Copilot 对话 |

### 全局 Copilot 请求示例

```json
POST /api/knowledge/chat
{
  "message": "这些项目里有哪些共同研究空白？",
  "copilot_session_id": "copilot_xxx",
  "session_ids": ["sess_1", "sess_2"]
}
```

说明：

- 不传 `session_ids` 时，全局检索所有真实 Session。
- 传入 `session_ids` 时，只检索指定 Session。

---

## 8. Skills 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/skills` | 获取 Skills 列表 |
| POST | `/api/skills` | 创建 Skill |
| PUT | `/api/skills/{skill_id}` | 更新 Skill |
| DELETE | `/api/skills/{skill_id}` | 软删除 Skill |
| GET | `/api/skills/defaults` | 获取系统默认 Skill |
| GET | `/api/skills/{skill_id}/usage` | 查看 Skill 使用情况 |

Skill 类型：

- `search`
- `notes`
- `write`

---

## 9. 工具管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tools` | 获取工具列表 |
| PUT | `/api/tools/{tool_name}/toggle` | 启用或禁用工具 |
| PUT | `/api/tools/{tool_name}/config` | 更新工具配置 |
| PUT | `/api/tools/batch-toggle` | 批量切换工具 |
| POST | `/api/tools/reset` | 重置工具配置 |

---

## 10. 收藏、历史与页面辅助

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/favorites` | 获取收藏夹 |
| POST | `/api/favorites` | 添加收藏 |
| DELETE | `/api/favorites/{filename}` | 取消收藏 |
| GET | `/api/agent/history` | 获取旧版历史综述列表 |
| GET | `/api/agent/history/{filename}` | 获取旧版历史综述详情 |
| DELETE | `/api/agent/history/{filename}` | 删除旧版历史综述 |
| GET | `/api/agent/document/{filename}/papers/{pdf_name}` | 获取 PDF |
| POST | `/api/keywords/extract` | 仅提取关键词，不创建 Session |

---

## 11. 页面路由

| 路径 | 页面 |
|------|------|
| `/` | 首页 |
| `/app/console` | 控制台 |
| `/app/history` | 历史记录 |
| `/app/chat` | 对话页面 |
| `/app/help` | 帮助页面 |
| `/app/skills` | Skills 管理页面 |

---

## 12. 通用错误

常见 HTTP 状态：

| 状态码 | 含义 |
|------|------|
| 400 | 请求参数为空或格式错误 |
| 404 | Session、论文、Skill 或文件不存在 |
| 409 | 状态冲突或正在运行 |
| 500 | 后端执行失败 |

所有接口默认返回 JSON；文件和 PDF 接口返回文件响应。
