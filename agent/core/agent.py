import json
import os
import time
from typing import List, Dict, Any
from core.tools import BaseTool
from utils.parser import extract_json
from llms.client import LLMClient

class BaseAgent:
    def __init__(self, tools: List[BaseTool], max_loops: int = 5):
        self.llm = LLMClient()
        self.tools: Dict[str, BaseTool] = {tool.name: tool for tool in tools}
        self.max_loops = max_loops
        self.traces = []
        self.error_history = []  # 记录连续同类错误，供给构化 Reflexion 使用
        self._critique_round = False  # Pre-FINISH 自主质检标记
        self._paper_filter_round = False  # Pre-FINISH 论文筛选标记

    def _generate_plan(self, user_query: str) -> str:
        """Plan-and-Execute 规划阶段：在 ReAct 循环前，让 LLM 自主产出一个显式的研究计划。"""
        planning_prompt = f"""你即将执行以下研究任务。请你先用一段简洁的文字制定你的研究计划：

{user_query}

请在你的计划中明确回答：
1. 你会把中文主题翻译成哪 2-3 组英文学术关键词进行尝试？
2. 你打算先用哪个学术数据库（arXiv / Semantic Scholar/ OpenAlex）？理由是什么？
3. 如果首轮搜索结果不理想，你的备选策略是什么？
4. 你预计需要搜集几篇论文、阅读到什么深度？

直接输出一个纯文本计划，不要用 JSON。控制在 300 字以内。"""

        try:
            plan_text = self.llm.chat(
                "你是一个擅长制定研究策略的 AI 学术助手。请直接输出研究计划，不要用 JSON 包裹。",
                planning_prompt,
                []
            )
            return plan_text.strip()
        except Exception as e:
            print(f"[Planning] 规划阶段调用失败（将跳过规划直接执行）: {e}")
            return ""
        
    def build_system_prompt(self) -> str:
        """构建系统级底层 Prompt，告知大模型工具可用性及 JSON 输出规约"""
        tool_descriptions = "\n".join(
            [f"- {name}: {t.description}\n  参数: {json.dumps(t.parameters, ensure_ascii=False)}" 
             for name, t in self.tools.items()]
        )
        
        return f"""你是一个具备自主思考和工具使用能力的顶级 AI 智能体。
你可以使用以下工具来解决用户的问题：
{tool_descriptions}

【你的输出格式强制限制】
每一次回复，包括你产生的所有思想，必须且只准输出合法的 JSON 格式。代码块不包含在任何解释内！
{{
    "thought": "你的思考逻辑，遇到错误请利用它进行反思并找出对策",
    "action": "当前一轮准备调用的工具的名称。如已经完成全部任务直接回答用户，填 'finish'",
    "action_input": {{"参数名称": "参数值"}},
    "final_answer": "如果你上方填入 action 的是 finish，则在此放置提供给用户的最终纯文本结果。否则留空字符串"
}}
"""

    def run(self, user_query: str) -> str:
        """Plan-and-Execute + ReAct + Reflexion：先规划，再执行，运行中自我修正"""
        system_prompt = self.build_system_prompt()
        history = []
        try:
            loop_delay_seconds = float(os.getenv("AGENT_LOOP_DELAY_SEC", "3"))
        except ValueError:
            loop_delay_seconds = 3.0

        # ━━━━━ 阶段 0：Plan（规划）━━━━━
        plan = self._generate_plan(user_query)
        if plan:
            self.traces.append({
                "thought": f"[规划阶段 Plan-and-Execute]\n{plan}",
                "action": "PLAN",
                "input": {},
                "observation": "研究计划已生成，下面进入执行阶段。",
                "error_type": "",
            })
            current_query = f"这是你之前制定的研究计划：\n\n{plan}\n\n---\n\n{user_query}\n\n现在请按照你的计划开始执行。"
        else:
            current_query = user_query

        for loop_count in range(self.max_loops):
            if loop_count > 0 and loop_delay_seconds > 0:
                print(f"\n⏳ [API 请求限流保护] 冷却 {loop_delay_seconds:g} 秒以防触发 429 Rate Limit...")
                time.sleep(loop_delay_seconds)
                
            # 1. 呼叫大模型，获得原始文本响应
            try:
                llm_response_str = self.llm.chat(system_prompt, current_query, history)
            except Exception as e:
                observation_error = f"LLM 请求失败：{str(e)}"
                self.traces.append({
                    "thought": "ERROR: LLM_REQUEST",
                    "action": "LLM_REQUEST_ERROR",
                    "input": current_query,
                    "observation": observation_error,
                    "error_type": "llm_request_error",
                })
                return observation_error
            
            # 将本次用户的请求/环境异常作为 prompt 写入历史
            if current_query:
                history.append({"role": "user", "content": current_query})
            history.append({"role": "assistant", "content": llm_response_str})
            # 重置环境观察提示词
            current_query = "" 
            
            # 2. 尝试提取意图 JSON 结构
            try:
                # 这一步尝试把文本洗成词典
                response_data = extract_json(llm_response_str)
            except ValueError as e:
                # 【核心：输出异常自我修正 Reflexion】
                # 没有中断主循环！将其塞成环境报错丢给大模型强迫其改正格式重做
                observation_error = f"JSON 提取或格式解析严重失败！报错日志：{str(e)}。强制要求：下一轮请端正格式严格重新输出合法的 JSON 结构。"
                self.traces.append({
                    "thought": "ERROR: FORMATTING",
                    "action": "JSON_PARSE_ERROR",
                    "input": llm_response_str,
                    "observation": observation_error,
                    "error_type": "json_parse_error",
                })
                current_query = observation_error
                continue
                
            thought = response_data.get("thought", "")
            action = response_data.get("action", "")
            action_input = response_data.get("action_input", {})
            final_answer = response_data.get("final_answer", "")
            
            # 3. 终局判断（带质量门禁 + Pre-FINISH 自主质检）
            if action.lower() == "finish":
                # ━━━ 质量门禁：检查是否满足硬性质量约束 ━━━
                note_count = sum(1 for t in self.traces if t.get("action") == "append_note")
                if note_count < 3:
                    gate_msg = (
                        f"⚠️ 质量门禁拦截：你目前只记录了 {note_count} 篇论文笔记，"
                        "但硬性要求是至少 3 篇独立笔记。你不能在此刻 FINISH。\n\n"
                        "【立即使用已获取的信息写笔记】\n"
                        "你已经搜索到了多篇论文并下载了 PDF。请立即用 append_note 工具"
                        "根据你已阅读的摘要或论文内容写笔记，每篇笔记包含：标题、作者、"
                        "核心方法、关键发现。不要再去搜索新的论文——先写好已找到的论文的笔记。"
                    )
                    self.traces.append({
                        "thought": thought,
                        "action": "FINISH_BLOCKED",
                        "input": action_input,
                        "observation": gate_msg,
                        "error_type": "quality_gate",
                    })
                    current_query = gate_msg
                    continue

                # ━━━ Pre-FINISH 自主质检（Self-Critique）━━━
                if not self._critique_round:
                    self._critique_round = True
                    critique_prompt = (
                        "🔍 自主质检回合：在你真正 FINISH 之前，请审查你已完成的所有研究笔记。\n\n"
                        "对每一篇你已记录笔记的论文，逐一检查是否包含以下要素：\n"
                        "1. ✅ 完整标题\n"
                        "2. ✅ 作者列表\n"
                        "3. ✅ DOI（或 arXiv ID）\n"
                        "4. ✅ 核心方法/技术路线描述\n"
                        "5. ✅ 关键实验发现或结论\n"
                        "6. ✅ 与你研究主题的关联分析\n\n"
                        "如果任何一篇笔记缺失了以上要素，请在下一轮用 append_note 补充，"
                        "或搜索更多信息来完善笔记。如果所有笔记都足够完整，请再次输出 FINISH。"
                    )
                    self.traces.append({
                        "thought": thought,
                        "action": "SELF_CRITIQUE",
                        "input": {},
                        "observation": "系统已触发 Pre-FINISH 自主质检，请审查笔记完整性。",
                        "error_type": "",
                    })
                    current_query = critique_prompt
                    continue

                # 质检已通过，允许 FINISH
                self._critique_round = False
                self.traces.append({
                    "thought": thought,
                    "action": "FINISH",
                    "input": action_input,
                    "observation": final_answer,
                    "error_type": "",
                })
                return final_answer
                
            # 4. 执行业务 Tool 与自我修正（Action/Observation Reflexion）
            observation = ""
            error_type = ""
            if action not in self.tools:
                # 工具调用名不存在 -> 交由反思池
                observation = f"你尝试调用的工具名称 '{action}' 并不存在。允许调用的工具有：{list(self.tools.keys())}。"
                error_type = "unknown_tool"
            else:
                tool = self.tools[action]
                try:
                    # ✅ 真正的外部业务执行，并包裹捕捉致命的报错
                    observation = str(tool.execute(**action_input))  # 【核心修复：防止 Token 爆炸导致 TPM 限流】
                    if len(observation) > 4500:
                        observation = observation[:4500] + "\n\n...[警告：为防止大模型上下文超限，PDF后续内容已被系统自动截断]..."
                        error_type = "tool_observation_truncated"
                except Exception as ex:
                    # 【核心：运行时自我修正 Reflexion】
                    observation = f"目标工具 '{action}' 在执行输入 \n{action_input}\n 时产生了一个异常报错: {str(ex)}。\n请使用 thought 字段反思参数为什么抛出该错误，调整你的算法和参数值并在下一次回答中重试。"
                    error_type = "tool_runtime_error"

                # 自动后处理：如果刚刚 append_note 成功，则尝试自动下载对应的 arXiv PDF
                try:
                    if action == "append_note" and "笔记已成功" in observation:
                        # 优先从 action_input.content 中提取 arXiv ID 或 PDF URL
                        import re
                        content_to_scan = thought + "\n" + str(action_input)
                        
                        # 扩大嗅探范围：若刚才没包含 URL，往前回溯最近 3 轮 Observation 寻找有没有遗留的 ID或PDF链接
                        for t in reversed(self.traces[-3:]):
                            content_to_scan += "\n" + str(t.get("observation", ""))
                        
                        paper_id_or_url = None
                        
                        # 首先提取显式的 JSON 字段 pdf_url 或 openAccessPdf，这最准确
                        m_json_url = re.search(r"['\"](?:pdf_url|openAccessPdf)['\"]\s*:\s*['\"](https?://[^\s\>\)\]\",]+)['\"]", content_to_scan, re.IGNORECASE)
                        if m_json_url:
                            paper_id_or_url = m_json_url.group(1)
                        else:
                            # 匹配常见 arXiv ID，例如 2308.11432 或 2308.11432v3 的特征
                            m_arxiv = re.search(r"\b(\d{4}\.\d{4,5})(v\d+)?\b", content_to_scan)
                            if m_arxiv:
                                paper_id_or_url = m_arxiv.group(1)
                            else:
                                # 最后匹配任意形如 http://xxx.pdf 的直链
                                m_url = re.search(r"(https?://[^\s\>\)\]\",]+\.pdf)", content_to_scan, re.IGNORECASE)
                                if m_url:
                                    paper_id_or_url = m_url.group(1)
                        
                        if paper_id_or_url:
                            download_tool = self.tools.get("arxiv_download_pdf")
                            if download_tool:
                                try:
                                    dl_res = download_tool.execute(paper_id=paper_id_or_url)
                                    observation = observation + f"\n\n[自动下载附加结果] {dl_res}"
                                except Exception as e:
                                    observation = observation + f"\n\n[自动下载附加结果] 触发下载时发生错误：{str(e)}"
                except Exception:
                    # 不让自动后处理影响主流程
                    pass
            
            # 记录本轮轨迹，给前台的可视化呈现使用
            self.traces.append({
                "thought": thought,
                "action": action,
                "input": action_input,
                "observation": observation,
                "error_type": error_type,
            })
            
            # ━━━ 结构化 Reflexion：连续同类错误触发深度反思 ━━━
            if error_type:
                self.error_history.append(error_type)
                # 只看最近 3 次
                recent = self.error_history[-3:]
                if len(recent) >= 3 and len(set(recent)) == 1:
                    # 连续 3 次同一类错误 → 注入深度反思提示
                    deep_reflection = (
                        f"🔴 深度反思警报：你已经连续 3 次遇到同一类错误（{error_type}）。"
                        "请暂时停下当前策略，在你的 thought 中深刻分析：\n"
                        "1. 这个错误的根本原因是什么？\n"
                        "2. 你之前的策略为什么反复失败？\n"
                        "3. 有哪些根本不同的替代方案可以尝试？\n"
                        "然后在下一次行动中采用全新的策略，不要再重复之前的做法。"
                    )
                    self.error_history.clear()
                    # 把反思提示追加到 current_query
                    if current_query:
                        current_query = deep_reflection + "\n\n" + current_query
                    else:
                        current_query = deep_reflection
            elif error_type == "":
                # 成功执行时清空错误历史（中断连续错误计数）
                self.error_history.clear()
            
            # 把当前回合的环境事实结果交由下一轮 user 对话的输入，驱动 ReAct 前进
            current_query = f"这是执行 '{action}' 的结果 / 环境报错观察 (Observation):\n{observation}\n现在请根据这个观察结果决定你的下一步 thought 和 action。"
            
        return "很遗憾，已达到系统的最大内部循环配置上限，未能得出最终结论。"
