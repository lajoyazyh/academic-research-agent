import json
from typing import List, Dict, Any, Optional

class TraceStep:
    """内部状态追踪节点，记录 ReAct 循环中的单步结构化数据"""
    def __init__(self, thought: str, action: str, action_input: Dict[str, Any], observation: str = ""):
        self.thought = thought
        self.action = action
        self.action_input = action_input
        self.observation = observation
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "thought": self.thought,
            "action": self.action,
            "action_input": self.action_input,
            "observation": self.observation
        }

class Memory:
    """Agent 记忆与状态管理核心类"""
    def __init__(self):
        self.messages: List[Dict[str, str]] = []
        self.traces: List[TraceStep] = []
        
    def add_message(self, role: str, content: str) -> None:
        """追加对话节点"""
        self.messages.append({"role": role, "content": content})
        
    def add_trace(self, step: TraceStep) -> None:
        """追加推理执行轨迹"""
        self.traces.append(step)

    def update_last_trace_observation(self, observation: str) -> None:
        """更新最后一次 Trace 的环境观察结果"""
        if self.traces:
            self.traces[-1].observation = observation
            
    def export_traces_to_json(self) -> str:
        """导出所有执行步骤的内部状态，方便 Web 端图形化展示"""
        return json.dumps([trace.to_dict() for trace in self.traces], ensure_ascii=False, indent=2)

