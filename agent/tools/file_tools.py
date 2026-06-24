import os
from typing import Any
from core.tools import BaseTool

class ClearNoteTool(BaseTool):
    name = "clear_notes"
    description = "清空临时研究笔记文件（research_notes.md）。用于清理本次运行的临时笔记缓存。"
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
    description = "用于记录单篇论文的深度阅读笔记（临时写入 research_notes.md）。请在笔记中明确标注论文 ID，系统会从执行轨迹中提取并将笔记与对应论文关联。"
    parameters = {
        "content": "严格结构化的Markdown格式笔记，必须包含 论文id、论文标题、作者、摘要、关键发现(列表)、方法、结论 几大部分，字数300-500左右。"
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


