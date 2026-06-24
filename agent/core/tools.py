from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseTool(ABC):
    """
    所有的工具都必须继承该基类。
    约束了工具必须具备名称、描述、参数定义以及核心的 execute 方法。
    """
    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {}

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        pass

class CalculatorTool(BaseTool):
    name = "calculator"
    description = "一个用于执行基础数学运算的计算器引擎。当需要进行数字计算时调用此工具。"
    parameters = {
        "expression": "包含数学运算的字符串表达式，例如 '12 * (3 + 4)'"
    }

    def execute(self, **kwargs) -> str:
        expression = kwargs.get("expression")
        if not expression:
            raise ValueError("Missing required parameter: 'expression'")
        try:
            # 安全注意：生产环境应使用安全的 eval 或 AST 解析
            result = eval(expression, {"__builtins__": None}, {})
            return str(result)
        except Exception as e:
            raise RuntimeError(f"Invalid math expression '{expression}': {str(e)}")

class DummySearchTool(BaseTool):
    name = "search_engine"
    description = "一个用于查询外部事实和最新信息的搜索引擎。"
    parameters = {
        "query": "需要搜索的关键词字符串"
    }

    def execute(self, **kwargs) -> str:
        query = kwargs.get("query")
        if not query:
            raise ValueError("Missing required parameter: 'query'")
        return f"【搜索引擎返回结果】：检索词 '{query}' 的主要结果是：DeepSeek 是一家中国的人工智能初创公司。"

