# agent/runtime/adapter.py
import time
import re
from typing import Dict, Any, List, Optional
from engine.database import DataSphereDB, ExecutionResult


class CortexDBAdapter:
    """
    DataSphere 原生接口适配器 (CortexDB Native Adapter).
    彻底隔离 Agent 上层逻辑与 DataSphere 内部实现，
    提供纯净、标准化的异步安全接口。
    """

    def __init__(self, db: Optional[DataSphereDB] = None, data_dir: str = 'data'):
        self.data_dir = data_dir
        self._owns_db = (db is None)
        self.db = db or DataSphereDB(data_dir=self.data_dir)

    def execute(self, sql: str) -> Dict[str, Any]:
        """物理执行 SQL 语句并返回结构化数据"""
        t0 = time.perf_counter()
        stmt = sql.strip()
        res: ExecutionResult = self.db.execute(stmt, actually_execute=True)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)

        columns = []
        if res.data and len(res.data) > 0:
            columns = list(res.data[0].keys())

        return {
            "sql": stmt,
            "success": res.success,
            "data": res.data or [],
            "columns": columns,
            "row_count": len(res.data) if res.data is not None else 0,
            "message": res.message,
            "error": res.error,
            "error_type": res.error_type,
            "latency_ms": latency_ms,
            "compilation_log": res.compilation_log or []
        }

    def validate(self, sql: str) -> Dict[str, Any]:
        """
        核心功能：SQL 编译前置质检 (Compiler Pre-check)
        调用词法、语法、语义检查与优化器计划生成，但不触碰底层磁盘数据。
        """
        t0 = time.perf_counter()
        stmt = sql.strip()
        res: ExecutionResult = self.db.execute(stmt, actually_execute=False)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)

        # 智能诊断分类
        stage = "unknown"
        error_code = "NONE"
        if not res.success:
            err_str = res.error or ""
            if "词法" in err_str or "Lex" in err_str:
                stage = "lexical"
                error_code = "LEXICAL_ERROR"
            elif "语法" in err_str or "Syntax" in err_str or "期望" in err_str:
                stage = "syntax"
                error_code = "SYNTAX_ERROR"
            elif "语义" in err_str or "不存在" in err_str or "类型不匹配" in err_str:
                stage = "semantic"
                if "表" in err_str and "不存在" in err_str:
                    error_code = "UNKNOWN_TABLE"
                elif "列" in err_str and "不存在" in err_str:
                    error_code = "UNKNOWN_COLUMN"
                elif "类型" in err_str:
                    error_code = "TYPE_ERROR"
                elif "约束" in err_str or "外键" in err_str:
                    error_code = "CONSTRAINT_ERROR"
                else:
                    error_code = "SEMANTIC_ERROR"
            else:
                stage = "planning"
                error_code = "PLANNING_ERROR"

        return {
            "sql": stmt,
            "valid": res.success,
            "stage": stage,
            "error_code": error_code,
            "error_message": res.error,
            "error_type": res.error_type,
            "smart_hints": res.smart_hints or [],
            "latency_ms": latency_ms,
            "compilation_log": res.compilation_log or []
        }

    def explain(self, sql: str) -> Dict[str, Any]:
        """获取并分析查询优化器的逻辑与物理执行计划"""
        stmt = sql.strip()
        res: ExecutionResult = self.db.execute(stmt, actually_execute=False)
        plan_str = ""
        for line in (res.compilation_log or []):
            if "执行计划" in line or "TableScan" in line or "HashJoin" in line or "IndexScan" in line or "Select" in line:
                plan_str += line + "\n"

        has_full_scan = "TableScan" in plan_str and "IndexScan" not in plan_str
        has_index_scan = "IndexScan" in plan_str

        return {
            "sql": stmt,
            "success": res.success,
            "explain_plan": plan_str.strip() or (res.compilation_log[-1] if res.compilation_log else "No plan"),
            "has_full_table_scan": has_full_scan,
            "has_index_scan": has_index_scan,
            "error": res.error if not res.success else None
        }

    def get_catalog_dict(self) -> Dict[str, Any]:
        """获取完整的 Schema 元数据字典"""
        catalog = self.db.catalog
        tables_meta = {}
        for tbl_name in catalog.list_tables():
            info = catalog.get_table_info(tbl_name)
            if info:
                indexes = catalog.list_indexes(tbl_name) if hasattr(catalog, "list_indexes") else []
                tables_meta[tbl_name] = {
                    "table_name": tbl_name,
                    "columns": info.get("columns", []),
                    "primary_key": info.get("primary_key"),
                    "row_count": info.get("row_count", 0),
                    "constraints": info.get("constraints", []),
                    "indexes": indexes
                }
        return tables_meta

    def get_schema_summary(self, target_tables: Optional[List[str]] = None) -> str:
        """
        生成紧凑的 Schema 提示摘要（用于 Prompt 实体注入，严格控制 Token）
        """
        cat = self.get_catalog_dict()
        lines = []
        for tbl_name, meta in cat.items():
            if target_tables and tbl_name not in target_tables:
                continue
            cols_desc = []
            for c in meta["columns"]:
                pk_mark = " [PK]" if c["name"] == meta.get("primary_key") else ""
                cols_desc.append(f"{c['name']} {c['type']}{pk_mark}")
            row_cnt = meta.get("row_count", 0)
            lines.append(f"Table `{tbl_name}` ({row_cnt} rows): ({', '.join(cols_desc)})")

            # 约束与外键
            for cons in meta.get("constraints", []):
                if cons[0] == "FOREIGN_KEY":
                    lines.append(f"  FK: {cons[1]} -> {cons[2]}({cons[3]})")
            # 索引
            if meta.get("indexes"):
                idx_names = [x.get("index_name", "") for x in meta["indexes"]]
                lines.append(f"  Indexes: {', '.join(idx_names)}")

        return "\n".join(lines)

    def get_buffer_metrics(self) -> Dict[str, Any]:
        """读取底层 BufferPool 运行指标与表空间状态"""
        bp = self.db.file_manager.buffer_pool
        hits = getattr(bp, "hit_count", 0)
        misses = getattr(bp, "miss_count", 0)
        total_access = hits + misses
        hit_rate = round((hits / total_access * 100), 2) if total_access > 0 else 100.0

        buf_dict = getattr(bp, "buffer", {})
        cached_pages = len(buf_dict)
        dirty_pages = len([p for p in buf_dict.values() if getattr(p, "is_dirty", False)])

        # 表空间文件大小
        db_file = getattr(self.db.file_manager.page_manager.tablespace, 'file_path', 'data/datasphere.db')
        import os
        file_size = os.path.getsize(db_file) if os.path.exists(db_file) else 0

        return {
            "cache_hits": hits,
            "cache_misses": misses,
            "cache_hit_rate_pct": hit_rate,
            "cached_pages": cached_pages,
            "dirty_pages": dirty_pages,
            "buffer_capacity": getattr(bp, "pool_size", 10),
            "tablespace_file_bytes": file_size,
            "tablespace_pages": file_size // 4096
        }

    def get_diagnostics(self) -> Dict[str, Any]:
        """生成数据库综合诊断报告"""
        cat = self.get_catalog_dict()
        metrics = self.get_buffer_metrics()

        tables_without_indexes = []
        for tbl, meta in cat.items():
            if not meta.get("indexes") and meta.get("row_count", 0) > 10:
                tables_without_indexes.append(tbl)

        health_status = "HEALTHY"
        issues = []
        if metrics["cache_hit_rate_pct"] < 50.0 and (metrics["cache_hits"] + metrics["cache_misses"]) > 20:
            health_status = "WARNING"
            issues.append(f"BufferPool 命中率过低 ({metrics['cache_hit_rate_pct']}%)，建议检查缓存容量或查询模式。")

        if tables_without_indexes:
            issues.append(f"表 {', '.join(tables_without_indexes)} 缺少索引，频繁查询可能引发全表扫描。")

        return {
            "health_status": health_status,
            "issues": issues,
            "tables_count": len(cat),
            "metrics": metrics,
            "catalog": cat
        }

    def close(self):
        if self._owns_db and hasattr(self.db, "close"):
            self.db.close()
