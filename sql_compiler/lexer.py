# 词法分析
import re

# === 种别码映射（与现有流水线保持一致） ===
TOKEN_TYPE_MAP = {
    'KEYWORD': 1,
    'IDENTIFIER': 2,
    'NUMBER': 3,
    'STRING': 3,   # 字符串与数字同用 3
    'OPERATOR': 4,
    'DELIMITER': 5,
    'END': 0
}


class Token:
    def __init__(self, type_, value, line, column):
        self.type = type_               # 词法类别字符串，如 'KEYWORD'
        self.value = value              # 词素内容
        self.line = line                # 行号（从1开始）
        self.column = column            # 列号（从1开始）
        self.type_code = TOKEN_TYPE_MAP.get(type_, 0)

    def __repr__(self):
        # 调试友好：与示例输出风格保持一致 [type_code, "value", line, column]
        v = self.value
        if isinstance(v, str):
            return f'[{self.type_code}, "{v}", {self.line}, {self.column}]'
        return f'[{self.type_code}, "{v}", {self.line}, {self.column}]'


class Lexer:
    """
    简单 SQL 词法分析器：
      - 关键字大小写不敏感，统一转为大写后输出为 KEYWORD
      - 标识符大小写保留原样
      - 字符串仅支持单引号包裹，内部不处理转义（可按需扩展）
      - 数字支持十进制整数与浮点数（有小数点解析为 float）
    """

    # 关键字集合（统一大写）
    KEYWORDS = {
        # DDL / DML / 查询
        'SELECT', 'FROM', 'WHERE', 'CREATE', 'TABLE', 'INSERT', 'INTO',
        'VALUES', 'DELETE', 'UPDATE', 'SET', 'JOIN', 'ON',
        'ORDER', 'BY', 'GROUP', 'HAVING', 'AS',
        'EXPLAIN',

        # 扩展 DDL / 管理命令
        'DROP', 'ALTER', 'ADD', 'COLUMN', 'TRUNCATE',
        'IF', 'EXISTS', 'INDEX', 'SHOW', 'TABLES', 'COLUMNS',
        'DESC', 'DESCRIBE',

        # 扩展 DQL / 连接与限制
        'LIMIT', 'OFFSET', 'DISTINCT',
        'LEFT', 'RIGHT', 'INNER', 'OUTER', 'CROSS',
        'LIKE', 'IN', 'BETWEEN', 'IS',

        # 逻辑 / 排序
        'AND', 'OR', 'NOT', 'ASC', 'DESC',

        # 约束（含主键/外键/唯一/默认/可空）
        'PRIMARY', 'KEY', 'FOREIGN', 'REFERENCES',
        'UNIQUE', 'NULL', 'DEFAULT', 'CONSTRAINT',

        # 聚合/函数名
        'COUNT', 'SUM', 'AVG', 'MAX', 'MIN',
        'UPPER', 'LOWER', 'LENGTH', 'SUBSTR', 'ABS', 'ROUND', 'NOW',

        # 常量字面量
        'TRUE', 'FALSE',

        # 商业级多数据类型
        'INT', 'INTEGER', 'BIGINT', 'SMALLINT', 'TINYINT',
        'FLOAT', 'REAL', 'DOUBLE', 'DECIMAL', 'NUMERIC',
        'VARCHAR', 'CHAR', 'TEXT',
        'DATE', 'DATETIME', 'TIMESTAMP', 'TIME',
        'BOOL', 'BOOLEAN',
        'BLOB', 'BYTES'
    }

    # 运算符集合（用于参考；真正匹配以正则为准，注意多字符优先）
    OPERATORS = {
        '=', '>', '<', '>=', '<=', '<>', '!='
    }

    # 分隔符集合（用于参考；真正匹配以正则为准）
    DELIMITERS = {
        '(', ')', ',', ';', '.', '*', '='  # '=' 会被 OPERATOR 正则先匹配
    }

    def __init__(self, text: str):
        self.text = text
        self.tokens = []
        self.errors = []
        self._tokenize()

    def _tokenize(self):
        """
        使用正则分组匹配整篇文本。为保证关键字优先于标识符，
        先匹配 IDENTIFIER，再在 Python 侧判断是否为关键字。
        """
        token_spec = [
            # 空白
            ('WHITESPACE', r'\s+'),

            # -- 单行注释 或 /* ... */ 多行注释
            ('COMMENT', r'--[^\n]*|/\*[\s\S]*?\*/'),

            # 反引号或双引号标识符（支持如 `姓名` 或 "姓名" 或 `order`）
            ('QUOTED_ID', r'`[^`]+`|"[^"]+"'),

            # 标识符（支持英文、下划线、Unicode/汉字，首字符非数字）
            ('IDENTIFIER', r'[^\W\d]\w*'),

            # 数字（可选符号，浮点在前，避免 123.45 被拆成 123 和 .45）
            ('NUMBER', r'[-+]?(?:\d+\.\d+|\d+)'),

            # 字符串（单引号，不处理转义）
            ('STRING', r"'[^']*'"),

            # 运算符（多字符优先，含加减）
            ('OPERATOR', r'<>|!=|>=|<=|=|>|<|\+|-'),

            # 分隔符：加入 '*' 以支持 SELECT * FROM ...
            ('DELIMITER', r'[(),;.*]'),
        ]

        tok_regex = '|'.join(
            f'(?P<{name}>{pattern})' for name, pattern in token_spec
        )

        # 用 finditer 逐个匹配，大小写不敏感
        for mo in re.finditer(tok_regex, self.text, flags=re.IGNORECASE | re.MULTILINE):
            kind = mo.lastgroup
            lexeme = mo.group()
            start = mo.start()

            # 计算行/列（1-based）
            before = self.text[:start]
            line = before.count('\n') + 1
            last_newline = before.rfind('\n')
            column = (start - (last_newline + 1)) + 1

            if kind in ('WHITESPACE', 'COMMENT'):
                continue

            if kind == 'QUOTED_ID':
                val = lexeme[1:-1]
                token = Token('IDENTIFIER', val, line, column)

            elif kind == 'IDENTIFIER':
                up = lexeme.upper()
                if up in self.KEYWORDS:
                    token = Token('KEYWORD', up, line, column)
                else:
                    token = Token('IDENTIFIER', lexeme, line, column)

            elif kind == 'NUMBER':
                # 有小数点解析为 float，否则 int
                if '.' in lexeme:
                    try:
                        num_val = float(lexeme)
                    except Exception:
                        num_val = lexeme  # 回退为原字符串
                else:
                    try:
                        num_val = int(lexeme)
                    except Exception:
                        num_val = lexeme
                token = Token('NUMBER', num_val, line, column)

            elif kind == 'STRING':
                token = Token('STRING', lexeme[1:-1], line, column)

            elif kind == 'OPERATOR':
                token = Token('OPERATOR', lexeme, line, column)

            elif kind == 'DELIMITER':
                token = Token('DELIMITER', lexeme, line, column)

            else:
                # 理论不会到这里
                self.errors.append((line, column, f"Unrecognized token: {lexeme}"))
                continue

            self.tokens.append(token)

    def get_tokens(self):
        """返回 Token 列表。"""
        return self.tokens

    def get_errors(self):
        return self.errors
