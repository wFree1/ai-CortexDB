# 🧠 ai-CortexDB 2.0 (DataSphere)

> **Database-Native Agentic AI Database Studio & Autonomous Relational Engine**  
> 原生集成数据库内核与认知智能体的下一代关系型数据库与智能交互工作台。

---

## 🌟 核心特性与架构概览

`ai-CortexDB 2.0` 是一个自研的轻量级关系型数据库内核与全流程 AI Agent 深度结合的数据库系统。它不仅拥有自主实现的存储引擎、索引与编译器，还深度植入了基于 LangGraph 编排的智能体运行时，具备**自主语法纠错**、**主动需求澄清**、**确定性安全防火墙**与**沉浸式 Web Studio 工作台**。

```mermaid
graph TD
    User([用户 / 开发者]) <--> WebStudio[Navicat-Style Web Studio (8088)]
    WebStudio <--> AgentRuntime[Cortex Agent Runtime (LangGraph)]
    
    subgraph AgentRuntime [AI Agent 认知运行时]
        Supervisor[意图分流路由器 Supervisor]
        SQLAgent[SQL 生成与上下文继承 Agent]
        Firewall[SQL 确定性安全防火墙 / 人工审批流]
        Recovery[语法错误自愈纠错 Recovery Agent]
        Memory[六层持久化记忆系统 Memory Manager]
    end
    
    AgentRuntime <--> NativeAdapter[CortexDB Native Adapter]
    
    subgraph DatabaseEngine [DataSphere 原生关系型数据库内核]
        Compiler[词法 / 语法 / 语义编译器 (Compiler Pipeline)]
        Planner[执行计划与优化器 (Execution Planner)]
        BufferPool[4KB 页式管理与 BufferPool 缓冲池]
        BPlusTree[B+ 树物理索引引擎]
        DiskStorage[(静态数据文件 *.db / Catalog 持久化)]
    end
    
    NativeAdapter <--> Compiler
    Compiler --> Planner
    Planner --> BufferPool
    BufferPool <--> DiskStorage
    BufferPool <--> BPlusTree
```

---

## 🚀 核心子系统介绍

### 1. 引擎内核与存储持久化 (Storage & Execution Engine)
- **4KB 页式存储管理**：采用标准页管理结构，结合 LRU/Clock 算法的内存缓冲池（BufferPool）。
- **全脏页同步落盘保证 (Disk Persistence)**：任何 `INSERT`、`UPDATE`、`DELETE` 操作均在物理执行后自动将所有脏页刷入静态磁盘文件（`.db`），杜绝内存修改不落盘的问题。
- **B+ 树物理索引**：支持单列与主键的高效范围检索与等值命中。
- **多数据库原生空间隔离 (Multiple Databases Workspace)**：
  - 支持 `CREATE DATABASE <name>`、`USE <name>`、`SHOW DATABASES` 等标准命令；
  - 库间物理文件相互隔离，Web 界面支持一键平滑切换。

### 2. SQL 编译器前置质检 (SQL Compiler Pipeline)
- **词法与递归下降语法分析器**：原生支持 `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `JOIN` (INNER/LEFT), `GROUP BY`, `HAVING`, `ORDER BY`, `LIMIT`。
- **编译器前置质检 (Compiler Pre-check)**：在任何查询执行前，经由词法、语法、语义及计划生成四重门禁静态检验，零数据污染。

### 3. Agent 2.0 认知运行时 (Agentic Runtime)
- **需求歧义自适应感知与主动追问 (Clarification Mechanism)**：
  - 当检测到模糊指令（如“删除Bob”）且数据库存在多个重名实体表（如 `employees`、`student`）时，主动拦截盲目执行并向用户发起选择追问；
- **多轮会话意图继承 (Context & Intent Inheritance)**：
  - 在用户回复表名后，模型严格继承上一轮操作意图（`DELETE`）与筛选条件（`WHERE name = 'Bob'`），杜绝误判为全表 `SELECT` 查询；
- **确定性安全防火墙与审批流 (Deterministic Firewall & Approval Guard)**：
  - 自动将操作划分为 `READ`、`WRITE`、`DANGEROUS` 三大风险等级；
  - 高危破坏性操作（如 `DELETE`、`UPDATE`、`DROP`）强制挂起并生成审批单，待管理员批准后方可执行；
- **错误自愈重试循环 (Self-Healing Recovery)**：
  - 若编译器诊断出语法或方言不兼容，触发自愈 Agent 根据诊断提示自动重构 SQL（最多 3 次自愈）。

### 4. 沉浸式 Navicat 风格 Web Studio
- **极客暗黑质感 GUI**：多数据库对象资源管理器、可视化数据网格（Grid View）、表结构定义查看器；
- **联动式 Copilot 流式对话面板**：
  - 展开式思维链展示（意图推断、Schema 召回、编译器质检、物理引擎执行）；
  - SQL 建议卡片：支持一键「📝 填入查询编辑器」与「▶ 直接物理运行」；
  - 管理员人工审批横幅与拒绝/批准一键执行。

---

## 🛠️ 快速开始

### 1. 环境准备
确保您的机器已安装 **Python 3.10** 或更高版本。

```bash
# 克隆仓库
git clone <your-repo-url>
cd DataSphere-master

# 安装所需依赖
pip install -r requirements.txt
```

### 2. 配置环境变量
项目使用 `.env` 管理敏感配置。从模板创建 `.env` 文件：

```bash
# 复制模板文件
cp .env.example .env
```

打开 `.env` 文件并填入您的大模型 API 密钥（如阿里云 DashScope 或 OpenAI）：

```ini
# 填入您的大模型 API Key (切勿直接提交此文件到 Git 仓库)
OPENAI_API_KEY=sk-your-valid-api-key-here

# API 请求的基础地址 (兼容 OpenAI 协议)
OPENAI_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1

# 主模型名称 (推荐 qwen3.7-plus / gpt-4o 等)
MODEL_NAME=qwen3.7-plus
```

> 🔒 **安全提醒**：`.env` 已在 [`.gitignore`](.gitignore) 中被完全忽略，包含真实 Key 的配置绝不会上传至代码仓库。

### 3. 一键启动 Studio

```bash
python run_studio.py
```

终端将输出服务地址，在浏览器中打开：
👉 **http://127.0.0.1:8088**

---

## 📁 目录结构

```text
ai-CortexDB/
├── agent/                    # CortexDB Agent 2.0 运行时核心
│   ├── agents/               # 专职 Agent (SQL, DBA, Supervisor, Recovery, Analyst)
│   ├── graph/                # LangGraph 状态图与状态路由编排
│   ├── memory/               # 六层分级记忆系统 (Working, Session, Semantic...)
│   ├── prompts/              # 严格约束的系统提示词工程
│   ├── runtime/              # 数据库内核原生适配器与事件总线
│   ├── security/             # SQL 安全防火墙、风险评估与审批管理器
│   └── services/             # 统一执行流水线服务
├── data/                     # 物理存储数据目录 (*.db, catalog.json)
├── engine/                   # 关系型数据库内核引擎
│   ├── database.py           # DataSphere 数据库主实例与多库管理
│   ├── executor.py           # 物理算子执行器
│   └── storage_engine.py     # 存储引擎中间接口
├── sql_compiler/             # SQL 编译器套件
│   ├── lexer.py              # 词法分词器
│   ├── parser.py             # 语法分析与 AST 构建
│   ├── planner.py            # 执行计划树生成与优化
│   └── semantic.py           # Catalog 语义绑定与校验
├── storage/                  # 底层分页存储层
│   ├── bplus_tree.py         # B+ 树索引实现
│   ├── buffer.py             # LRU 缓冲池与脏页管理
│   ├── file_manager.py       # 记录物理序列化与磁盘文件管理
│   └── page.py               # 4KB 物理页封装
├── web/                      # Navicat-Style Web Studio 前后端
│   ├── server.py             # 现代化 HTTP & SSE 流式服务端
│   └── static/               # 前端静态应用 (Vanilla JS + 极客暗黑 CSS)
├── .env.example              # 环境变量安全配置模板
├── requirements.txt          # Python 依赖清单
└── run_studio.py             # Studio 一键启动入口
```

---

## 📄 License
MIT License
