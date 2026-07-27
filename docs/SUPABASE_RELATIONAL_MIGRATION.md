# Supabase 关系型研究数据迁移

## 新架构

- `research_sessions`：首页列表、状态和完整非二进制快照。
- `research_papers`：论文元数据、筛选状态和用户备注。
- `research_artifacts`：规划、笔记、分析、轨迹和综述版本。
- `research_conversations` / `research_messages`：项目内对话。
- `research_runs`：可恢复的长任务记录。
- `research_files`：PDF 和全文文件的 Storage 对象索引。
- `research-workspaces` Storage bucket：
  - `<tenant>/sessions/<session>/session.zip`：不含 PDF 的小型兼容归档。
  - `<tenant>/sessions/<session>/files/*`：独立 PDF/全文对象。
  - `<tenant>/workspace-aux.zip`：Skill、Copilot 等辅助设置。

API Key、GitHub token 和 Authorization 头不会进入数据库、对象存储或运行记录。

## 旧数据导入

旧的 `<tenant>/workspace.zip` 保持只读兼容：

1. 用户迁移后第一次访问历史列表。
2. 后端发现 `research_sessions` 中没有该用户的数据。
3. 只下载一次旧 ZIP，并批量写入可查询 Session 索引。
4. 列表可返回后，后台再上传论文文件、对话、产物和运行记录。
5. 后续实例冷启动直接查询 Postgres，不再下载整个工作区。

迁移期间不会删除旧 ZIP。确认所有用户完成导入并经过备份周期后，才能单独安排清理。

## 性能验证

浏览器 Network 中检查：

- `/api/sessions/list` 和 `/api/stats` 响应包含 `Server-Timing`。
- 普通冷启动后 `persistence` 不应包含工作区 ZIP 解压时间。
- 第二次打开工作台时，5 分钟内不应再次请求列表和统计。
- 打开一个 Session 只恢复该 Session 的小型归档。
- PDF 只在预览、问答或生成笔记需要时按需下载。

## 回滚

旧 `workspace.zip` 在迁移阶段仍保留。若关系型读取不可用：

- 后端会退回本地文件系统模式；
- 旧 ZIP 可用于恢复历史数据；
- 数据库迁移是只增不删，不会改变 Supabase Auth 或现有 Storage bucket。
