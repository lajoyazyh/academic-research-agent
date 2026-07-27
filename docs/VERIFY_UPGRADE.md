# 升级验证手册

## 1. 自动回归

在项目根目录执行：

```powershell
python -m compileall -q agent
python -m pytest -q
node --check agent/frontend/cache.js
node --check agent/frontend/theme.js
npm run build
```

预期结果：Python 测试全部通过、JavaScript 无语法错误、`dist` 构建成功。

## 2. 启动本地服务

```powershell
python -m uvicorn web_app:app --app-dir agent --host 127.0.0.1 --port 8000
```

访问 `http://127.0.0.1:8000/`。如果本地没有 Supabase 公共配置，登录按钮会处于不可用状态，但公开首页、主题切换和本地模式 API 仍可验证。

## 3. 验证加载优化

打开浏览器开发者工具的 Network 面板，启用 Preserve log：

1. 清空当前站点的 Session Storage，首次进入 `/app`。
2. 确认工作台只请求一次 `/api/sessions/list`、一次 `/api/stats` 和一次 `/api/provider/status`；不应再为最近 10 个项目逐个请求详情。
3. 在 5 分钟内刷新或重新打开 `/app`。项目卡片和统计应立即从按用户隔离的本地缓存显示，并且不会重复请求上述两个接口。
4. 打开一个项目后刷新 `/app/console?sessionId=...`。论文、阶段和已有产物应先显示，再由后台请求刷新。
5. 首次进入 `/app/profile` 后确认会请求 `/api/provider/catalog`；再次打开时模型目录应直接出现。六小时内不会重复请求目录，除非点击“重新加载模型”。
6. 未打开全局知识库侧栏时，不应请求 `/api/knowledge/stats` 或 `/api/knowledge/sessions`；第一次打开侧栏时才加载。
7. 重新打开一个仍处于“规划”状态的旧项目，不应自动调用 `POST .../run/plan`；只有新建项目首次跳转时自动规划，之后由“生成关键词”按钮显式触发。
8. 控制台一次渲染最多请求一次 `.../context/stats`，不应再出现同一地址连续请求三到四次。

项目列表和统计写入按用户隔离的 Local Storage，最长保留 24 小时并在退出登录时清理；完整会话详情仍只写入 Session Storage。模型目录可以缓存到 Local Storage，但其中不包含 API Key。

## 4. 验证关系型 Session 存储

1. `/api/health` 应返回 `session_store=postgres+storage`。
2. `/api/sessions/list` 应直接读取 `research_sessions`，不应下载用户级 `workspace.zip`。
3. 响应中的 `Server-Timing` 应包含 `auth`、`persistence` 和 `app`。
4. 打开单个项目时，只允许恢复 `<tenant>/sessions/<session>/session.zip`。
5. PDF 应记录在 `research_files`，并在真正预览或生成笔记时按需获取。
6. 老用户第一次访问可能执行一次兼容导入；第二次及后续实例启动必须直接读取 Postgres。

## 5. 验证主题同步

1. 在公开首页点击太阳/月亮按钮。
2. 刷新公开首页，主题应保持不变，且不应先闪现另一种主题。
3. 进入 `/app` 或 `/app/console`，内部页面应沿用同一主题。
4. 在内部页面切回另一主题，再返回公开首页，公开首页应同步变化。
5. 分别在 390×844、768×1024 和 1440×900 检查，无横向滚动或导航覆盖。

## 6. 验证长任务恢复与安全性

- 搜索或自动流程启动响应应包含 `run_id`。
- 刷新控制台后，运行中的任务应恢复进度轮询。
- 服务重启后再次打开项目，应显示“任务已中断，可重试”，已生成的论文和笔记仍保留。
- `.runs` 下的 JSON 运行记录不得包含 `api_key`、GitHub token 或 Authorization 头。
- 连续超量调用运行、上传或模型测试接口时应返回 HTTP 429、`error_code=rate_limited` 和 `Retry-After`。
