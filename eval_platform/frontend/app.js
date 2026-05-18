const API_BASE = 'http://127.0.0.1:8001';

const api = axios.create({ baseURL: API_BASE });

// Basic Router implementation
const routes = {
  '/home': HomeView,
  '/dashboard': DashboardView,
  '/tasks': TaskList,
  '/tasks/detail/:taskId': TaskDetail,
  '/dataset': DatasetView
};

function router() {
    const hash = window.location.hash.slice(1) || '/home';
  const appElement = document.getElementById('router-view');
  appElement.innerHTML = '';
  updateNav(hash);
  
  // simple matching
  if (hash.startsWith('/tasks/detail/')) {
    const taskId = hash.split('/')[3];
    routes['/tasks/detail/:taskId'](taskId, appElement);
  } else if (routes[hash]) {
    routes[hash](appElement);
  } else {
    routes['/tasks'](appElement);
  }
}

function updateNav(hash) {
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.remove('active');
    if (hash.startsWith(el.getAttribute('href').slice(1))) {
      el.classList.add('active');
    }
  });
}

function formatCard(title, contentHTML) {
  return `
    <div class="card">
      <div class="card-header">
        <span>${title}</span>
      </div>
      <div class="card-body">
        ${contentHTML}
      </div>
    </div>
  `;
}

function formatDateTime(value) {
  if (!value) return '未知';
  const date = parseDateValue(value);
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return String(value);
  try {
    return new Intl.DateTimeFormat('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
      timeZone: 'Asia/Shanghai'
    }).format(date);
  } catch (e) {
    return date.toLocaleString();
  }
}


function parseDateValue(value) {
  // Handle numeric timestamps (seconds or milliseconds)
  if (typeof value === 'number') {
    // treat large numbers as milliseconds, small numbers (10-digit) as seconds
    return value > 1e12 ? new Date(value) : new Date(value * 1000);
  }
  if (!value) return new Date(NaN);
  if (typeof value !== 'string') {
    try { return new Date(value); } catch (e) { return new Date(NaN); }
  }
  const s = value.trim();
  // Common DB format: "YYYY-MM-DD HH:MM:SS" -> convert to ISO and assume UTC
  const spaceIso = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/;
  const isoNoTZ = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/;
  try {
    if (spaceIso.test(s)) {
      return new Date(s.replace(' ', 'T') + 'Z');
    }
    if (isoNoTZ.test(s)) {
      return new Date(s + 'Z');
    }
    // If it already contains timezone info (Z or ±hh:mm), let Date parse it
    return new Date(s);
  } catch (e) {
    return new Date(NaN);
  }
}

function formatScoreValue(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '-';
  return value.toFixed(3);
}

function getPrimaryScore(scoreMap) {
  const preferredOrder = ['answer_relevancy', 'answer_similarity', 'similarity_score', 'overall_score'];
  for (const key of preferredOrder) {
    if (typeof scoreMap[key] === 'number' && Number.isFinite(scoreMap[key])) {
      return scoreMap[key];
    }
  }
  const firstNumeric = Object.values(scoreMap).find(value => typeof value === 'number' && Number.isFinite(value));
  return typeof firstNumeric === 'number' ? firstNumeric : null;
}

function getResultTitle(result) {
  if (!result) return '暂无结果';
  const backend = result.backend || 'unknown';
  const method = result.method || 'unknown';
  return `${backend} / ${method}`;
}

function renderStatBarCard(label, value, color) {
  return `<div class="stat-card" style="border-left:3px solid ${color};">
    <div class="stat-card-label">${label}</div>
    <div class="stat-card-value" style="color:${color};">${value}</div>
  </div>`;
}

function renderStatCards(stats, containerIdPrefix) {
  const html = Object.entries(stats)
    .map(([label, value], index) => `
      <div class="stat-card">
        <div class="stat-card-label">${label}</div>
        <div class="stat-card-value">${value}</div>
      </div>
    `)
    .join('');
  return `<div class="stat-grid" id="${containerIdPrefix}">${html}</div>`;
}

function renderScoreCards(scoreMap) {
  const entries = Object.entries(scoreMap)
    .filter(([, value]) => typeof value === 'number' && Number.isFinite(value));
  if (!entries.length) {
    return '<p style="color:#94a3b8;">当前结果没有可展示的分数。</p>';
  }
  return `<div class="score-grid">${entries.map(([key, value]) => `
    <div class="score-card">
      <div class="score-label">${getMetricLabel(key)}</div>
      <div class="score-value">${formatScoreValue(value)}</div>
    </div>
  `).join('')}</div>`;
}

function safeJsonStringify(value, spacing = 2) {
  try {
    return JSON.stringify(value, null, spacing);
  } catch (error) {
    return String(value);
  }
}

function renderJsonAccordion(title, data) {
  return `
    <details class="json-details">
      <summary>${title}</summary>
      <pre>${safeJsonStringify(data)}</pre>
    </details>
  `;
}

function renderFailureList(tasks) {
  if (!tasks.length) {
    return '<p style="color:#94a3b8; text-align:center; padding:24px 0;">暂无失败任务</p>';
  }
  return `<div class="failure-list">${tasks.map(task => `
    <div class="failure-item">
      <div class="failure-header">
        <div>
          <strong>${task.task_name || '未命名任务'}</strong>
          <div class="failure-meta">ID ${task.id} · ${formatDateTime(task.created_at)} · ${task.method || '-'}</div>
        </div>
        <button class="btn-text" onclick="location.hash='/tasks/detail/${task.id}'">查看详情</button>
      </div>
      <div class="failure-message">${task.error_message || '无错误信息'}</div>
    </div>
  `).join('')}</div>`;
}

function extractResultsSource(payload) {
  if (!payload) return null;
  if (payload.data && typeof payload.data === 'object') {
    return payload.data;
  }
  return payload;
}

function extractScoreMap(payload) {
  const source = extractResultsSource(payload);
  if (!source) return {};
  let raw = {};
  if (source.scores && typeof source.scores === 'object') {
    raw = source.scores;
  } else {
    const numericEntries = Object.entries(source).filter(([, value]) => typeof value === 'number' && Number.isFinite(value));
    if (numericEntries.length > 0) {
      raw = Object.fromEntries(numericEntries);
    }
  }
  // 始终移除 ragas faithfulness（始终为 0，不可用）
  delete raw.faithfulness;
  return raw;
}

function extractTraceItems(payload) {
  const source = extractResultsSource(payload);
  if (!source) return [];
  if (Array.isArray(source.traces)) return source.traces;
  if (Array.isArray(source.trajectory)) return source.trajectory;
  if (Array.isArray(source.logs)) return source.logs;
  return [];
}

function getMetricLabel(metricKey) {
  const labelMap = {
    answer_relevancy: 'Answer Relevance',
    answer_correctness: 'Answer Correctness',
    answer_similarity: 'Answer Similarity',
    context_precision: 'Context Precision',
    context_recall: 'Context Recall',
    similarity_score: 'Similarity Score',
    faithfulness_score: 'Faithfulness (LLM)',
    overall_score: 'Overall Score',
    completeness_score: 'Completeness',
    relevance_score: 'Relevance',
    grounding_score: 'Grounding',
    reasoning_score: 'Reasoning',
    step_coherence_score: 'Step Coherence',
    helpfulness_score: 'Helpfulness'
  };
  return labelMap[metricKey] || metricKey;
}

function buildRadarOption(scoreMap, seriesName) {
  const filtered = Object.fromEntries(
    Object.entries(scoreMap).filter(([key]) => key !== 'faithfulness')
  );
  const entries = Object.entries(filtered)
    .filter(([, value]) => typeof value === 'number' && Number.isFinite(value))
    .sort((a, b) => a[0].localeCompare(b[0]));

  const radarValues = entries.map(([, value]) => value);
  const indicators = entries.length > 0
    ? entries.map(([key]) => ({ name: getMetricLabel(key), max: 1 }))
    : [{ name: 'No Data', max: 1 }];

  return {
    tooltip: {},
    radar: { indicator: indicators },
    series: [{
      name: seriesName,
      type: 'radar',
      data: [{
        value: entries.length > 0 ? radarValues : [0],
        name: seriesName
      }],
      areaStyle: { color: 'rgba(24, 144, 255, 0.4)' },
      itemStyle: { color: '#1890ff' }
    }]
  };
}

// ---------------- Home View ---------------- //
function HomeView(container) {
  container.innerHTML = `
    <div class="home-page">
      <div class="home-hero">
        <h1 class="home-title">Agent 评测平台</h1>
        <p class="home-subtitle">
          一站式大模型 Agent 任务管理与性能评测，<br>让每一次迭代都有据可循。
        </p>
        <div class="home-cards">
          <div class="card home-card" onclick="location.hash='#/dashboard'">
              <div class="card-body" style="display:flex; flex-direction:column; align-items:center; text-align:center; padding:28px;">
                <div style="font-size:48px; margin-bottom:16px;">📊</div>
                <h3 style="margin:0 0 8px;">大盘概览</h3>
                <p style="color:#64748b; font-size:14px; line-height:1.6;">查看任务统计、最新得分及失败分析</p>
              </div>
          </div>
          <div class="card home-card" onclick="location.hash='#/tasks'">
            <div class="card-body" style="display:flex; flex-direction:column; align-items:center; text-align:center; padding:28px;">
              <div style="font-size:48px; margin-bottom:16px;">📋</div>
              <h3 style="margin:0 0 8px;">任务记录</h3>
              <p style="color:#64748b; font-size:14px; line-height:1.6;">管理评测任务，查看历史与详情</p>
            </div>
          </div>
          <div class="card home-card" onclick="location.hash='#/dataset'">
            <div class="card-body" style="display:flex; flex-direction:column; align-items:center; text-align:center; padding:28px;">
              <div style="font-size:48px; margin-bottom:16px;">📦</div>
              <h3 style="margin:0 0 8px;">评测基准测试集</h3>
              <p style="color:#64748b; font-size:14px; line-height:1.6;">维护测试数据与标准答案</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}


// ---------------- Dashboard View ---------------- //
async function DashboardView(container) {
  container.innerHTML = `
    <div class="page-hero page-section-tight">
      <h1 class="page-title">大盘概览</h1>
      <p class="page-subtitle">观察当前任务结构、失败分布和最近完成结果。</p>
    </div>
    <div id="dashboard-stat-bar" class="stat-grid loading-skeleton" style="margin-bottom:20px;"></div>
    <div class="card dashboard-top">
       <div>
         <h3>&nbsp &nbsp最近一次评测指标 (Latest Metrics)</h3>
         <div id="overview-radar-chart" class="chart-container loading-skeleton"></div>
       </div>
       <div>
         <h3>最新完成任务 (Latest Completed)</h3>
         <div id="latest-result-container" class="loading-skeleton" style="height:350px; overflow-y:auto; padding: 10px;"></div>
       </div>
    </div>
    <div class="card">
      <div class="card-header"><span>任务状态速览</span></div>
      <div class="card-body">
        <div style="display:grid; grid-template-columns:1fr; gap:20px;">
          <div>
            <h4 style="margin:0 0 12px; color:#d92d20;">失败任务 (Failed)</h4>
            <div id="failed-tasks-container" class="loading-skeleton" style="min-height:140px;"></div>
          </div>
        </div>
      </div>
    </div>
  `;
  try {
    const res = await api.get('/tasks/list?skip=0&limit=50');
    const tasks = res.data.tasks || [];
    const latestCompleted = [...tasks]
      .filter(task => task.status === 'completed' && task.results)
      .sort((a, b) => parseDateValue(b.created_at || 0) - parseDateValue(a.created_at || 0))[0];
    const failedTasks = tasks.filter(task => task.status === 'failed');

    // Dashboard stat bar
    const total = tasks.length;
    const completed = tasks.filter(t => t.status === 'completed').length;
    const failed = failedTasks.length;
    const running = tasks.filter(t => t.status === 'running').length;
    const statBar = document.getElementById('dashboard-stat-bar');
    statBar.className = 'stat-grid';
    statBar.innerHTML = `${renderStatBarCard('总任务', total, '#64748b')}${renderStatBarCard('已完成', completed, '#1f8f4a')}${renderStatBarCard('失败', failed, '#d92d20')}${renderStatBarCard('进行中', running, '#c77700')}`;

    // Use latest completed task scores for the radar chart
    const latestScores = latestCompleted ? extractScoreMap(latestCompleted.results) : {};
    
    // Render the chart using the existing renderRadarChart function but custom legend
    const chartContainer = document.getElementById('overview-radar-chart');
    chartContainer.className = 'chart-container'; 
    const myChart = echarts.init(chartContainer);
    
    myChart.setOption(buildRadarOption(latestScores, 'Latest Performance'));
    
    // Render latest completed task preview
    const latestContainer = document.getElementById('latest-result-container');
    if (latestCompleted) {
      const scores = extractScoreMap(latestCompleted.results);
      delete scores.faithfulness;  // 移除始终为 0 的 ragas faithfulness
      latestContainer.innerHTML = `
        <div style="padding: 4px 0 12px 0;">
          <div><strong>${latestCompleted.task_name || '未命名任务'}</strong></div>
          <div style="color:#64748b; margin-top:4px;">${getResultTitle(latestCompleted.results)} · ${formatDateTime(latestCompleted.created_at)}</div>
        </div>
        ${renderScoreCards(scores)}
        <div style="margin-top:12px; padding:12px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px;">
          <div><strong>主要得分</strong></div>
          <div style="font-size:28px; font-weight:700; color:#1890ff; margin-top:4px;">${formatScoreValue(getPrimaryScore(scores))}</div>
          <div style="color:#64748b; margin-top:4px;">样本数：${latestCompleted.results.sample_count ?? 0}</div>
        </div>
      `;
    } else {
      latestContainer.innerHTML = '<p style="color:#999; text-align:center; padding: 40px;">暂无已完成任务</p>';
    }
    latestContainer.classList.remove('loading-skeleton');

    const failedContainer = document.getElementById('failed-tasks-container');
    failedContainer.innerHTML = renderFailureList(failedTasks);
    failedContainer.classList.remove('loading-skeleton');

    // Pending tasks column removed per UI update
    
  } catch(e) {
    const isEmpty = e.response?.status === 404;
    const msg = isEmpty ? '暂无数据，请先创建数据集和任务。' : `加载大盘数据失败: ${e.message}`;
    const color = isEmpty ? '#94a3b8' : 'red';
    const els = ['overview-radar-chart', 'failed-tasks-container', 'latest-result-container', 'dashboard-stat-bar'];
    els.forEach(id => {
      const el = document.getElementById(id);
      if (el) { el.innerHTML = `<p style="padding:20px; text-align:center; color:${color};">${msg}</p>`; el.classList.remove('loading-skeleton'); }
    });
  }
}

// ---------------- Task List View ---------------- //
async function TaskList(container) {
  container.innerHTML = `
    <div class="page-hero page-section-tight">
      <h1 class="page-title">任务记录</h1>
      <p class="page-subtitle">查看所有评测任务的状态、方法和结果概览。完成项、失败项和待处理项会被分开呈现，方便快速定位问题。</p>
    </div>
    <div class="page-actions">
      <button class="btn" onclick="openTaskModal()">+ 新建评测任务</button>
    </div>
    <div class="card">
      <div class="card-header">
        <span>任务记录库 (Histories)</span>
      </div>
      <div class="card-body">
        <div id="table-container" class="loading-skeleton" style="max-height: 70vh; overflow-y: auto; width: 100%;"></div>
      </div>
    </div>

    <!-- Create Task Modal Form -->
    <div id="task-modal" class="modal-overlay">
      <div class="modal-sheet">
        <div class="modal-header">
          <div class="modal-kicker">Create Task</div>
          <h3 class="modal-title">新建评测任务</h3>
          <p class="modal-desc">创建一个新的评测任务，并绑定数据集与评测方法。</p>
        </div>
        <div class="form-grid">
          <div class="form-group">
            <label class="form-label" for="tk-name">任务名称 <sup>*</sup></label>
            <input class="field" type="text" id="tk-name" placeholder="例如: MathEval Agent V2">
          </div>
          <div class="form-group">
            <label class="form-label" for="tk-method">评估方法 (Method) <sup>*</sup></label>
            <select class="field" id="tk-method">
              <option value="result_oriented">面向结果 (Result Oriented)</option>
              <option value="process_oriented">面向过程 (Process Oriented)</option>
              <option value="explicit_metrics">综合指标 (Explicit Metrics)</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label" for="tk-dataset">关联数据集 <sup>*</sup></label>
            <select class="field" id="tk-dataset">
              <option value="">加载中...</option>
            </select>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn-text" onclick="closeTaskModal()">取消</button>
          <button class="btn" onclick="submitTask()">创建并提交</button>
        </div>
      </div>
    </div>
  `;
  
  try {
    const res = await api.get('/tasks/list?skip=0&limit=50');
    // 修改处：后端返回的数据结构是 { tasks: [...] } 
    const tasks = res.data.tasks || []; 
    renderTable(tasks, document.getElementById('table-container'));
  } catch(e) {
    const isEmpty = e.response?.status === 404;
    const msg = isEmpty ? '暂无任务数据，点击右上角"新建评测任务"开始。' : `获取任务列表失败: ${e.message}`;
    document.getElementById('table-container').innerHTML = `<p style="color:${isEmpty ? '#94a3b8' : 'red'};">${msg}</p>`;
    document.getElementById('table-container').classList.remove('loading-skeleton');
  }
}

function renderTable(tasks, container) {
  if(!tasks || tasks.length === 0) { container.innerHTML = '<p>暂无数据</p>'; return; }
  
  let html = `<div class="table-wrap"><table>
    <thead><tr>
      <th>ID</th><th>任务名称</th><th>状态</th><th>方法</th><th>结果概览</th><th>创建时间</th><th>操作</th>
    </tr></thead><tbody>`;
    
    tasks.forEach(t => {
      const isCompleted = t.status === 'completed';
      const isFailed = t.status === 'failed';
      const isRunning = t.status === 'running';
      const tagClass = isCompleted ? 'completed' : (isFailed ? 'failed' : (isRunning ? 'running' : 'pending'));
      const scoreMap = extractScoreMap(t.results);
      const primaryScore = getPrimaryScore(scoreMap);
      const resultSummary = isCompleted
        ? `${t.results?.backend || 'unknown'} · ${t.results?.sample_count ?? 0} 样本 · ${formatScoreValue(primaryScore)}`
        : (isFailed ? (t.error_message || '失败') : (isRunning ? '执行中...' : '等待执行'));
      html += `<tr>
        <td>${t.id}</td>
        <td>${t.task_name || '默认任务'}</td>
        <td><span class="tag ${tagClass}">${t.status}</span></td>
        <td>${t.method || '-'}</td>
        <td>${resultSummary}</td>
        <td>${formatDateTime(t.created_at)}</td>
        <td>
          <button class="btn-text" onclick="location.hash='/tasks/detail/${t.id}'">查看详情</button>
          <button class="btn-text" style="color: #ff4d4f;" onclick="deleteTask('${t.id}')">删除</button>
        </td>
      </tr>`;
    });
    html += `</tbody></table></div>`;
  container.innerHTML = html;
  container.classList.remove('loading-skeleton');
}

window.openTaskModal = async function() {
  document.getElementById('task-modal').style.display = 'flex';
  const dsSelect = document.getElementById('tk-dataset');
  try {
    const res = await api.get('/datasets/list?skip=0&limit=50');
    const datasets = res.data.datasets || [];
    if(datasets.length === 0) {
      dsSelect.innerHTML = '<option value="">(请先在侧边栏创建数据集)</option>';
    } else {
      dsSelect.innerHTML = datasets.map(d => `<option value="${d.id}">${d.dataset_name} (ID: ${d.id})</option>`).join('');
    }
  } catch(e) {
    dsSelect.innerHTML = '<option value="">加载数据集失败</option>';
  }
}

window.closeTaskModal = function() {
  document.getElementById('task-modal').style.display = 'none';
  document.getElementById('tk-name').value = '';
  document.getElementById('tk-method').value = 'result_oriented';
}

window.submitTask = async function() {
  const name = document.getElementById('tk-name').value;
  const dataset = document.getElementById('tk-dataset').value;
  const method = document.getElementById('tk-method').value;
  
  if(!name || !dataset) {
    alert("请填完整必填项（若无数据集需先去侧边栏创建）。");
    return;
  }
  
  try {
    const createRes = await api.post('/tasks/create', {
      task_name: name,
      agent_id: 'default-agent',
      dataset_id: parseInt(dataset),
      method: method
    });
    const taskId = createRes.data.id;
    closeTaskModal();
    router();
    // 创建成功后自动开始评测
    await api.post(`/tasks/evaluate/${taskId}`);
    alert(`任务 #${taskId} 创建成功，评测已自动开始！`);
    router();
  } catch(e) {
    alert("创建失败: " + e.message);
  }
}

window.deleteTask = async function(taskId) {
  if(!confirm(`确定要删除任务 ${taskId} 吗？此操作不可恢复。`)) return;
  try {
    await api.delete(`/tasks/delete/${taskId}`);
    alert("删除成功");
    router(); // reload the task list
  } catch(e) {
    alert("删除失败: " + e.message);
  }
}

window.startEval = async function(taskId) {
  if (!confirm(`确定要开始评测任务 #${taskId} 吗？将向 Agent 下发指令并等待执行结果。`)) return;
  try {
    await api.post(`/tasks/evaluate/${taskId}`);
    alert("评测任务已下发，正在后台执行...");
    router();
  } catch(e) {
    alert("触发评测失败: " + e.message);
  }
}

window.retryEval = async function(taskId) {
  if (!confirm(`确定要重新评测任务 #${taskId} 吗？`)) return;
  try {
    await api.post(`/tasks/evaluate/${taskId}`);
    alert("重新评测已下发！");
    router();
  } catch(e) {
    alert("重新评测失败: " + e.message);
  }
}

window.deleteTaskFromDetail = async function(taskId) {
  if(!confirm(`确定要删除任务 ${taskId} 吗？此操作不可恢复。`)) return;
  try {
    await api.delete(`/tasks/delete/${taskId}`);
    alert("删除成功");
    window.location.hash = '#/tasks';
  } catch(e) {
    alert("删除失败: " + e.message);
  }
}

// ---------------- Task Detail View ---------------- //
async function TaskDetail(taskId, container) {
  container.innerHTML = `
    <div class="page-hero page-section-tight">
      <a href="#/tasks" class="btn-text" style="padding-left:0;">&larr; 返回列表</a>
      <h1 class="page-title" style="margin-top:10px;">任务详情：${taskId}</h1>
      <p class="page-subtitle">查看评测概况、分数分布、原始 JSON 和执行轨迹。</p>
      <div class="page-actions" style="margin-top:8px;">
        <button class="btn" onclick="retryEval('${taskId}')">🔄 重新评测</button>
        <button class="btn-text" style="color:#d92d20;" onclick="deleteTaskFromDetail('${taskId}')">🗑 删除此任务</button>
      </div>
    </div>
    <div id="task-detail-summary" class="loading-skeleton" style="margin-bottom:20px;"></div>
    <div class="card">
       <div class="card-body">
         <h3>多维评测指标</h3>
         <div id="radar-chart" class="chart-container loading-skeleton"></div>
       </div>
    </div>
    <div class="card">
       <div class="card-body">
         <h3>评估概况</h3>
         <div id="summary-info" class="loading-skeleton" style="min-height:120px;"></div>
       </div>
    </div>
    <div class="card">
       <div class="card-body">
         <h3>执行轨迹 (Trajectory)</h3>
         <div id="trajectory-timeline" class="loading-skeleton" style="min-height:200px;"></div>
       </div>
    </div>
    <div class="card">
       <div class="card-body">
         <h3>原始结果 JSON</h3>
         <div id="raw-json-container" class="loading-skeleton" style="min-height:120px;"></div>
       </div>
     </div>
  `;
  try {
    const [detailRes, resultRes] = await Promise.all([
      api.get(`/tasks/detail/${taskId}`),
      api.get(`/tasks/results/${taskId}`).catch(() => ({data: null})) // might be pending
    ]);
    
    const task = detailRes.data;
    const resultData = resultRes.data;
    // 从 task 对象的 results 字段中提取真正的评测结果
    const resultsSource = extractResultsSource((resultData || task)?.results) || null;
    const scoreMap = extractScoreMap(resultsSource);
    const traceItems = extractTraceItems(resultsSource || task);
    const taskSummary = document.getElementById('task-detail-summary');

    taskSummary.className = 'dashboard-stats';
    taskSummary.innerHTML = renderStatCards({
      '状态': task.status || 'unknown',
      '方法': task.method || '-'
    }, 'task-detail-stat-grid');
    
    // Check status
    if (!task || task.status === 'pending' || task.status === 'running') {
      document.getElementById('radar-chart').innerHTML = `<p style="padding:40px;text-align:center;color:#999;">未完成评测，请稍后刷新重试</p>`;
      document.getElementById('radar-chart').classList.remove('loading-skeleton');
      document.getElementById('summary-info').innerHTML = `<p>任务状态：运行中 / 待评测...</p>`;
      document.getElementById('summary-info').classList.remove('loading-skeleton');
      document.getElementById('trajectory-timeline').innerHTML = `<p>暂无轨迹信息</p>`;
      document.getElementById('trajectory-timeline').classList.remove('loading-skeleton');
      return;
    }

    renderSummary({ ...task, results: resultsSource }, document.getElementById('summary-info'));
    renderRadarChart(scoreMap, document.getElementById('radar-chart'));
    renderTimeline(traceItems, document.getElementById('trajectory-timeline'));

    const rawJsonContainer = document.getElementById('raw-json-container');
    rawJsonContainer.className = '';
    rawJsonContainer.innerHTML = `
      ${renderJsonAccordion('任务元数据 JSON', task)}
      ${renderJsonAccordion('评测结果 JSON', resultsSource || {})}
    `;
  } catch(e) {
    document.getElementById('radar-chart').innerHTML = `<p style="color:red;">加载详情失败: ${e.message}</p>`;
    document.getElementById('radar-chart').classList.remove('loading-skeleton');
  }
}

function renderSummary(data, container) {
  container.className = '';
  const results = extractResultsSource(data.results || data);
  const scoreMap = extractScoreMap(results);
  const scoreKeys = Object.keys(scoreMap);
  const answerPreview = results?.answer ? String(results.answer).slice(0, 280) : '无';
  const questionPreview = results?.question ? String(results.question) : '无';
  const metricNames = Array.isArray(results?.metric_names) ? results.metric_names : [];
  container.innerHTML = `
    <p><strong>任务名称：</strong> ${data.task_name || '未知'}</p>
    <p><strong>评测方法：</strong> ${results?.method || data.method || '未知'}</p>
    <p><strong>创建时间：</strong> ${formatDateTime(data.created_at)}</p>
    <p><strong>状态：</strong> ${data.status}</p>
    <p><strong>指标数量：</strong> ${scoreKeys.length}</p>
    <p><strong>问题：</strong> ${questionPreview}</p>
    <p><strong>回答预览：</strong> ${answerPreview}</p>
    <p><strong>指标列表：</strong> ${metricNames.length ? metricNames.join(', ') : '无'}</p>
  `;
  const scoreContainer = document.createElement('div');
  scoreContainer.innerHTML = renderScoreCards(scoreMap);
  container.appendChild(scoreContainer);
}

function renderRadarChart(scores, container) {
  container.className = 'chart-container'; 
  const myChart = echarts.init(container);
  myChart.setOption(buildRadarOption(scores || {}, 'Model Performance'));
}

function renderTimeline(trajectory, container) {
  container.className = 'timeline';
  
  if(!trajectory || !trajectory.length) {
    container.innerHTML = '<p style="color:#666; padding:24px; text-align:center;">暂无运行轨迹数据。</p>';
    return;
  }
  
  let html = '';
  trajectory.forEach((item, idx) => {
    if (typeof item !== 'object' || item === null) {
      html += `<div class="timeline-item"><strong>Step ${idx + 1}</strong><div class="timeline-content"><pre>${safeJsonStringify(item)}</pre></div></div>`;
      return;
    }
    const stepLabel = item.step || item.action || item.role || `Step ${idx + 1}`;
    const timeLabel = item.time || item.timestamp || '';
    const header = timeLabel ? `${stepLabel} — ${timeLabel}` : stepLabel;
    const thought = item.thought || item.thinking || item.reasoning || '';
    const action = item.action || item.tool || '';
    const input = item.input || item.tool_input || item.arguments || '';
    const observation = item.observation || item.output || item.result || '';
    const error = item.error || item.error_type || '';
    html += `
      <div class="timeline-item">
        <strong>${header}</strong>
        <div class="timeline-content">
          ${thought ? `<div class="trace-field"><span class="trace-label">Thought:</span><pre>${String(thought).slice(0, 600)}</pre></div>` : ''}
          ${action ? `<div class="trace-field"><span class="trace-label">Action:</span><code>${String(action)}</code></div>` : ''}
          ${input ? `<div class="trace-field"><span class="trace-label">Input:</span><pre>${safeJsonStringify(input)}</pre></div>` : ''}
          ${observation ? `<div class="trace-field"><span class="trace-label">Observation:</span><pre>${String(observation).slice(0, 800)}</pre></div>` : ''}
          ${error ? `<div class="trace-field"><span class="trace-label" style="color:#d92d20;">Error:</span><pre style="color:#d92d20;">${String(error)}</pre></div>` : ''}
        </div>
      </div>
    `;
  });
  container.innerHTML = html;
}

// ---------------- Dataset View ---------------- //
window.openDatasetModal = function() {
  document.getElementById('dataset-modal').style.display = 'flex';
}

window.closeDatasetModal = function() {
  document.getElementById('dataset-modal').style.display = 'none';
  document.getElementById('ds-name').value = '';
  document.getElementById('ds-desc').value = '';
  document.getElementById('ds-samples').value = '';
  document.getElementById('ds-truths').value = '';
}

window.submitDataset = async function() {
  const name = document.getElementById('ds-name').value;
  const desc = document.getElementById('ds-desc').value;
  const samples = document.getElementById('ds-samples').value;
  const truths = document.getElementById('ds-truths').value;
  
  if(!name || !desc) {
    alert("Name and description are required.");
    return;
  }
  
  try {
    const res = await api.post('/datasets/create', {
      dataset_name: name,
      description: desc,
      data_samples: samples,
      ground_truths: truths
    });
    alert("创建成功!");
    closeDatasetModal();
    loadDatasets();
  } catch(e) {
    alert("创建失败: " + e.message);
  }
}

window.deleteDataset = async function(datasetId) {
  if(!confirm(`确定要删除数据集 #${datasetId} 吗？此操作不可恢复。`)) return;
  try {
    await api.delete(`/datasets/delete/${datasetId}`);
    alert("删除成功");
    loadDatasets();
  } catch(e) {
    alert("删除失败: " + e.message);
  }
}

async function loadDatasets() {
  const container = document.getElementById('dataset-table-container');
  if(!container) return;
  try {
    const res = await api.get('/datasets/list?skip=0&limit=50');
    const datasets = res.data.datasets || []; 
    renderDatasetTable(datasets, container);
  } catch(e) {
    container.innerHTML = `<p style="color:red;">获取数据失败: ${e.message}</p>`;
    container.classList.remove('loading-skeleton');
  }
}

function renderDatasetTable(datasets, container) {
  if(!datasets || datasets.length === 0) { container.innerHTML = '<p>暂无数据</p>'; return; }
  
  let html = `<div class="table-wrap"><table>
    <thead><tr>
      <th>ID</th><th>名称</th><th>描述</th><th>创建时间</th><th>操作</th>
    </tr></thead><tbody>`;
    
    datasets.forEach(t => {
    html += `<tr>
      <td>${t.id}</td>
      <td>${t.dataset_name}</td>
      <td>${t.description}</td>
      <td>${formatDateTime(t.created_at)}</td>
      <td>
        <button class="btn-text" style="color: #ff4d4f;" onclick="deleteDataset('${t.id}')">删除</button>
      </td>
    </tr>`;
  });
  html += `</tbody></table></div>`;
  container.innerHTML = html;
  container.classList.remove('loading-skeleton');
}

async function DatasetView(container) {
  container.innerHTML = `
    <div class="page-hero page-section-tight">
      <h1 class="page-title">评测基准测试集</h1>
      <p class="page-subtitle">维护用于评测的题目与基准答案，支持快速创建和浏览。数据集页面与任务页共享统一的视觉语言和层级。</p>
    </div>
    <div class="page-actions">
      <button class="btn" onclick="openDatasetModal()">+ Create Dataset</button>
    </div>
    <div class="card">
      <div class="card-header">
        <span>评测基准测试集 (Datasets)</span>
      </div>
      <div class="card-body">
        <div id="dataset-table-container" class="loading-skeleton" style="max-height: 70vh; overflow-y: auto; width: 100%;"></div>
      </div>
    </div>

    <!-- Modal Form -->
    <div id="dataset-modal" class="modal-overlay">
      <div class="modal-sheet">
        <div class="modal-header">
          <div class="modal-kicker">Create Dataset</div>
          <h3 class="modal-title">创建评测基准测试集</h3>
          <p class="modal-desc">录入数据样本与标准答案，供后续任务评估使用。</p>
        </div>
        <div class="form-grid">
          <div class="form-group">
            <label class="form-label" for="ds-name">Dataset Name <sup>*</sup></label>
            <input class="field" type="text" id="ds-name" placeholder="例如: Science QA Benchmark">
          </div>
          <div class="form-group">
            <label class="form-label" for="ds-desc">Description <sup>*</sup></label>
            <input class="field" type="text" id="ds-desc" placeholder="例如: 多文档检索问答测试集">
          </div>
          <div class="form-group">
            <label class="form-label" for="ds-samples">Data Samples</label>
            <textarea class="field" id="ds-samples" placeholder='e.g. [{"query": "..."}]'></textarea>
          </div>
          <div class="form-group">
            <label class="form-label" for="ds-truths">Ground Truths</label>
            <textarea class="field" id="ds-truths" placeholder='e.g. [{"answer": "..."}]'></textarea>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn-text" onclick="closeDatasetModal()">Cancel</button>
          <button class="btn" onclick="submitDataset()">Create</button>
        </div>
      </div>
    </div>
  `;
  loadDatasets();
}

// Bootstrap
window.addEventListener('hashchange', router);
window.addEventListener('DOMContentLoaded', router);
