# 输出格式化：统一输出格式

class OutputFormatter:
    """输出格式化器"""

    @staticmethod
    def print_stage_header(stage_name):
        """打印阶段标题"""
        print(f"\n{'=' * 50}")
        print(f"阶段: {stage_name}")
        print(f"{'=' * 50}")

    @staticmethod
    def print_token_stream(tokens):
        """打印 Token 流"""
        for token in tokens:
            print(f"[{token.type_code}, \"{token.value}\", {token.line}, {token.column}]")

    @staticmethod
    def print_ast(ast):
        """打印 AST"""
        print(ast)

    @staticmethod
    def print_semantic_result(result):
        """打印语义分析结果"""
        print(result)

    @staticmethod
    def print_execution_plan(plan):
        """打印执行计划"""
        print(plan)