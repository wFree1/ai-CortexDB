#工具类和常量

# utils/constants.py
import enum

class TokenType(enum.Enum):
    KEYWORD = 1
    IDENTIFIER = 2
    CONSTANT = 3
    OPERATOR = 4
    DELIMITER = 5

class DataType(enum.Enum):
    INT = 1
    VARCHAR = 2
    FLOAT = 3
    BOOL = 4

# SQL 关键字
KEYWORDS = {
    'SELECT', 'FROM', 'WHERE', 'CREATE', 'TABLE', 'INSERT', 'INTO',
    'VALUES', 'DELETE', 'UPDATE', 'SET', 'DROP', 'AND', 'OR', 'NOT',
    'INT', 'VARCHAR', 'FLOAT', 'BOOL','KEY','FOREIGN','KEY','REFERENCES',
    'JOIN', 'INNER', 'LEFT', 'RIGHT', 'FULL', 'ON',
    'COUNT', 'SUM', 'AVG'
}

# 运算符
OPERATORS = {
    '=', '>', '<', '>=', '<=', '!=', '+', '-', '*', '/', '%'
}

# 分隔符
DELIMITERS = {
    ',', ';', '(', ')', '.', "'"
}

# 页面大小
PAGE_SIZE = 4096  # 4KB
BUFFER_POOL_SIZE = 100  # 缓存池大小