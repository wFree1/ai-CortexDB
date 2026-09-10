// web/static/app.js
// DataSphere Studio - Navicat Web Edition Controller

(function() {
  'use strict';

  // --- 全局状态 ---
  const state = {
    tabs: [],
    activeTabId: null,
    nextTabSeq: 1,
    tables: [],
    overview: null,
    filterKeyword: ''
  };

  // --- 预置 SQL 模版库 ---
  const SQL_TEMPLATES = {
    'join_query': `-- 1. 多表连接与条件查询 (JOIN & WHERE)\nSELECT \n    e.emp_id,\n    e.name AS 姓名,\n    d.dept_name AS 部门,\n    e.salary AS 薪资,\n    e.is_active AS 在职状态,\n    e.hire_date AS 入职日期\nFROM employees e\nLEFT JOIN departments d ON e.dept_id = d.dept_id\nWHERE e.salary >= 20000.00\nORDER BY e.salary DESC;`,

    'group_agg': `-- 2. 分组统计与聚合筛选 (GROUP BY & HAVING)\nSELECT \n    d.dept_name AS 部门名称,\n    COUNT(*) AS 员工人数,\n    AVG(e.salary) AS 平均薪资,\n    MAX(e.salary) AS 最高薪资\nFROM employees e\nJOIN departments d ON e.dept_id = d.dept_id\nGROUP BY d.dept_name\nHAVING 平均薪资 > 20000;`,

    'rich_types_insert': `-- 3. 工业级全数据类型插入 (BIGINT, DATETIME, BOOL, DOUBLE)\nINSERT INTO employees (\n    emp_id, name, dept_id, salary, is_active, hire_date, created_at\n) VALUES (\n    1006, '孙七', 10, 35000.00, TRUE, '2024-03-01', '2024-03-01 08:30:00'\n);`,

    'create_table': `-- 4. 创建新表 (CREATE TABLE with Types)\nCREATE TABLE IF NOT EXISTS test_orders (\n    order_id BIGINT PRIMARY KEY,\n    user_name VARCHAR(50),\n    amount DOUBLE,\n    is_paid BOOL,\n    created_at DATETIME\n);`,

    'alter_table': `-- 5. 动态修改表结构 (ALTER TABLE)\nALTER TABLE employees ADD COLUMN rank VARCHAR(20);`,

    'like_between': `-- 6. 模糊查询与区间筛选 (LIKE & BETWEEN)\nSELECT * FROM products \nWHERE title LIKE '%智能%'\n  AND price BETWEEN 500.00 AND 2000.00;`
  };

  // --- DOM 引用 ---
  const el = {
    headerDbName: document.getElementById('header-db-name'),
    headerHitRate: document.getElementById('header-hit-rate'),
    btnRunSql: document.getElementById('btn-run-sql'),
    btnNewQuery: document.getElementById('btn-new-query'),
    btnSeedDemo: document.getElementById('btn-seed-demo'),
    btnRefreshAll: document.getElementById('btn-refresh-all'),
    btnTabPlus: document.getElementById('btn-tab-plus'),
    tabsContainer: document.getElementById('tabs-container'),
    viewport: document.getElementById('tab-content-viewport'),
    databaseTree: document.getElementById('database-tree'),
    filterTables: document.getElementById('filter-tables'),
    sidebarTableCount: document.getElementById('sidebar-table-count'),
    metricDbSize: document.getElementById('metric-db-size'),
    metricCachedPages: document.getElementById('metric-cached-pages'),
    metricDirtyPages: document.getElementById('metric-dirty-pages'),
    footerExecStats: document.getElementById('footer-exec-stats')
  };

  // ==========================================================================
  // API 请求函数
  // ==========================================================================

  async function apiGet(endpoint) {
    try {
      const res = await fetch(endpoint);
      return await res.json();
    } catch (err) {
      console.error(`GET ${endpoint} failed:`, err);
      throw err;
    }
  }

  async function apiPost(endpoint, data = {}) {
    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      return await res.json();
    } catch (err) {
      console.error(`POST ${endpoint} failed:`, err);
      throw err;
    }
  }

  // ==========================================================================
  // 数据同步与刷新
  // ==========================================================================

  async function refreshDatabaseMeta() {
    try {
      // 1. 获取全局概览
      const overview = await apiGet('/api/overview');
      state.overview = overview;
      if (overview && overview.buffer_pool) {
        el.headerHitRate.textContent = `命中率: ${overview.buffer_pool.hit_rate_pct}%`;
        el.metricDbSize.textContent = `${overview.file_size_kb} KB`;
        el.metricCachedPages.textContent = `${overview.buffer_pool.cached_pages} / ${overview.buffer_pool.capacity}`;
        el.metricDirtyPages.textContent = `${overview.buffer_pool.dirty_pages} 页`;
      }

      // 2. 获取表列表
      const tablesRes = await apiGet('/api/tables');
      state.tables = tablesRes.tables || [];
      el.sidebarTableCount.textContent = `${state.tables.length} 张表`;

      renderObjectTree();
    } catch (e) {
      console.error("Failed to refresh database metadata:", e);
    }
  }

  // ==========================================================================
  // Navicat 左侧对象导航树渲染 (Object Explorer)
  // ==========================================================================

  function renderObjectTree() {
    const filter = state.filterKeyword.trim().toLowerCase();
    const filtered = state.tables.filter(t => {
      if (!filter) return true;
      if (t.name.toLowerCase().includes(filter)) return true;
      return (t.columns || []).some(c => c.name.toLowerCase().includes(filter));
    });

    if (state.tables.length === 0) {
      el.databaseTree.innerHTML = `
        <div class="empty-grid-placeholder" style="padding: 30px 10px;">
          <span>当前数据库暂无数据表</span>
          <button class="btn btn-secondary" onclick="document.getElementById('btn-seed-demo').click()">一键载入演示数据</button>
        </div>
      `;
      return;
    }

    let html = `
      <div class="tree-node">
        <div class="node-item expanded" id="root-db-node">
          <span class="arrow">▶</span>
          <span class="node-icon">🗄️</span>
          <span class="node-label" style="font-weight: 600; color: #fff;">datasphere</span>
          <span class="node-badge" style="background: rgba(99,102,241,0.2); color: #818cf8;">DB</span>
        </div>
        <div class="node-children open" id="tables-group-node">
    `;

    filtered.forEach(t => {
      const colCount = (t.columns || []).length;
      html += `
        <div class="tree-node" data-table="${t.name}">
          <div class="node-item" onclick="window.DataSphereStudio.toggleNode(this)" ondblclick="window.DataSphereStudio.openTableDataTab('${t.name}')">
            <span class="arrow">▶</span>
            <span class="node-icon">📄</span>
            <span class="node-label">${t.name}</span>
            <span class="node-badge badge-rows">${t.row_count} 行</span>
          </div>
          <div class="node-children">
            <div style="display: flex; gap: 4px; padding: 4px 8px; margin-bottom: 4px;">
              <button class="btn-mini" onclick="window.DataSphereStudio.openTableDataTab('${t.name}')">查看数据</button>
              <button class="btn-mini" onclick="window.DataSphereStudio.openTableSchemaTab('${t.name}')">表结构</button>
            </div>
      `;

      // 字段子树
      (t.columns || []).forEach(c => {
        const isPk = (c.name === t.primary_key);
        html += `
          <div class="node-item" style="padding-left: 12px; font-size: 12px;">
            <span class="node-icon">${isPk ? '🔑' : '🔹'}</span>
            <span class="node-label">${c.name}</span>
            ${isPk ? '<span class="node-badge badge-pk">PK</span>' : ''}
            <span class="node-badge badge-type">${c.type}</span>
          </div>
        `;
      });

      html += `
          </div>
        </div>
      `;
    });

    html += `
        </div>
      </div>
    `;

    el.databaseTree.innerHTML = html;
  }

  // ==========================================================================
  // 多标签页管理器 (Tab Management)
  // ==========================================================================

  function createNewQueryTab(initialSql = null) {
    const id = `tab_query_${Date.now()}_${state.nextTabSeq++}`;
    const defaultSql = (initialSql !== null && initialSql !== undefined) ? initialSql : '';

    const tabObj = {
      id: id,
      title: `查询 ${state.nextTabSeq - 1}`,
      type: 'query',
      sql: defaultSql,
      results: null,
      executionLogs: [],
      activeSubtab: 'grid'
    };

    state.tabs.push(tabObj);
    switchTab(id);
  }

  function openTableDataTab(tableName) {
    const id = `tab_data_${tableName}`;
    let tab = state.tabs.find(t => t.id === id);
    if (!tab) {
      tab = {
        id: id,
        title: `${tableName} [数据]`,
        type: 'table_data',
        tableName: tableName,
        page: 1,
        pageSize: 100,
        data: null
      };
      state.tabs.push(tab);
    }
    switchTab(id);
    loadTableData(tab);
  }

  function openTableSchemaTab(tableName) {
    const id = `tab_schema_${tableName}`;
    let tab = state.tabs.find(t => t.id === id);
    if (!tab) {
      tab = {
        id: id,
        title: `${tableName} [设计]`,
        type: 'table_schema',
        tableName: tableName,
        schema: null
      };
      state.tabs.push(tab);
    }
    switchTab(id);
    loadTableSchema(tab);
  }

  function closeTab(tabId, evt) {
    if (evt) evt.stopPropagation();
    const idx = state.tabs.findIndex(t => t.id === tabId);
    if (idx === -1) return;

    state.tabs.splice(idx, 1);

    if (state.activeTabId === tabId) {
      if (state.tabs.length > 0) {
        const nextActive = state.tabs[Math.max(0, idx - 1)];
        switchTab(nextActive.id);
      } else {
        createNewQueryTab();
      }
    } else {
      renderTabsHeader();
    }
  }

  function switchTab(tabId) {
    state.activeTabId = tabId;
    renderTabsHeader();
    renderTabViewport();
  }

  function renderTabsHeader() {
    let html = '';
    state.tabs.forEach(t => {
      const isActive = (t.id === state.activeTabId);
      let icon = '⚡';
      if (t.type === 'table_data') icon = '📊';
      if (t.type === 'table_schema') icon = '📐';

      html += `
        <div class="tab-btn ${isActive ? 'active' : ''}" onclick="window.DataSphereStudio.switchTab('${t.id}')">
          <span>${icon}</span>
          <span>${t.title}</span>
          <span class="tab-close" onclick="window.DataSphereStudio.closeTab('${t.id}', event)">✕</span>
        </div>
      `;
    });
    el.tabsContainer.innerHTML = html;
  }

  function renderTabViewport() {
    const currentTab = state.tabs.find(t => t.id === state.activeTabId);
    if (!currentTab) return;

    if (currentTab.type === 'query') {
      renderQueryTabContent(currentTab);
    } else if (currentTab.type === 'table_data') {
      renderTableDataContent(currentTab);
    } else if (currentTab.type === 'table_schema') {
      renderTableSchemaContent(currentTab);
    }
  }

  // ==========================================================================
  // SQL 查询视窗渲染 (Query Tab View)
  // ==========================================================================

  function renderQueryTabContent(tab) {
    el.viewport.innerHTML = `
      <div class="tab-pane active" id="pane-${tab.id}">
        <!-- 上部：SQL 编辑器 -->
        <div class="query-editor-container">
          <div class="editor-toolbar">
            <div class="editor-tools-left">
              <select class="select-snippet" onchange="window.DataSphereStudio.insertSnippet(this.value)">
                <option value="">💡 常用 SQL 模版库...</option>
                <option value="join_query">多表连接与条件查询 (JOIN)</option>
                <option value="group_agg">分组统计与 HAVING 聚合</option>
                <option value="like_between">模糊查询与区间筛选 (LIKE & BETWEEN)</option>
                <option value="rich_types_insert">全数据类型插入 (BIGINT, BOOL, DATE)</option>
                <option value="create_table">新建数据表 (CREATE TABLE)</option>
                <option value="alter_table">修改表字段 (ALTER TABLE)</option>
              </select>

              <button class="btn-mini" onclick="window.DataSphereStudio.formatSql()">格式化</button>
              <button class="btn-mini" onclick="window.DataSphereStudio.clearSql()">清空</button>
            </div>

            <div class="editor-stats-right">
              <span id="tab-cost-indicator">${tab.results ? `耗时: ${tab.results.total_execution_time_ms} ms` : '快捷键: Ctrl + Enter 执行'}</span>
            </div>
          </div>

          <div class="editor-textarea-wrapper">
            <textarea class="sql-textarea" id="sql-input-${tab.id}" spellcheck="false" placeholder="在此输入 SQL 语句 (支持单条或多条以分号分隔)...">${tab.sql || ''}</textarea>
          </div>
        </div>

        <!-- 下部：结果区 (Grid / Explain / Messages) -->
        <div class="results-panel">
          <div class="results-tab-header">
            <button class="subtab-btn ${tab.activeSubtab === 'grid' ? 'active' : ''}" onclick="window.DataSphereStudio.switchSubtab('${tab.id}', 'grid')">
              📊 结果网格 ${tab.results && tab.results.results && tab.results.results[0] ? `(${tab.results.results[0].row_count} 行)` : ''}
            </button>
            <button class="subtab-btn ${tab.activeSubtab === 'explain' ? 'active' : ''}" onclick="window.DataSphereStudio.switchSubtab('${tab.id}', 'explain')">
              🧠 逻辑执行计划 (Explain)
            </button>
            <button class="subtab-btn ${tab.activeSubtab === 'messages' ? 'active' : ''}" onclick="window.DataSphereStudio.switchSubtab('${tab.id}', 'messages')">
              📝 执行日志 ${tab.executionLogs && tab.executionLogs.length > 0 ? `(${tab.executionLogs.length})` : ''}
            </button>
          </div>

          <div class="results-content-area" id="results-content-${tab.id}">
            <!-- 动态填充子面板 -->
          </div>
        </div>
      </div>
    `;

    // 绑定当前 textarea 输入事件以保存当前编辑状态
    const ta = document.getElementById(`sql-input-${tab.id}`);
    if (ta) {
      ta.addEventListener('input', (e) => {
        tab.sql = e.target.value;
      });
      ta.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
          e.preventDefault();
          executeCurrentQuery();
        }
      });
    }

    renderQueryResultsSubpane(tab);
  }

  function renderQueryResultsSubpane(tab) {
    const container = document.getElementById(`results-content-${tab.id}`);
    if (!container) return;

    if (!tab.results) {
      container.innerHTML = `
        <div class="empty-grid-placeholder">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <polygon points="5 3 19 12 5 21 5 3"></polygon>
          </svg>
          <span>点击上方「运行查询」或按 Ctrl + Enter 查看数据结果</span>
        </div>
      `;
      return;
    }

    const firstResult = tab.results.results && tab.results.results[0];

    // 1) 结果网格 (Data Grid)
    if (tab.activeSubtab === 'grid') {
      if (!firstResult) {
        container.innerHTML = `<div class="empty-grid-placeholder"><span>无查询结果</span></div>`;
        return;
      }
      if (!firstResult.success) {
        container.innerHTML = `
          <div class="messages-log-box log-error">
            ❌ 执行失败：\n${firstResult.error || '未知错误'}
          </div>
        `;
        return;
      }

      if (!firstResult.data || firstResult.data.length === 0) {
        container.innerHTML = `
          <div class="messages-log-box log-success">
            ✅ 执行成功：${firstResult.message || '操作成功完成 (0 行返回)'}\n耗时: ${firstResult.execution_time_ms} ms
          </div>
        `;
        return;
      }

      container.innerHTML = buildSpreadsheetGridHTML(firstResult.columns, firstResult.data);
      return;
    }

    // 2) 执行计划 (Explain Plan)
    if (tab.activeSubtab === 'explain') {
      if (firstResult && firstResult.explain_plan) {
        container.innerHTML = `
          <div class="explain-tree-box">${escapeHtml(firstResult.explain_plan)}</div>
        `;
      } else {
        container.innerHTML = `
          <div class="empty-grid-placeholder">
            <span>当前语句无逻辑执行计划输出 (通常仅 SELECT 语句提供优化器计划)</span>
          </div>
        `;
      }
      return;
    }

    // 3) 日志信息 (Messages)
    if (tab.activeSubtab === 'messages') {
      const logsList = tab.executionLogs || [];
      if (logsList.length === 0) {
        container.innerHTML = `
          <div class="empty-grid-placeholder">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
            </svg>
            <span>暂无执行日志，点击「运行查询」后将在此累积记录全部历史执行记录</span>
          </div>
        `;
        return;
      }

      let html = `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 16px; background: #151a26; border-bottom: 1px solid var(--border-subtle); position: sticky; top: 0; z-index: 5;">
          <span style="font-size: 12px; color: var(--text-dim);">
            📜 累积执行历史: <strong style="color: var(--accent-cyan);">${logsList.length}</strong> 次会话
          </span>
          <button class="btn-mini" onclick="window.DataSphereStudio.clearTabLogs('${tab.id}')">🗑️ 清空历史日志</button>
        </div>
        <div class="messages-log-box" id="log-box-${tab.id}">
      `;

      logsList.forEach((entry, eIdx) => {
        html += `
          <div class="log-history-card">
            <div class="log-history-header">
              <span style="color: #38bdf8; font-weight: 600;">
                #${eIdx + 1} &bull; ${entry.time}
              </span>
              <span style="color: var(--text-dim); font-size: 11px;">
                ${entry.total_statements} 条语句 &bull; 耗时 ${entry.total_execution_time_ms} ms
              </span>
            </div>
        `;

        (entry.results || []).forEach((r, idx) => {
          const isOk = r.success;
          html += `
            <div style="margin-top: 6px; padding: 8px 10px; background: rgba(0,0,0,0.3); border-radius: 4px; border-left: 3px solid ${isOk ? '#10b981' : '#ef4444'};">
              <div style="color: #e2e8f0; font-family: var(--font-mono); font-size: 12px; white-space: pre-wrap; margin-bottom: 4px;">${escapeHtml(r.sql)}</div>
              <div style="font-size: 11.5px;">
                ${isOk 
                  ? `<span style="color: #34d399; font-weight: 600;">[OK 成功]</span> <span style="color: var(--text-dim); margin-left: 6px;">耗时: ${r.execution_time_ms} ms | ${escapeHtml(r.message || `${r.row_count} 行受影响/返回`)}</span>`
                  : `<span style="color: #f87171; font-weight: 600;">[ERROR 失败]</span> <span style="color: #fca5a5; margin-left: 6px;">${escapeHtml(r.error)}</span>`
                }
              </div>
            </div>
          `;
        });

        html += `</div>`;
      });

      html += `</div>`;
      container.innerHTML = html;

      setTimeout(() => {
        const box = document.getElementById(`log-box-${tab.id}`);
        if (box) box.scrollTop = box.scrollHeight;
      }, 20);
      return;
    }
  }

  // ==========================================================================
  // 表数据视图 (Table Data View)
  // ==========================================================================

  async function loadTableData(tab) {
    try {
      const res = await apiGet(`/api/table/${tab.tableName}/data?limit=${tab.pageSize}&offset=${(tab.page - 1) * tab.pageSize}`);
      tab.data = res;
      renderTableDataContent(tab);
    } catch (err) {
      console.error(err);
    }
  }

  function renderTableDataContent(tab) {
    if (!tab.data) {
      el.viewport.innerHTML = `<div class="empty-grid-placeholder"><span>加载表数据中...</span></div>`;
      return;
    }

    const cols = tab.data.columns || [];
    const colNames = tab.data.column_names || cols.map(c => c.name);
    const rows = tab.data.rows || [];

    el.viewport.innerHTML = `
      <div class="tab-pane active" style="padding: 0;">
        <div class="editor-toolbar" style="background: #141926; height: 38px;">
          <div class="editor-tools-left">
            <span style="font-weight: 600; color: #fff; font-size: 13px;">数据表: ${tab.tableName}</span>
            <span class="badge-rows" style="margin-left: 8px;">共 ${tab.data.total_rows} 条记录</span>
            <button class="btn-mini" onclick="window.DataSphereStudio.refreshTableData('${tab.tableName}')">🔄 刷新</button>
          </div>
          <div class="editor-stats-right">
            <span>查询耗时: ${tab.data.execution_time_ms} ms</span>
          </div>
        </div>
        <div class="results-content-area" style="flex: 1;">
          ${buildSpreadsheetGridHTML(colNames, rows, cols)}
        </div>
      </div>
    `;
  }

  // ==========================================================================
  // 表结构设计视图 (Table Schema / Design View)
  // ==========================================================================

  async function loadTableSchema(tab) {
    try {
      const res = await apiGet(`/api/table/${tab.tableName}/schema`);
      tab.schema = res;
      renderTableSchemaContent(tab);
    } catch (err) {
      console.error(err);
    }
  }

  function renderTableSchemaContent(tab) {
    if (!tab.schema) {
      el.viewport.innerHTML = `<div class="empty-grid-placeholder"><span>加载表结构中...</span></div>`;
      return;
    }

    const columns = tab.schema.columns || [];

    let html = `
      <div class="tab-pane active" style="padding: 0;">
        <div class="editor-toolbar" style="background: #141926; height: 38px;">
          <div class="editor-tools-left">
            <span style="font-weight: 600; color: #fff; font-size: 13px;">表结构设计: ${tab.tableName}</span>
            <span class="badge-rows" style="margin-left: 8px;">主键: ${tab.schema.primary_key || '无'}</span>
          </div>
          <div class="editor-stats-right">
            <button class="btn-mini" onclick="window.DataSphereStudio.openTableDataTab('${tab.tableName}')">查看数据内容</button>
          </div>
        </div>

        <div class="results-content-area" style="flex: 1; padding: 14px;">
          <table class="navicat-grid" style="border: 1px solid var(--border-subtle); border-radius: 6px; overflow: hidden;">
            <thead>
              <tr>
                <th class="th-rownum">#</th>
                <th>字段名称 (Field)</th>
                <th>数据类型 (Type)</th>
                <th>主键 (Key)</th>
                <th>可为空 (Null)</th>
                <th>说明 (Comment)</th>
              </tr>
            </thead>
            <tbody>
    `;

    columns.forEach((col, idx) => {
      html += `
        <tr>
          <td class="td-rownum">${idx + 1}</td>
          <td style="font-weight: 600; color: #fff;">${col.name}</td>
          <td><span class="node-badge badge-type">${col.type}</span></td>
          <td>${col.is_primary_key ? '<span class="node-badge badge-pk">PRIMARY KEY</span>' : '-'}</td>
          <td>${col.nullable ? 'YES' : 'NO'}</td>
          <td style="color: var(--text-dim);">${col.is_primary_key ? '唯一标识主键' : ''}</td>
        </tr>
      `;
    });

    html += `
            </tbody>
          </table>
        </div>
      </div>
    `;

    el.viewport.innerHTML = html;
  }

  // ==========================================================================
  // 通用 Navicat 风格电子表格网格 HTML 生成器 (Spreadsheet Grid)
  // ==========================================================================

  function buildSpreadsheetGridHTML(columns, rows, colDefs = []) {
    if (!columns || columns.length === 0) {
      return `<div class="empty-grid-placeholder"><span>查询成功，无返回数据列</span></div>`;
    }

    const typeMap = {};
    colDefs.forEach(c => { typeMap[c.name] = c.type; });

    let html = `
      <table class="navicat-grid">
        <thead>
          <tr>
            <th class="th-rownum">#</th>
    `;

    columns.forEach(col => {
      const typeStr = typeMap[col] || guessTypeFromRows(rows, col);
      html += `
        <th>
          <div class="col-header-info">
            <span>${escapeHtml(col)}</span>
            ${typeStr ? `<span class="col-header-type">${typeStr}</span>` : ''}
          </div>
        </th>
      `;
    });

    html += `
          </tr>
        </thead>
        <tbody>
    `;

    rows.forEach((row, rIdx) => {
      html += `
        <tr>
          <td class="td-rownum">${rIdx + 1}</td>
      `;

      columns.forEach(col => {
        const val = row[col];
        html += `<td>${formatCellValue(val)}</td>`;
      });

      html += `</tr>`;
    });

    html += `
        </tbody>
      </table>
    `;

    return html;
  }

  function guessTypeFromRows(rows, colName) {
    for (let r of rows) {
      if (r[colName] !== null && r[colName] !== undefined) {
        const v = r[colName];
        if (typeof v === 'boolean') return 'BOOL';
        if (typeof v === 'number') return Number.isInteger(v) ? 'INT' : 'DOUBLE';
        if (typeof v === 'string') {
          if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return 'DATE';
          if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(v)) return 'DATETIME';
          return 'VARCHAR';
        }
      }
    }
    return '';
  }

  function formatCellValue(val) {
    if (val === null || val === undefined) {
      return `<span class="badge-null">NULL</span>`;
    }
    if (typeof val === 'boolean') {
      return val ? `<span class="badge-bool-true">TRUE</span>` : `<span class="badge-bool-false">FALSE</span>`;
    }
    if (typeof val === 'object') {
      return `<span style="color:#a855f7;">${escapeHtml(JSON.stringify(val))}</span>`;
    }
    return escapeHtml(String(val));
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ==========================================================================
  // 执行 SQL
  // ==========================================================================

  async function executeCurrentQuery() {
    const currentTab = state.tabs.find(t => t.id === state.activeTabId);
    if (!currentTab || currentTab.type !== 'query') return;

    const sqlInput = currentTab.sql.trim();
    if (!sqlInput) {
      alert("请输入有效的 SQL 语句！");
      return;
    }

    el.btnRunSql.disabled = true;
    el.btnRunSql.innerHTML = `<span>⏳ 执行中...</span>`;
    el.footerExecStats.textContent = '执行中...';

    try {
      const res = await apiPost('/api/execute', { sql: sqlInput });
      currentTab.results = res;

      // 累积历史日志
      if (!currentTab.executionLogs) {
        currentTab.executionLogs = [];
      }
      currentTab.executionLogs.push({
        id: Date.now(),
        time: new Date().toLocaleTimeString(),
        total_statements: res.total_statements,
        total_execution_time_ms: res.total_execution_time_ms,
        results: res.results
      });

      el.footerExecStats.textContent = `执行完成 (${res.total_execution_time_ms} ms, 共 ${res.total_statements} 语句)`;

      // 如果执行了 DDL 或 DML（更新/删除/插入/建表），自动刷新元数据
      const isMutating = /create|alter|drop|truncate|insert|update|delete/i.test(sqlInput);
      if (isMutating) {
        await refreshDatabaseMeta();
      }

      renderQueryTabContent(currentTab);
    } catch (err) {
      if (!currentTab.executionLogs) {
        currentTab.executionLogs = [];
      }
      currentTab.executionLogs.push({
        id: Date.now(),
        time: new Date().toLocaleTimeString(),
        total_statements: 1,
        total_execution_time_ms: 0,
        results: [{
          sql: sqlInput,
          success: false,
          error: err.message || String(err),
          execution_time_ms: 0
        }]
      });

      alert(`执行出错: ${err.message || err}`);
      el.footerExecStats.textContent = '执行出错';
      renderQueryTabContent(currentTab);
    } finally {
      el.btnRunSql.disabled = false;
      el.btnRunSql.innerHTML = `
        <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
          <polygon points="5 3 19 12 5 21 5 3"></polygon>
        </svg>
        运行查询
      `;
    }
  }

  // ==========================================================================
  // 全局暴露给 HTML 内联事件的函数
  // ==========================================================================

  window.DataSphereStudio = {
    switchTab: (tabId) => switchTab(tabId),
    closeTab: (tabId, evt) => closeTab(tabId, evt),
    openTableDataTab: (tableName) => openTableDataTab(tableName),
    openTableSchemaTab: (tableName) => openTableSchemaTab(tableName),
    refreshTableData: (tableName) => {
      const tab = state.tabs.find(t => t.id === `tab_data_${tableName}`);
      if (tab) loadTableData(tab);
    },
    clearTabLogs: (tabId) => {
      const tab = state.tabs.find(t => t.id === tabId);
      if (tab) {
        tab.executionLogs = [];
        renderQueryTabContent(tab);
      }
    },
    switchSubtab: (tabId, subtabName) => {
      const tab = state.tabs.find(t => t.id === tabId);
      if (tab) {
        tab.activeSubtab = subtabName;
        renderQueryTabContent(tab);
      }
    },
    insertSnippet: (key) => {
      if (!key || !SQL_TEMPLATES[key]) return;
      const currentTab = state.tabs.find(t => t.id === state.activeTabId);
      if (!currentTab || currentTab.type !== 'query') return;

      currentTab.sql = SQL_TEMPLATES[key];
      const ta = document.getElementById(`sql-input-${currentTab.id}`);
      if (ta) ta.value = currentTab.sql;
    },
    formatSql: () => {
      const currentTab = state.tabs.find(t => t.id === state.activeTabId);
      if (!currentTab || currentTab.type !== 'query') return;
      let s = currentTab.sql;
      // 简单关键字大写美化
      const keywords = ["SELECT", "FROM", "WHERE", "JOIN", "LEFT JOIN", "RIGHT JOIN", "CROSS JOIN", "ON", "GROUP BY", "HAVING", "ORDER BY", "LIMIT", "OFFSET", "INSERT INTO", "VALUES", "UPDATE", "SET", "DELETE FROM", "CREATE TABLE", "ALTER TABLE"];
      keywords.forEach(kw => {
        const re = new RegExp(`\\b${kw}\\b`, 'gi');
        s = s.replace(re, kw);
      });
      currentTab.sql = s;
      const ta = document.getElementById(`sql-input-${currentTab.id}`);
      if (ta) ta.value = s;
    },
    clearSql: () => {
      const currentTab = state.tabs.find(t => t.id === state.activeTabId);
      if (!currentTab || currentTab.type !== 'query') return;
      currentTab.sql = '';
      const ta = document.getElementById(`sql-input-${currentTab.id}`);
      if (ta) ta.value = '';
    },
    toggleNode: (nodeItemEl) => {
      nodeItemEl.classList.toggle('expanded');
      const children = nodeItemEl.nextElementSibling;
      if (children && children.classList.contains('node-children')) {
        children.classList.toggle('open');
      }
    }
  };

  // ==========================================================================
  // 事件监听绑定与初始化
  // ==========================================================================

  el.btnRunSql.addEventListener('click', executeCurrentQuery);
  el.btnNewQuery.addEventListener('click', () => createNewQueryTab());
  el.btnTabPlus.addEventListener('click', () => createNewQueryTab());

  el.btnRefreshAll.addEventListener('click', () => {
    refreshDatabaseMeta();
    el.footerExecStats.textContent = '数据库对象树已刷新';
  });

  el.btnSeedDemo.addEventListener('click', async () => {
    if (confirm("确定载入演示数据库吗？将初始化 departments、employees、products、orders 等丰富示例表。")) {
      try {
        const res = await apiPost('/api/seed_demo');
        alert(res.message || "演示库已成功载入！");
        await refreshDatabaseMeta();
        createNewQueryTab(SQL_TEMPLATES['join_query']);
      } catch (e) {
        alert("载入失败: " + e.message);
      }
    }
  });

  el.filterTables.addEventListener('input', (e) => {
    state.filterKeyword = e.target.value;
    renderObjectTree();
  });

  // 全局键盘快捷键
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      executeCurrentQuery();
    }
  });

  // 启动初始化
  async function init() {
    await refreshDatabaseMeta();
    // 默认打开一个初始查询标签页
    createNewQueryTab();
  }

  init();
})();
