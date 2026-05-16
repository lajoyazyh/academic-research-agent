# 迭代三：连续对话与交互式调研平台

迭代三在迭代二 Agent 的基础上，从“一次性黑盒执行”升级为**会话驱动的交互式调研平台**——用户可在关键决策点参与、编辑、反馈，与 Agent 协作完成高质量文献综述。

## 演示视频
- 迭代二：https://www.bilibili.com/video/BV1Fq5A61EMV

## 核心模块

agent/
├── web_app.py              # FastAPI Web 服务入口
├── main.py                 # Agent 管线（Plan / Search / Write 断点执行）
├── backend/
│   ├── session_manager.py  # Session 会话状态管理（8 阶段状态机）
│   └── api.py              # 独立 API（备用）
├── core/                   # Agent 核心（ReAct 循环、工具调度）
├── tools/                  # 学术检索工具
├── llms/                   # LLM 客户端（智谱 API）
├── frontend/               # Web UI
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── sessions/               # Session 数据存储
│   └── {session_id}/
│       ├── metadata.json
│       ├── plan/           # 规划与关键词
│       ├── papers/         # 论文 PDF + 元数据
│       ├── notes/          # 笔记草稿 + 编辑历史
│       └── draft/          # 综述草稿多版本
├── documents/              # 迭代二兼容：历史综述产物
├── tests/                  # 自动化测试
└── prompts/                # Prompt 模板

## 迭代三核心创新

### 1. Session 会话模型
每个学术调研任务是一个持久化的 Session，中间可暂停/修改/继续。

```
planning -> plan_confirmed -> searching -> search_complete
-> reviewing_notes -> writing -> reviewing_draft -> complete
```

### 2. 左侧面板双模块

| 模块 | 本质 | 存储位置 | 用途 |
|------|------|---------|------|
| ⭐ **收藏夹** | 用户主动收藏的满意综述 | `agent/favorites.json` | 手动收藏/取消收藏；只展示用户认可的结果；可折叠/展开 |
| 🔄 **会话管理** | 进行中的交互式调研 | `agent/sessions/` | 新建/恢复/删除会话；编辑关键词；审核笔记 |

> 两模块关系：**会话管理是"做研究的地方"，收藏夹是"满意的研究成果档案室"**。浏览综述时点击 ⭐ 即可加入收藏夹。

### 3. 关键步骤可见化
- **关键词审核**（✅ 已实现）：Plan 阶段后展示关键词方案，用户可编辑/删除/新增；可随时通过会话旁的 ✏️ 编辑按钮重新修改
- **论文管理**（第二波规划）：混合 Agent 搜索 + 用户上传，支持审查模式
- **笔记编辑**（第三波规划）：在线 Markdown 分屏编辑器，修改后可重新撰写
- **综述反馈**（第三波规划）：提交修改意见，最多 2 次反馈重写

## 当前实现进度

| 波次 | 状态 | 已实现 |
|------|:----:|------|
| 第一波：Session 管理 + 关键词确认 | 完成 | SessionManager、状态机、关键词确认 UI、折叠/删除 |
| 第二波：论文管理 + 混合来源 | 待开发 | -- |
| 第三波：笔记编辑 + 综述重写 | 待开发 | -- |

## 环境安装

```powershell
cd 迭代三
python -m pip install -r requirements.txt
```

## 配置方式
依赖智谱 API：在 agent/.env 中配置 ZHIPU_API_KEY、ZHIPU_BASE_URL、ZHIPU_MODEL。

## 运行方式

```powershell
cd 迭代三/agent
python web_app.py
```

浏览器打开 `http://127.0.0.1:8000/`

## Session 管理 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/sessions/create | 创建新会话 |
| GET | /api/sessions/list | 列出所有会话 |
| GET | /api/sessions/{id} | 获取会话完整状态 |
| DELETE | /api/sessions/{id} | 删除会话 |
| PUT | /api/sessions/{id}/state | 状态转移（带校验） |
| PUT | /api/sessions/{id}/keywords | 保存确认后的关键词 |
| POST | /api/sessions/{id}/run/plan | 执行规划阶段 |
| POST | /api/sessions/{id}/run/search | 执行搜索阶段 |
| POST | /api/sessions/{id}/run/write | 执行撰写阶段 |
| GET | /api/sessions/{id}/papers | 获取论文列表 |
| GET | /api/sessions/state-machine | 获取状态机定义 |

## 收藏夹 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/favorites` | 获取收藏列表 |
| `POST` | `/api/favorites` | 加入收藏 `{filename, topic}` |
| `DELETE` | `/api/favorites/{filename}` | 取消收藏 |

## Agent 断点执行

`main.py` 新增三个独立阶段函数：

```python
run_plan_only(topic)                           # 阶段 1：仅规划
run_search_only(topic, plan, keywords)         # 阶段 2：搜索并记录笔记
run_write_from_notes(topic, notes, feedback)   # 阶段 3：撰写/反馈重写
```

## GitLab CI

CI 配置在仓库根目录 `.gitlab-ci.yml`，每次 push 自动安装依赖并运行 `pytest tests/`。

## 进一步规划
- 第二波：论文混合来源（标题/DOI/PDF 上传）+ 智能审查模式
- 第三波：在线笔记编辑器 + 综述反馈重写
- 迭代四：多用户协作、自动化评测集成、模板预设
