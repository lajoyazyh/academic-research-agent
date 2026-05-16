import os
from typing import Any
from core.tools import BaseTool

class ClearNoteTool(BaseTool):
    name = "clear_notes"
    description = "清空草稿本。每次新任务开始时调用。"
    parameters = {}

    def __init__(self, work_dir: str):
        self.note_file = os.path.join(work_dir, "research_notes.md")

    def execute(self, **kwargs) -> Any:
        os.makedirs(os.path.dirname(self.note_file), exist_ok=True)
        if os.path.exists(self.note_file):
            os.remove(self.note_file)
        return "旧的草稿本已清空，你可以开始全新的调研和记笔记了。"

class AppendNoteTool(BaseTool):
    name = "append_note"
    description = "用于在调研过程中记录单篇论文的深度阅读笔记。"
    parameters = {
        "content": "你要记录的详细笔记内容。必须要详细。"
    }

    def __init__(self, work_dir: str):
        self.note_file = os.path.join(work_dir, "research_notes.md")

    def execute(self, **kwargs) -> Any:
        content = kwargs.get("content")
        if not content:
            return "写入失败，缺少 content 参数。"

        os.makedirs(os.path.dirname(self.note_file), exist_ok=True)
        with open(self.note_file, "a", encoding="utf-8") as f:
            f.write(content + "\n\n" + "="*40 + "\n\n")

        with open(self.note_file, 'r', encoding='utf-8') as f:
            current_size = len(f.read())
        return f"✅ 笔记已成功追加到草稿本！当前总字数：{current_size}。"

