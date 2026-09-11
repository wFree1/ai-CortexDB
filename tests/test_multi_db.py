# tests/test_multi_db.py
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from engine.database import DataSphereDB

def test_multi_db():
    db = DataSphereDB(data_dir='data')
    print('Initial dbs:', db.list_databases())
    
    r = db.execute('SHOW DATABASES;')
    print('SHOW DATABASES result:', r.data)
    assert any(d.get('Database') == 'datasphere' for d in r.data)
    
    r2 = db.execute('CREATE DATABASE IF NOT EXISTS test_shop;')
    print('CREATE DATABASE result:', r2.message)
    assert r2.success
    
    r_show = db.execute('SHOW DATABASES;')
    print('SHOW DATABASES after create:', [d['Database'] for d in r_show.data])
    assert any(d.get('Database') == 'test_shop' for d in r_show.data)
    
    r3 = db.execute('USE test_shop;')
    print('USE test_shop result:', r3.message, 'Current:', db.current_database)
    assert db.current_database == 'test_shop'
    
    # 验证当前库内无表
    r_tables_empty = db.execute('SHOW TABLES;')
    print('Tables in test_shop (should be 0):', len(r_tables_empty.data or []))
    assert len(r_tables_empty.data or []) == 0
    
    # 建表与插入
    r4 = db.execute('CREATE TABLE goods (id INT PRIMARY KEY, name VARCHAR(50), price DOUBLE);')
    print('CREATE TABLE goods:', r4.message)
    assert r4.success
    
    r5 = db.execute("INSERT INTO goods VALUES (101, 'MacBook Pro', 19999.0);")
    print('INSERT INTO goods:', r5.message)
    assert r5.success
    
    r6 = db.execute('SELECT * FROM goods;')
    print('SELECT * FROM goods:', r6.data)
    assert len(r6.data) == 1
    assert r6.data[0]['name'] == 'MacBook Pro'
    
    # 切换回 datasphere 验证数据隔离：goods 不应该在 datasphere 中！
    r7 = db.execute('USE datasphere;')
    print('Switched back to datasphere:', r7.message, 'Current:', db.current_database)
    assert db.current_database == 'datasphere'
    r_ds_tables = db.execute('SHOW TABLES;')
    table_names = [t.get('table_name') or t.get('Tables_in_database') for t in r_ds_tables.data]
    print('Tables in datasphere:', table_names)
    assert 'goods' not in table_names, "Isolation failed: goods table should NOT exist in datasphere!"
    
    # 切回 test_shop 验证数据持久化
    r8 = db.execute('USE test_shop;')
    assert db.current_database == 'test_shop'
    r9 = db.execute('SELECT * FROM goods;')
    print('Re-query goods in test_shop:', r9.data)
    assert len(r9.data) == 1
    
    # 清理：切回 datasphere 并删除 test_shop
    r10 = db.execute('USE datasphere;')
    r11 = db.execute('DROP DATABASE test_shop;')
    print('DROP DATABASE test_shop:', r11.message)
    assert r11.success
    
    final_dbs = db.list_databases()
    print('Final databases:', final_dbs)
    assert 'test_shop' not in final_dbs
    # -------------------------------------------------------------
    # 语法与语义分析器单测
    # -------------------------------------------------------------
    from sql_compiler.lexer import Lexer
    from sql_compiler.parser import Parser
    from sql_compiler.semantic import SemanticAnalyzer
    from sql_compiler.planner import Planner

    sem = SemanticAnalyzer(db.catalog)
    planner = Planner()

    for sql, expected_node in [
        ('SHOW DATABASES;', 'ShowDatabasesNode'),
        ('CREATE DATABASE IF NOT EXISTS my_db;', 'CreateDatabaseNode'),
        ('USE my_db;', 'UseDatabaseNode'),
        ('DROP DATABASE IF EXISTS my_db;', 'DropDatabaseNode')
    ]:
        tokens = Lexer(sql).get_tokens()
        ast = Parser(tokens, source_text=sql).parse()
        assert type(ast).__name__ == expected_node, f"Expected {expected_node}, got {type(ast).__name__}"
        sem_res = sem.analyze(ast)
        assert "[语义正确]" in sem_res
        plan = planner.generate_plan(ast)
        assert plan is not None

    print('[PASS] ALL COMPILER & AST TESTS PASSED!')
    print('\n[PASS] ALL MULTI-DATABASE CORE TESTS PASSED SUCCESSFULLY!')

if __name__ == '__main__':
    test_multi_db()
