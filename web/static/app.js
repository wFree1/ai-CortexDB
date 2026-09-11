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
    filterKeyword: '',
    databases: ['datasphere'],
    currentDatabase: 'datasphere',
    databasesDetail: [],
    expandedDbs: new Set()
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
    headerDbSelect: document.getElementById('header-db-select'),
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
      // 1. 获取全局概览与多数据库元数据详情
      const [overview, dbRes] = await Promise.all([
        apiGet('/api/overview'),
        apiGet('/api/databases')
      ]);

      state.overview = overview;
      if (overview) {
        if (overview.current_database) {
          state.currentDatabase = overview.current_database;
        }
        if (overview.databases && Array.isArray(overview.databases)) {
          state.databases = overview.databases;
        }
        if (overview.buffer_pool) {
          el.headerHitRate.textContent = `命中率: ${overview.buffer_pool.hit_rate_pct}%`;
          el.metricDbSize.textContent = `${overview.file_size_kb} KB`;
          el.metricCachedPages.textContent = `${overview.buffer_pool.cached_pages} / ${overview.buffer_pool.capacity}`;
          el.metricDirtyPages.textContent = `${overview.buffer_pool.dirty_pages} 页`;
        }
      }

      if (dbRes) {
        if (dbRes.current_database) state.currentDatabase = dbRes.current_database;
        if (dbRes.databases) state.databases = dbRes.databases;
        if (dbRes.databases_detail) state.databasesDetail = dbRes.databases_detail;
      }

      renderDatabaseSelect();

      // 2. 获取当前活动库表列表 (用于主工作区查询与模版)
      const tablesRes = await apiGet('/api/tables');
      state.tables = tablesRes.tables || [];

      // 计算所有数据库的总表数
      let totalTables = 0;
      if (state.databasesDetail && state.databasesDetail.length > 0) {
        totalTables = state.databasesDetail.reduce((acc, d) => acc + (d.table_count || (d.tables ? d.tables.length : 0)), 0);
      } else {
        totalTables = state.tables.length;
      }
      const totalDbs = (state.databases && state.databases.length) || 1;
      el.sidebarTableCount.textContent = `${totalTables} 张表 · ${totalDbs} 库`;

      renderObjectTree();
    } catch (e) {
      console.error("Failed to refresh database metadata:", e);
    }
  }

  function renderDatabaseSelect() {
    if (!el.headerDbSelect) return;
    const dbs = state.databases && state.databases.length > 0 ? state.databases : ['datasphere'];
    let html = '';
    dbs.forEach(dbName => {
      const selected = (dbName === state.currentDatabase) ? 'selected' : '';
      html += `<option value="${escapeHtml(dbName)}" ${selected}>${escapeHtml(dbName)}</option>`;
    });
    el.headerDbSelect.innerHTML = html;
  }

  // ==========================================================================
  // Navicat 左侧对象导航树渲染 (Object Explorer - 多数据库完整支持)
  // ==========================================================================

  function toggleDbNode(dbName, nodeItemEl) {
    nodeItemEl.classList.toggle('expanded');
    const children = nodeItemEl.nextElementSibling;
    if (children && children.classList.contains('node-children')) {
      children.classList.toggle('open');
      if (children.classList.contains('open')) {
        state.expandedDbs.add(dbName);
      } else {
        state.expandedDbs.delete(dbName);
      }
    }
  }

  async function switchDatabase(targetDb) {
    if (!targetDb) return;
    if (targetDb === state.currentDatabase) {
      el.footerExecStats.textContent = `当前已在数据库: ${targetDb}`;
      return;
    }
    el.footerExecStats.textContent = `正在切换至数据库: ${targetDb}...`;
    try {
      const res = await apiPost('/api/database/switch', { database: targetDb });
      if (res.success) {
        state.currentDatabase = res.current_database || targetDb;
        state.expandedDbs.add(state.currentDatabase);
        await refreshDatabaseMeta();
        el.footerExecStats.textContent = `已成功切换至数据库: ${state.currentDatabase}`;
      } else {
        alert("切换数据库失败: " + (res.error || res.message));
      }
    } catch (err) {
      alert("切换数据库异常: " + err.message);
    }
  }

  function renderObjectTree() {
    let dbList = state.databasesDetail;
    if (!dbList || dbList.length === 0) {
      const dbs = (state.databases && state.databases.length > 0) ? state.databases : ['datasphere'];
      dbList = dbs.map(name => ({
        name: name,
        is_active: (name === (state.currentDatabase || 'datasphere')),
        table_count: (name === state.currentDatabase) ? state.tables.length : 0,
        tables: (name === state.currentDatabase) ? state.tables : []
      }));
    }

    const filter = state.filterKeyword.trim().toLowerCase();
    let html = '';

    dbList.forEach(db => {
      const isActive = (db.name === state.currentDatabase);
      const isExpanded = state.expandedDbs.has(db.name) || isActive || Boolean(filter);
      const tables = db.tables || [];

      const filteredTables = tables.filter(t => {
        if (!filter) return true;
        if (t.name.toLowerCase().includes(filter)) return true;
        return (t.columns || []).some(c => c.name.toLowerCase().includes(filter));
      });

      // 如果有过滤条件且当前库没有匹配项，则跳过展示
      if (filter && filteredTables.length === 0 && !db.name.toLowerCase().includes(filter)) {
        return;
      }

      html += `
        <div class="tree-node db-root-node" data-dbname="${escapeHtml(db.name)}" style="margin-bottom: 6px;">
          <div class="node-item ${isExpanded ? 'expanded' : ''} ${isActive ? 'active-db-node' : ''}" 
               onclick="window.DataSphereStudio.toggleDbNode('${escapeHtml(db.name)}', this)" 
               ondblclick="window.DataSphereStudio.switchDatabase('${escapeHtml(db.name)}')"
               title="${isActive ? '当前激活数据库' : '双击切换至此数据库'}">
            <span class="arrow">▶</span>
            <span class="node-icon">${isActive ? '🗄️' : '📁'}</span>
            <span class="node-label" style="font-weight: 600; color: ${isActive ? '#60a5fa' : '#cbd5e1'}; font-size: 13px;">${escapeHtml(db.name)}</span>
            ${isActive ? `
              <span class="node-badge badge-active-db" title="当前激活的工作数据库">当前</span>
            ` : `
              <button class="btn-mini btn-switch-db" onclick="event.stopPropagation(); window.DataSphereStudio.switchDatabase('${escapeHtml(db.name)}')" title="切换到此数据库">切库</button>
            `}
            <span class="node-badge" style="background: rgba(255,255,255,0.06); color: var(--text-dim); margin-left: 2px;">${db.table_count ?? tables.length} 表</span>
          </div>
          <div class="node-children ${isExpanded ? 'open' : ''}" id="db-children-${escapeHtml(db.name)}">
      `;

      if (filteredTables.length === 0) {
        if (filter) {
          html += `<div style="padding: 6px 14px; color: var(--text-dim); font-size: 11.5px; font-style: italic;">无匹配数据表</div>`;
        } else {
          html += `
            <div style="padding: 10px 12px; text-align: center; color: var(--text-dim); font-size: 11.5px;">
              <span>暂无数据表</span>
              ${isActive ? `
                <div style="margin-top: 6px;">
                  <button class="btn btn-secondary" onclick="document.getElementById('btn-seed-demo').click()" style="padding: 2px 8px; font-size: 11px;">载入演示数据</button>
                </div>
              ` : ''}
            </div>
          `;
        }
      } else {
        filteredTables.forEach(t => {
          html += `
            <div class="tree-node" data-table="${escapeHtml(t.name)}">
              <div class="node-item" onclick="window.DataSphereStudio.toggleNode(this)" ondblclick="window.DataSphereStudio.openTableDataTab('${escapeHtml(t.name)}', '${escapeHtml(db.name)}')">
                <span class="arrow">▶</span>
                <span class="node-icon">📄</span>
                <span class="node-label">${escapeHtml(t.name)}</span>
                <span class="node-badge badge-rows">${t.row_count || 0} 行</span>
              </div>
              <div class="node-children">
                <div style="display: flex; gap: 4px; padding: 4px 8px; margin-bottom: 4px;">
                  <button class="btn-mini" onclick="window.DataSphereStudio.openTableDataTab('${escapeHtml(t.name)}', '${escapeHtml(db.name)}')">查看数据</button>
                  <button class="btn-mini" onclick="window.DataSphereStudio.openTableSchemaTab('${escapeHtml(t.name)}', '${escapeHtml(db.name)}')">表结构</button>
                </div>
          `;

          (t.columns || []).forEach(c => {
            const isPk = (c.name === t.primary_key);
            html += `
              <div class="node-item" style="padding-left: 12px; font-size: 12px;">
                <span class="node-icon">${isPk ? '🔑' : '🔹'}</span>
                <span class="node-label">${escapeHtml(c.name)}</span>
                ${isPk ? '<span class="node-badge badge-pk">PK</span>' : ''}
                <span class="node-badge badge-type">${escapeHtml(c.type)}</span>
              </div>
            `;
          });

          html += `
              </div>
            </div>
          `;
        });
      }

      html += `
          </div>
        </div>
      `;
    });

    if (!html) {
      html = `<div style="padding: 20px; text-align: center; color: var(--text-dim); font-size: 12px;">未匹配到任何数据库或数据表</div>`;
    }

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

  async function openTableDataTab(tableName, dbName = null) {
    if (dbName && dbName !== state.currentDatabase) {
      await switchDatabase(dbName);
    }
    const id = `tab_data_${dbName || state.currentDatabase}_${tableName}`;
    let tab = state.tabs.find(t => t.id === id);
    if (!tab) {
      tab = {
        id: id,
        title: `${tableName} [数据]`,
        type: 'table_data',
        tableName: tableName,
        database: dbName || state.currentDatabase,
        page: 1,
        pageSize: 100,
        data: null
      };
      state.tabs.push(tab);
    }
    switchTab(id);
    loadTableData(tab);
  }

  async function openTableSchemaTab(tableName, dbName = null) {
    if (dbName && dbName !== state.currentDatabase) {
      await switchDatabase(dbName);
    }
    const id = `tab_schema_${dbName || state.currentDatabase}_${tableName}`;
    let tab = state.tabs.find(t => t.id === id);
    if (!tab) {
      tab = {
        id: id,
        title: `${tableName} [设计]`,
        type: 'table_schema',
        tableName: tableName,
        database: dbName || state.currentDatabase,
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

      // 实时感知当前活动数据库变更
      if (res.current_database && res.current_database !== state.currentDatabase) {
        state.currentDatabase = res.current_database;
      }
      if (res.databases && Array.isArray(res.databases)) {
        state.databases = res.databases;
      }
      renderDatabaseSelect();

      // 如果执行了 DDL 或 DML 或数据库操作（更新/删除/插入/建表/切库），自动刷新元数据
      const isMutating = /create|alter|drop|truncate|insert|update|delete|use/i.test(sqlInput);
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
  // 编辑器辅助与外部调用控制
  // ==========================================================================

  function insertSqlToEditor(sql) {
    if (!sql) return;
    let currentTab = state.tabs.find(t => t.id === state.activeTabId && t.type === 'query');
    if (!currentTab) {
      currentTab = state.tabs.find(t => t.type === 'query');
      if (currentTab) {
        switchTab(currentTab.id);
      } else {
        createNewQueryTab(sql);
        currentTab = state.tabs.find(t => t.id === state.activeTabId && t.type === 'query');
      }
    }
    if (currentTab) {
      currentTab.sql = sql;
      const ta = document.getElementById(`sql-input-${currentTab.id}`);
      if (ta) {
        ta.value = sql;
        ta.focus();
      }
    }
    el.footerExecStats.textContent = 'SQL 已填入当前查询窗口';
  }

  async function runSqlDirectly(sql) {
    if (!sql) return;
    insertSqlToEditor(sql);
    setTimeout(() => {
      executeCurrentQuery();
    }, 60);
  }

  // ==========================================================================
  // 全局暴露给 HTML 内联事件的函数
  // ==========================================================================

  window.DataSphereStudio = {
    switchTab: (tabId) => switchTab(tabId),
    closeTab: (tabId, evt) => closeTab(tabId, evt),
    openTableDataTab: (tableName, dbName) => openTableDataTab(tableName, dbName),
    openTableSchemaTab: (tableName, dbName) => openTableSchemaTab(tableName, dbName),
    refreshTableData: (tableName) => {
      const tab = state.tabs.find(t => (t.type === 'table_data' && t.tableName === tableName) || t.id === state.activeTabId);
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
    insertSql: (sql) => insertSqlToEditor(sql),
    runSqlDirect: (sql) => runSqlDirectly(sql),
    toggleNode: (nodeItemEl) => {
      nodeItemEl.classList.toggle('expanded');
      const children = nodeItemEl.nextElementSibling;
      if (children && children.classList.contains('node-children')) {
        children.classList.toggle('open');
      }
    },
    toggleDbNode: (dbName, nodeItemEl) => toggleDbNode(dbName, nodeItemEl),
    switchDatabase: (dbName) => switchDatabase(dbName)
  };

  // 全局兼容易用别名
  window.Studio = window.DataSphereStudio;

  // ==========================================================================
  // CortexDB Native AI Copilot Controller
  // ==========================================================================
  const copilotEl = {
    btnToggle: document.getElementById('btn-toggle-copilot'),
    drawer: document.getElementById('copilot-drawer'),
    btnClose: document.getElementById('btn-close-copilot'),
    chatContainer: document.getElementById('copilot-chat-container'),
    input: document.getElementById('copilot-input'),
    btnSend: document.getElementById('btn-send-copilot'),
    approvalBanner: document.getElementById('copilot-approval-banner'),
    approvalDesc: document.getElementById('approval-desc'),
    btnConfirmApproval: document.getElementById('btn-confirm-approval'),
    btnRejectApproval: document.getElementById('btn-reject-approval')
  };

  let currentPendingApprovalId = null;

  function toggleCopilot(forceOpen = null) {
    if (!copilotEl.drawer) return;
    if (forceOpen === true) {
      copilotEl.drawer.classList.remove('closed');
    } else if (forceOpen === false) {
      copilotEl.drawer.classList.add('closed');
    } else {
      copilotEl.drawer.classList.toggle('closed');
    }
  }

  function appendUserMessage(text) {
    const msg = document.createElement('div');
    msg.className = 'chat-msg user';
    msg.innerHTML = `<div class="chat-bubble-user">${escapeHtml(text)}</div>`;
    copilotEl.chatContainer.appendChild(msg);
    copilotEl.chatContainer.scrollTop = copilotEl.chatContainer.scrollHeight;
  }

  function appendAgentLoading() {
    const id = 'agent-loading-' + Date.now();
    const msg = document.createElement('div');
    msg.className = 'chat-msg agent';
    msg.id = id;
    msg.innerHTML = `
      <div class="chat-bubble-agent">
        <div style="display:flex; align-items:center; gap:8px; color:#a5b4fc;">
          <span style="font-size:14px;">⚡</span>
          <span>CortexDB 内核正在分析意图、召回 Schema 并前置编译校验...</span>
        </div>
      </div>
    `;
    copilotEl.chatContainer.appendChild(msg);
    copilotEl.chatContainer.scrollTop = copilotEl.chatContainer.scrollHeight;
    return id;
  }

  function insertSqlToEditor(sql) {
    const activeTab = state.tabs.find(t => t.id === state.activeTabId && t.type === 'query');
    if (activeTab) {
      activeTab.sql = sql;
      const ta = document.getElementById(`editor-textarea-${activeTab.id}`);
      if (ta) ta.value = sql;
    } else {
      createNewQueryTab(sql);
    }
    el.footerExecStats.textContent = 'SQL 已填入当前查询窗口';
  }

  function runSqlDirectly(sql) {
    insertSqlToEditor(sql);
    executeCurrentQuery();
  }

  window.Studio = window.Studio || {};
  window.Studio.insertSql = insertSqlToEditor;
  window.Studio.runSqlDirect = runSqlDirectly;

  function renderAgentTraceTimeline(data) {
    const steps = [];
    steps.push({ name: '意图推断 (Intent)', status: 'success', time: data.intent || 'query' });
    steps.push({ name: 'Schema 动态精简检索', status: 'success', time: 'Catalog' });

    const val = data.validation || {};
    if (val.valid) {
      const retries = data.retry_count || 0;
      if (retries > 0) {
        steps.push({ name: `自愈修复通过 (Recovery Retried: ${retries})`, status: 'warn', time: 'Healed' });
      } else {
        steps.push({ name: '内核编译前置质检 (Compiler Pre-check)', status: 'success', time: 'PASS' });
      }
    } else {
      steps.push({ name: '内核编译前置质检 (Compiler Pre-check)', status: 'failed', time: 'FAIL' });
    }

    if (data.explain) {
      steps.push({ name: '逻辑与物理执行计划 (Explain)', status: 'success', time: 'Planner' });
    }

    if (data.execution_result) {
      const ms = data.execution_result.latency_ms || 0;
      const rows = data.execution_result.data ? data.execution_result.data.length : 0;
      steps.push({ name: `物理存储引擎执行成功 (${rows} 行)`, status: 'success', time: `${ms} ms` });
    } else if (data.approval_required) {
      steps.push({ name: '安全门禁拦截，等待管理员人工审批', status: 'warn', time: data.risk_level || 'ADMIN' });
    }

    let html = `<div class="trace-timeline">`;
    for (const s of steps) {
      const icon = s.status === 'success' ? '✓' : (s.status === 'failed' ? '❌' : '⚠️');
      html += `
        <div class="trace-step ${s.status}">
          <span class="step-icon">${icon}</span>
          <span class="step-name">${s.name}</span>
          <span class="step-time">${s.time}</span>
        </div>
      `;
    }
    html += `</div>`;
    return html;
  }

  function appendAgentResponse(data) {
    const msg = document.createElement('div');
    msg.className = 'chat-msg agent';

    let contentHtml = '';
    contentHtml += renderAgentTraceTimeline(data);

    if (data.generated_sql) {
      const escapedSql = escapeHtml(data.generated_sql);
      const safeEncodedSql = encodeURIComponent(data.generated_sql).replace(/'/g, '%27');
      contentHtml += `
        <div class="copilot-sql-card">
          <div class="sql-card-header">
            <span>生成 SQL 语句</span>
            <span>DataSphere Dialect</span>
          </div>
          <div class="sql-card-code">${escapedSql}</div>
          <div class="sql-card-actions">
            <button class="btn-sql-action btn-insert-sql" data-sql="${escapedSql}" onclick="window.Studio.insertSql(decodeURIComponent('${safeEncodedSql}'))">
              <span>📝 填入查询</span>
            </button>
            <button class="btn-sql-action btn-exec-sql" data-sql="${escapedSql}" onclick="window.Studio.runSqlDirect(decodeURIComponent('${safeEncodedSql}'))">
              <span>▶ 直接运行</span>
            </button>
          </div>
        </div>
      `;
    }

    if (data.answer) {
      contentHtml += `<div style="white-space:pre-wrap; margin-top:6px;">${escapeHtml(data.answer)}</div>`;
    }

    msg.innerHTML = `<div class="chat-bubble-agent">${contentHtml}</div>`;
    copilotEl.chatContainer.appendChild(msg);
    copilotEl.chatContainer.scrollTop = copilotEl.chatContainer.scrollHeight;

    // 处理审批
    if (data.approval_required && data.approval_request_id) {
      currentPendingApprovalId = data.approval_request_id;
      copilotEl.approvalDesc.textContent = `${data.generated_sql} [单号: ${currentPendingApprovalId}]`;
      copilotEl.approvalBanner.classList.remove('hidden');
    }
  }

  function renderMarkdownMini(md) {
    if (!md) return '';
    let text = md.trim();
    // 移除生硬死板的模板大标题与重复的 SQL 代码块
    text = text.replace(/^#+\s*(?:CortexDB|查询分析报告|核心结论|执行详情|数据分析报告|业务结论|查询结果)[^\n]*\n+/gim, '');
    text = text.replace(/```sql[\s\S]*?```/gi, ''); // 移除重复的 SQL 代码块
    text = text.replace(/^#+\s+/gm, ''); // 移除多余的 # 标题记号

    // 彻底剥离任何 Markdown 表格结构 (如 | col1 | col2 |)
    text = text.replace(/\|[^\n]+\|\n\|[-:\s|]+\|\n(?:\|[^\n]+\|\n*)+/g, '');
    text = text.replace(/\|[^\n]+\|/g, '');

    // 移除冗余废话提示
    text = text.replace(/📋\s*查询结果[^\n]*/gi, '');
    text = text.replace(/查询共返回\s*\d+\s*行记录[^\n]*/gi, '');
    text = text.replace(/数据如下[：:]*/gi, '');
    text = text.replace(/最终执行\s*SQL[：:]*[^\n]*/gi, '');

    text = text.trim();

    // 转义 HTML
    let html = escapeHtml(text);

    // 加粗 **text** -> <strong class="hl-bold">text</strong>
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong class="hl-bold">$1</strong>');

    // 行内代码 `code` -> <code class="inline-code">code</code>
    html = html.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');

    // 换行与段落
    const paragraphs = html.split(/\n{2,}/).filter(Boolean);
    return paragraphs.map(p => `<p style="margin:4px 0 8px 0; line-height:1.6;">${p.replace(/\n/g, '<br>')}</p>`).join('');
  }

  function formatStepDescription(evt) {
    const type = evt.event;
    const data = evt.data || {};
    switch (type) {
      case 'agent.started':
        return { text: '🚀 启动智能会话，正在构建内核执行图谱...', status: 'success' };
      case 'intent.detected':
        const intentNames = { query: '数据查询', diagnose: '慢查询诊断', optimize: '索引性能调优', explain: '执行计划分析', ddl: '表结构运维' };
        return { text: `🎯 意图推断完成：${intentNames[data.intent] || data.intent} (置信度 ${(data.confidence * 100).toFixed(0)}%)`, status: 'success' };
      case 'schema.retrieved':
        return { text: '📚 召回当前数据库 Catalog 表结构与字段元数据', status: 'success' };
      case 'sql.generated':
        return { text: '⚙️ 初步生成数据操作 SQL 逻辑', status: 'success' };
      case 'sql.validated':
        if (data.valid) {
          return { text: '✓ 数据库内核编译器前置质检 (Compiler Pre-check: PASS)', status: 'success' };
        } else {
          return { text: '⚠️ 编译器发现语法或字段偏差，触发自愈引擎...', status: 'warn' };
        }
      case 'sql.corrected':
        return { text: `🔧 语法自愈修复成功 (重试 #${data.retry_count})：${data.root_cause || '消除字段或语法歧义'}`, status: 'warn' };
      case 'analysis.completed':
        return { text: '📊 收集 BufferPool 缓存指标与物理存储分析报告', status: 'success' };
      case 'sql.executed':
        return { text: `⚡ 物理引擎执行完毕，共命中 ${data.rows_count || 0} 行数据 (耗时: ${data.latency_ms || 0}ms)`, status: 'success' };
      case 'approval.required':
        return { text: `🛡️ 检测到数据删除/修改操作 (${data.statement_type || 'DML'})，已拦截物理执行并挂起等待用户确认`, status: 'warn' };
      case 'clarification.required':
        return { text: `❓ 目标表不明确或存在多表歧义，向用户发起追问澄清`, status: 'warn' };
      default:
        return { text: `• ${type}`, status: 'success' };
    }
  }

  async function handleSendCopilot(customQuery = null) {
    const query = (customQuery || copilotEl.input.value).trim();
    if (!query) return;

    if (!customQuery) {
      copilotEl.input.value = '';
    }

    toggleCopilot(true);
    appendUserMessage(query);

    const msgId = 'msg-' + Date.now();
    const msgEl = document.createElement('div');
    msgEl.className = 'chat-msg agent';
    msgEl.id = msgId;

    msgEl.innerHTML = `
      <div class="chat-bubble-agent">
        <!-- 深度思考折叠容器 (DeepSeek 风格) -->
        <div class="copilot-thinking-box thinking-active" id="thinking-${msgId}">
          <div class="thinking-header" id="thinking-header-${msgId}">
            <div class="thinking-status-left">
              <span class="thinking-pulse-dot" id="thinking-dot-${msgId}"></span>
              <span id="thinking-title-${msgId}">⚡ 深度思考中...</span>
            </div>
            <div class="thinking-meta-right">
              <span class="thinking-time-badge" id="thinking-time-${msgId}">0.0s</span>
              <svg class="thinking-arrow-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="6 9 12 15 18 9"></polyline>
              </svg>
            </div>
          </div>
          <div class="thinking-body" id="thinking-body-${msgId}">
            <div class="thinking-steps-list" id="thinking-steps-${msgId}"></div>
            <div class="thinking-model-text" id="thinking-model-text-${msgId}" style="display:none;"></div>
          </div>
        </div>

        <!-- 逐字打字机正文容器 -->
        <div class="streaming-answer-text" id="answer-text-${msgId}">
          <span class="typing-cursor" id="typing-cursor-${msgId}"></span>
        </div>

        <!-- 结构化 SQL 卡片占位 -->
        <div class="sql-card-container" id="sql-card-container-${msgId}"></div>
      </div>
    `;

    copilotEl.chatContainer.appendChild(msgEl);
    copilotEl.chatContainer.scrollTop = copilotEl.chatContainer.scrollHeight;

    // 思考卡片折叠/展开事件绑定
    const thinkingBox = document.getElementById(`thinking-${msgId}`);
    const thinkingHeader = document.getElementById(`thinking-header-${msgId}`);
    if (thinkingHeader && thinkingBox) {
      thinkingHeader.addEventListener('click', () => {
        thinkingBox.classList.toggle('collapsed');
      });
    }

    const tStart = performance.now();
    let isThinkingDone = false;
    const timerInterval = setInterval(() => {
      if (isThinkingDone) {
        clearInterval(timerInterval);
        return;
      }
      const sec = ((performance.now() - tStart) / 1000).toFixed(1);
      const timeBadge = document.getElementById(`thinking-time-${msgId}`);
      if (timeBadge) timeBadge.textContent = `${sec}s`;
    }, 100);

    function markThinkingCompleted() {
      if (isThinkingDone) return;
      isThinkingDone = true;
      clearInterval(timerInterval);
      const totalSec = ((performance.now() - tStart) / 1000).toFixed(1);

      const titleEl = document.getElementById(`thinking-title-${msgId}`);
      const dotEl = document.getElementById(`thinking-dot-${msgId}`);
      const timeBadge = document.getElementById(`thinking-time-${msgId}`);

      if (titleEl) titleEl.textContent = '✓ 已深度思考';
      if (dotEl) {
        dotEl.classList.add('done');
      }
      if (timeBadge) timeBadge.textContent = `${totalSec}s`;
      if (thinkingBox) {
        thinkingBox.classList.remove('thinking-active');
        // 推理完毕后，默认半收起，保持界面整洁优雅
        thinkingBox.classList.add('collapsed');
      }
    }

    const answerTextEl = document.getElementById(`answer-text-${msgId}`);
    const cursorEl = document.getElementById(`typing-cursor-${msgId}`);
    const stepsContainer = document.getElementById(`thinking-steps-${msgId}`);
    const modelThoughtEl = document.getElementById(`thinking-model-text-${msgId}`);
    const sqlCardContainer = document.getElementById(`sql-card-container-${msgId}`);

    let fullAnswerText = '';
    let hasAutoExecutedQuery = false;

    try {
      const response = await fetch('/api/agent/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: query,
          session_id: 'navicat_web_copilot'
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // 保留未完整的最后一行

        let currentEvent = 'message';
        for (let line of lines) {
          line = line.trim();
          if (!line) continue;

          if (line.startsWith('event:')) {
            currentEvent = line.substring(6).trim();
            continue;
          }

          if (line.startsWith('data:')) {
            const jsonStr = line.substring(5).trim();
            let parsedData = {};
            try {
              parsedData = JSON.parse(jsonStr);
            } catch (e) {
              continue;
            }

            if (currentEvent === 'step') {
              const stepInfo = formatStepDescription(parsedData);
              const stepRow = document.createElement('div');
              stepRow.className = `trace-step ${stepInfo.status}`;
              stepRow.style.padding = '2px 0';
              stepRow.innerHTML = `
                <span class="step-icon">${stepInfo.status === 'warn' ? '⚠️' : '✓'}</span>
                <span class="step-name">${escapeHtml(stepInfo.text)}</span>
              `;
              if (stepsContainer) {
                stepsContainer.appendChild(stepRow);
                copilotEl.chatContainer.scrollTop = copilotEl.chatContainer.scrollHeight;
              }

              // 【核心响应前移】：当物理引擎执行完毕 (sql.executed) 时，立刻将 SQL 填入查询栏并刷新数据网格！
              const stepEvt = parsedData.event;
              const stepData = parsedData.data || {};
              if (stepEvt === 'sql.executed' && stepData.sql && !hasAutoExecutedQuery) {
                const sText = stepData.sql.trim();
                if (/^SELECT\b/i.test(sText)) {
                  hasAutoExecutedQuery = true;
                  // 立即自动填入当前活跃或新建的查询窗口
                  window.Studio.insertSql(sText);
                  // 立即执行并在左侧网格呈现真实数据
                  setTimeout(() => {
                    executeCurrentQuery();
                  }, 20);
                }
              }
            } else if (currentEvent === 'model_thought') {
              if (modelThoughtEl && parsedData.thought) {
                modelThoughtEl.style.display = 'block';
                modelThoughtEl.textContent = parsedData.thought;
              }
            } else if (currentEvent === 'token') {
              markThinkingCompleted();
              const token = parsedData.token || '';
              fullAnswerText += token;
              // 在打字光标前插入文字
              if (cursorEl) {
                cursorEl.insertAdjacentText('beforebegin', token);
              } else if (answerTextEl) {
                answerTextEl.textContent = fullAnswerText;
              }
              copilotEl.chatContainer.scrollTop = copilotEl.chatContainer.scrollHeight;
            } else if (currentEvent === 'done') {
              markThinkingCompleted();
              if (cursorEl) cursorEl.remove();

              // 精简并美化核心结论自然语言（移除生硬死板的 MD 大标题与重复 SQL）
              if (answerTextEl && fullAnswerText) {
                answerTextEl.innerHTML = renderMarkdownMini(fullAnswerText);
              }

              // 处理生成的 SQL
              if (parsedData.generated_sql && sqlCardContainer) {
                const sqlText = parsedData.generated_sql.trim();
                const sqlUpper = sqlText.toUpperCase();
                const isDangerous = /^(DELETE|DROP|TRUNCATE|UPDATE|ALTER)\b/.test(sqlUpper);

                if (isDangerous || parsedData.approval_required) {
                  // 1) 危险/删除/变更操作：严禁自动运行！必须在面板上展示高危警示，需要用户确认
                  const escapedSql = escapeHtml(sqlText);
                  const safeEncodedSql = encodeURIComponent(sqlText).replace(/'/g, '%27');
                  sqlCardContainer.innerHTML = `
                    <div class="copilot-sql-card dangerous-card">
                      <div class="sql-card-header dangerous-header">
                        <span style="color:#fb7185; font-weight:600;">⚠️ 包含数据删除或结构修改操作</span>
                        <span style="color:#fda4af; font-size:10.5px;">需人工确认</span>
                      </div>
                      <div class="sql-card-code" style="color:#fca5a5; background:#1c1015;">${escapedSql}</div>
                      <div class="sql-card-actions">
                        <button class="btn-sql-action btn-insert-sql" data-sql="${escapedSql}" onclick="window.Studio.insertSql(decodeURIComponent('${safeEncodedSql}'))">
                          <span>📝 仅填入编辑器</span>
                        </button>
                        <button class="btn-sql-action btn-danger-confirm" data-sql="${escapedSql}" onclick="if(confirm('⚠️ 警告：该操作将物理删除/修改数据，操作不可撤销！确定要继续执行吗？')){ window.Studio.runSqlDirect(decodeURIComponent('${safeEncodedSql}')); }">
                          <span>⚡ 确认并执行变更</span>
                        </button>
                      </div>
                    </div>
                  `;
                } else if (/^SELECT\b/.test(sqlUpper)) {
                  // 2) 能够查询的 SQL 语句：若此前在 thinking 阶段未触发，则在此兜底执行
                  if (!hasAutoExecutedQuery) {
                    hasAutoExecutedQuery = true;
                    insertSqlToEditor(sqlText);
                    setTimeout(() => {
                      executeCurrentQuery();
                    }, 50);
                  }

                  sqlCardContainer.innerHTML = `
                    <div class="auto-executed-pill">
                      <span class="pill-check">✓</span>
                      <span>已实时填入查询窗口并为您运行查询，真实数据已在左侧网格呈现</span>
                    </div>
                  `;
                } else {
                  // 其他非查询语句 (如 CREATE INDEX, SHOW 等)
                  const escapedSql = escapeHtml(sqlText);
                  const safeEncodedSql = encodeURIComponent(sqlText).replace(/'/g, '%27');
                  sqlCardContainer.innerHTML = `
                    <div class="copilot-sql-card">
                      <div class="sql-card-header">
                        <span>生成 SQL 语句</span>
                        <span>DataSphere Dialect</span>
                      </div>
                      <div class="sql-card-code">${escapedSql}</div>
                      <div class="sql-card-actions">
                        <button class="btn-sql-action btn-insert-sql" data-sql="${escapedSql}" onclick="window.Studio.insertSql(decodeURIComponent('${safeEncodedSql}'))">
                          <span>📝 填入查询</span>
                        </button>
                        <button class="btn-sql-action btn-exec-sql" data-sql="${escapedSql}" onclick="window.Studio.runSqlDirect(decodeURIComponent('${safeEncodedSql}'))">
                          <span>▶ 直接运行</span>
                        </button>
                      </div>
                    </div>
                  `;
                }
              }

              // 处理管理员审批流
              if (parsedData.approval_required && parsedData.approval_request_id) {
                currentPendingApprovalId = parsedData.approval_request_id;
                copilotEl.approvalDesc.textContent = `${parsedData.generated_sql} [单号: ${currentPendingApprovalId}]`;
                copilotEl.approvalBanner.classList.remove('hidden');
              }

              copilotEl.chatContainer.scrollTop = copilotEl.chatContainer.scrollHeight;
            } else if (currentEvent === 'error') {
              markThinkingCompleted();
              if (cursorEl) cursorEl.remove();
              if (answerTextEl) {
                answerTextEl.innerHTML += `<div style="color:#fb7185; margin-top:6px;">⚠️ 处理错误: ${escapeHtml(parsedData.error || '未知错误')}</div>`;
              }
            }
          }
        }
      }

      markThinkingCompleted();
      if (cursorEl) cursorEl.remove();

    } catch (err) {
      markThinkingCompleted();
      if (cursorEl) cursorEl.remove();
      if (answerTextEl) {
        answerTextEl.innerHTML = `<div style="color:#fb7185;">请求 Copilot 流式服务失败: ${escapeHtml(err.message)}</div>`;
      }
    }
  }

  // ==========================================================================
  // 事件监听绑定与初始化
  // ==========================================================================

  el.btnRunSql.addEventListener('click', executeCurrentQuery);
  el.btnNewQuery.addEventListener('click', () => createNewQueryTab());
  el.btnTabPlus.addEventListener('click', () => createNewQueryTab());

  el.btnRefreshAll.addEventListener('click', async () => {
    el.btnRefreshAll.classList.add('rotating');
    el.footerExecStats.textContent = '正在刷新数据库对象树与元数据...';
    try {
      await refreshDatabaseMeta();
      const curTab = state.tabs.find(t => t.id === state.activeTabId);
      if (curTab && curTab.type === 'table_data') {
        await loadTableData(curTab);
      } else if (curTab && curTab.type === 'table_schema') {
        await loadTableSchema(curTab);
      }
      el.footerExecStats.textContent = '数据库对象树与工作区数据已成功刷新';
    } catch (e) {
      console.error(e);
      el.footerExecStats.textContent = '刷新异常: ' + e.message;
    } finally {
      setTimeout(() => el.btnRefreshAll.classList.remove('rotating'), 600);
    }
  });

  if (el.headerDbSelect) {
    el.headerDbSelect.addEventListener('change', async (e) => {
      const targetDb = e.target.value;
      if (!targetDb || targetDb === state.currentDatabase) return;
      try {
        const res = await apiPost('/api/database/switch', { database: targetDb });
        if (res.success) {
          state.currentDatabase = res.current_database;
          await refreshDatabaseMeta();
          el.footerExecStats.textContent = `已切换至数据库: ${state.currentDatabase}`;
        }
      } catch (err) {
        alert("切换数据库失败: " + err.message);
        renderDatabaseSelect();
      }
    });
  }

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

  // Copilot 事件绑定
  if (copilotEl.btnToggle) {
    copilotEl.btnToggle.addEventListener('click', () => toggleCopilot());
  }
  if (copilotEl.btnClose) {
    copilotEl.btnClose.addEventListener('click', () => toggleCopilot(false));
  }
  if (copilotEl.btnSend) {
    copilotEl.btnSend.addEventListener('click', () => handleSendCopilot());
  }
  if (copilotEl.input) {
    copilotEl.input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSendCopilot();
      }
    });
  }

  // Copilot 对话框内按钮全局事件代理 (填入查询 / 直接运行 / 危险操作确认)
  if (copilotEl.chatContainer) {
    copilotEl.chatContainer.addEventListener('click', (e) => {
      const insertBtn = e.target.closest('.btn-insert-sql');
      if (insertBtn) {
        const sql = insertBtn.getAttribute('data-sql');
        if (sql) {
          insertSqlToEditor(sql);
        }
        return;
      }

      const execBtn = e.target.closest('.btn-exec-sql');
      if (execBtn) {
        const sql = execBtn.getAttribute('data-sql');
        if (sql) {
          runSqlDirectly(sql);
        }
        return;
      }

      const dangerConfirmBtn = e.target.closest('.btn-danger-confirm');
      if (dangerConfirmBtn) {
        const sql = dangerConfirmBtn.getAttribute('data-sql');
        if (sql && confirm('⚠️ 警告：该操作将物理删除/修改数据，操作不可撤销！确定要继续执行吗？')) {
          runSqlDirectly(sql);
        }
        return;
      }
    });
  }

  // 快速体验 prompt chip 点击
  document.querySelectorAll('.prompt-chip').forEach(btn => {
    btn.addEventListener('click', () => {
      const promptText = btn.getAttribute('data-prompt');
      if (promptText) {
        handleSendCopilot(promptText);
      }
    });
  });

  // 审批批准 / 拒绝
  if (copilotEl.btnConfirmApproval) {
    copilotEl.btnConfirmApproval.addEventListener('click', async () => {
      if (!currentPendingApprovalId) return;
      try {
        const res = await apiPost('/api/agent/approve', { request_id: currentPendingApprovalId });
        copilotEl.approvalBanner.classList.add('hidden');
        alert("✓ 审批通过并已成功执行物理变更！");
        await refreshDatabaseMeta();
        const activeTab = tabs.find(t => t.id === activeTabId);
        if (activeTab && activeTab.type === 'table_data') {
          await refreshTableData(activeTab.tableName);
        }
        appendAgentResponse({
          answer: "✓ 管理员人工审批已通过，已完成底层数据库变更物理执行。",
          execution_result: res.result
        });
      } catch (e) {
        alert("审批执行失败: " + e.message);
      }
    });
  }

  if (copilotEl.btnRejectApproval) {
    copilotEl.btnRejectApproval.addEventListener('click', async () => {
      if (!currentPendingApprovalId) return;
      try {
        await apiPost('/api/agent/reject', { request_id: currentPendingApprovalId });
        copilotEl.approvalBanner.classList.add('hidden');
        alert("已拒绝该操作。");
        appendAgentResponse({
          answer: "❌ 该操作已被管理员驳回，未对数据库结构做出修改。"
        });
      } catch (e) {
        alert("操作失败: " + e.message);
      }
    });
  }

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

