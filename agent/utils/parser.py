import json
import re

def extract_json(text: str) -> dict:
    """
    从模型返回的非结构化文本中安全提取出 JSON 字典对象。
    自带鲁棒性校验，应对 Markdown 代码块包装。
    """
    text = text.strip()
    
    # 场景1：大模型很大概率会使用 ```json ... ``` 包装
    json_pattern = re.compile(r'```(?:json)?\s*(.*?)\s*```', re.DOTALL)
    match = json_pattern.search(text)
    
    try:
        if match:
            json_str = match.group(1).strip()
        else:
            # 场景2：大模型没有包裹 Markdown，但文本夹带解释。我们强行截取第一个 { 和最后一个 }
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                json_str = text[start:end+1]
            else:
                # 场景3：干干净净的 JSON
                json_str = text

        # 修复：LLM 输出的 JSON 可能包含 LaTeX 命令（如 \\uparrow、\\downarrow），
        # 其 \\u 前缀会被 json.loads 误解析为 Unicode 转义序列导致 ParseError。
        # 这里将不构成合法 Unicode 转义的 \\u 序列自动转义为字面量 \\\\u。
        json_str = re.sub(
            r'\\u(?![\da-fA-F]{4})',
            r'\\\\u',
            json_str
        )

        return json.loads(json_str)
    except json.JSONDecodeError as e:
        # 如果依然无法解析，主动抛出异常供外部 Reflexion 反思拦截
        raise ValueError(f"无法将文本解析为合法 JSON: {str(e)}。原文摘录: {text[:50]}...")

