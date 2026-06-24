"""
上下文工程管理器：滑动窗口历史 + 摘要压缩 + 分层记忆

用于管理 Agent 对话和聊天的上下文窗口，避免超出 LLM token 限制。
"""
from typing import TypedDict


class Message(TypedDict, total=False):
    role: str       # "user" | "agent" | "system"
    text: str
    timestamp: str


class ContextManager:
    """上下文管理器：滑动窗口 + 自动摘要压缩"""

    def __init__(
        self,
        max_recent: int = 8,        # 最近保留的完整轮数
        max_anchor: int = 2,        # 最旧保留的完整轮数（锚定上下文）
        max_summary_chars: int = 500,  # 中间轮次摘要压缩后的最大字符数
        max_context_chars: int = 12000,  # 总上下文最大字符数
    ):
        self.max_recent = max_recent
        self.max_anchor = max_anchor
        self.max_summary_chars = max_summary_chars
        self.max_context_chars = max_context_chars
        self._compressed_summary = ""  # 中间轮次的摘要缓存

    def build_context(
        self,
        messages: list[Message],
        system_prompt: str = "",
        current_query: str = "",
    ) -> str:
        """构建最终发送给 LLM 的上下文文本

        Args:
            messages: 完整消息历史（role + text + timestamp）
            system_prompt: 系统提示词
            current_query: 当前用户查询（不计入截断）

        Returns:
            拼接好的上下文字符串
        """
        total = len(messages)

        # 消息不足时直接全部返回
        if total <= self.max_recent + self.max_anchor:
            parts = []
            if system_prompt:
                parts.append(system_prompt)
            for msg in messages:
                role_label = self._role_label(msg.get("role", ""))
                parts.append(f"{role_label}: {msg.get('text', '')}")
            if current_query:
                parts.append(f"用户: {current_query}")
            result = "\n\n".join(parts)
            if len(result) > self.max_context_chars:
                result = result[-self.max_context_chars:]
            return result

        # 需要压缩：保留首尾，中间用摘要替代
        anchor_msgs = messages[:self.max_anchor]
        recent_msgs = messages[-self.max_recent:]
        middle_msgs = messages[self.max_anchor:total - self.max_recent]

        # 更新摘要（累积式）
        if middle_msgs:
            self._compressed_summary = self._summarize_middle(middle_msgs)

        # 拼接上下文
        parts = []
        if system_prompt:
            parts.append(f"[系统]\n{system_prompt}")

        # 锚定上下文（最旧的几轮）
        for msg in anchor_msgs:
            role_label = self._role_label(msg.get("role", ""))
            parts.append(f"{role_label}: {msg.get('text', '')}")

        # 压缩摘要
        if self._compressed_summary:
            parts.append(f"[对话摘要]\n{self._compressed_summary}")

        # 最近的上下文
        for msg in recent_msgs:
            role_label = self._role_label(msg.get("role", ""))
            parts.append(f"{role_label}: {msg.get('text', '')}")

        if current_query:
            parts.append(f"用户: {current_query}")

        result = "\n\n".join(parts)

        # 最终长度保护
        if len(result) > self.max_context_chars:
            # 优先保留 system_prompt + recent + current_query
            head = parts[0] if system_prompt else ""
            tail = "\n\n".join(parts[-self.max_recent - 2:])
            result = head + "\n\n[中间对话已省略]\n\n" + tail
            if len(result) > self.max_context_chars:
                result = result[-self.max_context_chars:]

        return result

    def _role_label(self, role: str) -> str:
        mapping = {
            "user": "用户",
            "agent": "AI",
            "system": "系统",
            "assistant": "AI",
        }
        return mapping.get(role, role)

    def _summarize_middle(self, messages: list[Message]) -> str:
        """对中间轮次的消息做本地摘要（基于关键词提取 + 拼接）"""
        if not messages:
            return ""

        # 轻量级摘要：提取每轮的关键词和主题
        topics = []
        for msg in messages:
            text = msg.get("text", "")
            if not text:
                continue
            # 提取前 80 个字符作为主题提示
            snippet = text[:80].replace("\n", " ")
            if len(text) > 80:
                snippet += "..."
            topics.append(snippet)

        if not topics:
            return ""

        # 拼成连贯的摘要
        summary = "；".join(topics[:5])
        if len(summary) > self.max_summary_chars:
            summary = summary[:self.max_summary_chars] + "..."

        # 如果已有累积摘要，追加
        if self._compressed_summary:
            summary = self._compressed_summary + " | " + summary

        return summary

    def reset(self):
        """重置压缩摘要缓存"""
        self._compressed_summary = ""


def build_chat_context(
    messages: list[dict],
    system_prompt: str = "",
    current_query: str = "",
    max_chars: int = 12000,
) -> str:
    """便捷函数：为聊天场景构建上下文"""
    mgr = ContextManager(max_context_chars=max_chars)
    typed_msgs = []
    for m in messages:
        typed_msgs.append({
            "role": m.get("role", ""),
            "text": m.get("text", m.get("content", "")),
            "timestamp": m.get("timestamp", ""),
        })
    return mgr.build_context(typed_msgs, system_prompt, current_query)
