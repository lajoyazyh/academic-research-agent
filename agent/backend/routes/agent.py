"""Agent 执行端点：规划、搜索、笔记、综述、自动模式、分析"""
import json
import os
import datetime
import re
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .deps import (
    session_mgr, global_kb, skill_mgr, copilot_mgr, _tool_registry,
    RUNS, RUN_LOCK, SESSIONS_DIR, DOCS_DIR, FRONTEND_DIR,
    FAVORITES_FILE,
)

import threading
from main import run_agent_pipeline, run_agent_pipeline_session  # noqa
from .models import (
    RunPhaseRequest, RunNotesRequest, ReviseNotesRequest,
    AutoRunRequest, AnalysisRequest,
)

router = APIRouter(prefix="/api/sessions", tags=["agent"])

@router.post("/{session_id}/run/plan")
def run_plan_phase(session_id: str, payload: RunPhaseRequest) -> dict:
    """【阶段1】执行规划，生成关键词候选项"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")

    try:
        result = run_agent_pipeline_session(
            session_id=session_id,
            user_topic=payload.topic.strip(),
            start_phase="plan",
        )
        # 保存初始规划到 Session
        if result.get("initial_plan"):
            session_mgr.save_initial_plan(session_id, result["initial_plan"])
        # 保存关键词候选项
        if result.get("keywords"):
            session_mgr.save_keywords(session_id, result["keywords"])
        # 保存 Plan 阶段的 traces
        if result.get("traces"):
            session_mgr.save_traces(session_id, result["traces"])
        # 保持 planning 状态（Session 创建时已为此状态，无需再次转移）

        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"规划阶段执行失败: {str(e)}")

def _run_search_in_background(session_id: str, topic: str, keywords: list[dict], max_loops: int) -> None:
    """后台执行搜索阶段，周期性保存 traces 供前端实时轮询"""
    import time as _time
    _stop_flag = [False]  # 用列表做可变容器，线程间可共享修改
    
    def _periodic_trace_saver():
        """每 3 秒将运行中的 traces 同步到 RUNS 内存（不写磁盘，避免覆盖历史数据）"""
        while not _stop_flag[0]:
            _time.sleep(3)
            try:
                agent = _agent_holder.get("agent")
                traces = list(agent.traces) if agent else []
                if not traces:
                    with RUN_LOCK:
                        traces = list(RUNS.get(f"session_{session_id}", {}).get("traces", []))
                if traces:
                    # 只更新 RUNS 内存，供前端轮询 /api/sessions/{id}/run/status
                    with RUN_LOCK:
                        if f"session_{session_id}" in RUNS:
                            RUNS[f"session_{session_id}"]["traces"] = traces
            except Exception:
                pass
    
    _saver_thread = threading.Thread(target=_periodic_trace_saver, daemon=True)
    _agent_holder = {}  # 用于捕获运行中 Agent 的引用
    
    try:
        # 更新 Session 状态为 searching（端点可能已更新，忽略重复异常）
        try:
            session_mgr.update_session_state(session_id, "searching")
        except ValueError:
            pass
        
        with RUN_LOCK:
            RUNS[f"session_{session_id}"] = {
                "status": "running",
                "phase": "searching",
                "traces": [],
                "_stop_flag": _stop_flag,  # 暴露终止标志供 cancel API 使用
            }
        
        _saver_thread.start()

        result = run_agent_pipeline_session(
            session_id=session_id,
            user_topic=topic,
            start_phase="search",
            user_keywords=keywords,
            max_loops=max_loops,
            agent_callback=lambda agent, wd: _agent_holder.update({"agent": agent}),
        )
        
        _stop_flag[0] = True

        # 保存论文列表到 Session
        if result.get("papers"):
            session_mgr.save_papers_list(session_id, result["papers"])
        # 保存轨迹（追加模式：不覆盖之前的轨迹）
        if result.get("traces"):
            session_mgr.save_traces(session_id, result["traces"], append=True)
        # 如果没有被取消，更新状态
        try:
            session_mgr.update_session_state(session_id, "search_complete")
        except ValueError:
            pass  # 可能已被取消设置为其他状态

        with RUN_LOCK:
            RUNS[f"session_{session_id}"] = {
                "status": "done",
                "phase": "search_complete",
                "traces": result.get("traces", []),
                "result": result,
            }

    except Exception as exc:
        import traceback
        _stop_flag[0] = True
        with RUN_LOCK:
            RUNS[f"session_{session_id}"] = {
                "status": "error",
                "phase": "failed",
                "error": str(exc),
                "_traceback": traceback.format_exc(),
            }


@router.post("/{session_id}/run/search")
def run_search_phase(session_id: str, payload: RunPhaseRequest) -> dict:
    """【阶段2】执行搜索（后台运行，需轮询状态）"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")

    # 获取用户确认的关键词
    keywords = payload.keywords or session.get("keywords", [])
    if not keywords:
        raise HTTPException(status_code=400, detail="关键词不能为空，请先确认关键词")

    # 更新状态为 searching
    try:
        session_mgr.update_session_state(session_id, "searching")
    except ValueError:
        pass  # 状态可能已经是 searching

    # 设置最低论文数环境变量（供 Agent 质量门禁使用）
    if hasattr(payload, 'min_papers') and payload.min_papers:
        os.environ["AGENT_MIN_PAPERS"] = str(payload.min_papers)

    # 后台执行
    worker = threading.Thread(
        target=_run_search_in_background,
        args=(session_id, payload.topic.strip(), keywords, payload.max_loops),
        daemon=True,
    )
    worker.start()
    return {
        "session_id": session_id,
        "status": "searching",
        "message": "搜索已开始，请通过 GET /api/sessions/{session_id} 轮询状态",
    }


@router.get("/{session_id}/run/status")
def get_session_run_status(session_id: str) -> dict:
    run_key = f"session_{session_id}"
    with RUN_LOCK:
        run = RUNS.get(run_key)
    if not run:
        return {"status": "unknown", "message": "无正在运行的任务"}
    return run


@router.post("/{session_id}/run/cancel")
def cancel_session_run(session_id: str) -> dict:
    """打断正在运行的搜索/撰写任务"""
    run_key = f"session_{session_id}"
    with RUN_LOCK:
        run = RUNS.get(run_key)
    
    if not run:
        # RUNS 里没有（可能是服务器重启过），检查磁盘状态
        session = session_mgr.load_session(session_id)
        if session and session.get("state") in {"searching", "writing"}:
            # 卡住状态，直接回退
            fallback = {"searching": "search_complete", "writing": "reviewing_notes"}
            new_state = fallback.get(session["state"], "search_complete")
            try:
                session_mgr.update_session_state(session_id, new_state)
            except ValueError:
                session_dir = SESSIONS_DIR / session_id
                meta = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
                meta["state"] = new_state
                (session_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"status": "fixed", "message": f"卡住状态已修复：{session['state']} → {new_state}"}
        raise HTTPException(status_code=404, detail="没有正在运行的任务，且状态未卡住")

    # 设置停止标志
    stop_flag = run.get("_stop_flag")
    if stop_flag and isinstance(stop_flag, list):
        stop_flag[0] = True
    
    # 更新 RUNS 状态
    with RUN_LOCK:
        RUNS[run_key]["status"] = "cancelled"
        RUNS[run_key]["phase"] = "cancelled"

    # 回退 Session 状态
    try:
        session_mgr.update_session_state(session_id, "search_complete")
    except ValueError:
        try:
            session_mgr.update_session_state(session_id, "plan_confirmed")
        except ValueError:
            pass

    return {"status": "cancelled", "message": "任务已被用户终止"}


@router.post("/{session_id}/run/write")
def run_write_phase(session_id: str, payload: RunPhaseRequest) -> dict:
    """【阶段3】撰写综述（基于 Session 中的笔记）"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")

    notes = session.get("notes", "")
    # 如果 draft_notes.md 为空，尝试从 papers_list.json 中聚合各论文的笔记
    if not notes.strip():
        papers = session.get("papers", [])
        aggregated = []
        for p in papers:
            pn = (p.get("notes") or "").strip()
            if pn:
                aggregated.append(f"## {p.get('title', p.get('paper_id', ''))}\n\n{pn}")
        notes = "\n\n---\n\n".join(aggregated)
    
    if not notes.strip():
        raise HTTPException(status_code=400, detail="笔记为空，请先为选中论文生成笔记")

    previous_review = session.get("review", "")
    feedback = session_mgr.get_feedback(session_id)
    rewrite_count = session.get("rewrite_count", 0)

    try:
        from main import run_write_from_notes  # noqa
        result = run_write_from_notes(
            user_topic=payload.topic.strip(),
            notes_content=notes,
            previous_review=previous_review,
            user_feedback=feedback,
            rewrite_count=rewrite_count,
            session_id=session_id,
        )

        # 保存综述，并记录本次撰写引用了哪些论文
        if result.get("review"):
            from main import _merge_referenced_papers
            referenced_papers = _merge_referenced_papers(notes, papers)
            session_mgr.save_review(session_id, result["review"], referenced_papers=referenced_papers)

        # 更新状态
        new_state = "reviewing_draft" if result.get("can_rewrite", True) else "complete"
        try:
            session_mgr.update_session_state(session_id, new_state)
        except ValueError:
            pass

        result["session_id"] = session_id
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"撰写阶段执行失败: {str(e)}")


# ━━━ 迭代三新增：为选中论文生成独立笔记 ━━━


@router.post("/{session_id}/run/notes")
def run_notes_phase(session_id: str, payload: RunNotesRequest) -> dict:
    """【阶段2b】为选中的每篇论文生成独立笔记"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")

    papers = session.get("papers", [])
    paper_ids = [pid.strip() for pid in payload.paper_ids if pid.strip()]
    if not paper_ids:
        raise HTTPException(status_code=400, detail="paper_ids 不能为空")

    from llms.client import LLMClient
    from tools.rag_note_generator import RAGNoteGenerator
    llm = LLMClient()
    rag = RAGNoteGenerator()
    topic = payload.topic.strip()

    # ━━━ 双通道 Skill 注入：笔记阶段 ━━━
    notes_skill_content = ""
    skills_config = session.get("skills", {})
    notes_skill_id = skills_config.get("notes")
    if notes_skill_id:
        try:
            notes_skill = skill_mgr.get_skill(notes_skill_id)
            if notes_skill and not notes_skill.get("deleted"):
                notes_skill_content = str(notes_skill.get("content", ""))
                if notes_skill_content:
                    print(f"[NotesSkill] Loaded skill {notes_skill_id}: len={len(notes_skill_content)}, title={notes_skill.get('title','?')}")
                else:
                    print(f"[NotesSkill] Skill {notes_skill_id} has empty content, falling back to default")
            else:
                # Skill 已删除或无效 → 自动回退默认通道
                print(f"[NotesSkill] Skill {notes_skill_id} is deleted/invalid, using default")
        except Exception as e:
            # Skill 加载异常 → 静默回退默认通道
            print(f"[NotesSkill] Failed to load skill {notes_skill_id}: {e}")
    else:
        print(f"[NotesSkill] No notes skill configured for this session, using default")

    notes_map = {}

    for paper in papers:
        pid = paper.get("paper_id", "")
        if pid not in paper_ids:
            continue

        title = paper.get("title", pid)
        abstract = paper.get("abstract", "")
        source_info = paper.get("source", "")
        if source_info == "agent_search":
            paper_path = session_mgr.get_agent_search_paper_path(session_id, pid)
        elif source_info == "user_custom":
            paper_path = session_mgr.get_user_custom_paper_path(session_id, pid)
        elif source_info == "user_upload":
            paper_path = session_mgr.get_user_upload_paper_path(session_id, title)

        try:
            # 使用 RAG 生成深度笔记（Embedding 检索全文 + LLM 逐节生成）
            note_text = rag.generate(
                pdf_path=str(paper_path),
                paper_title=title,
                abstract=abstract,
                topic=topic,
                skill_content=notes_skill_content,
            )
            notes_map[pid] = note_text
        except Exception:
            notes_map[pid] = f"## 论文笔记：{title}\n\n生成笔记时出错"

    if notes_map:
        session_mgr.batch_update_paper_notes(session_id, notes_map)

    return {
        "phase": "notes",
        "notes_map": notes_map,
        "count": len(notes_map),
    }

@router.post("/{session_id}/run/notes/revise")
def revise_notes_phase(session_id: str, payload: ReviseNotesRequest) -> dict:
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session 不存在")
    
    # 优先获取论文独立笔记，否则获取整体笔记
    notes = ""
    is_paper_notes = False
    if payload.paper_id:
        papers = session.get("papers", [])
        for p in papers:
            if p.get("paper_id") == payload.paper_id:
                notes = p.get("notes", "")
                is_paper_notes = True
                break
    
    if not notes:
        notes = session.get("notes", "")
        is_paper_notes = False

    if not notes.strip():
        raise HTTPException(status_code=400, detail="笔记为空，无法修订")
    
    from llms.client import LLMClient
    llm = LLMClient()

    rag_context = ""
    try:
        from tools.retriever import HybridRetriever
        import os as _os
        papers_path = _os.path.join(SESSIONS_DIR, session_id, "papers")
        retriever = HybridRetriever(session_id, str(papers_path))
        passages = retriever.iterative_retrieve(payload.feedback, top_k=10)
        if passages:
            parts = []
            for p in passages:
                pid_p = p.get("paper_id", "")
                pg = p.get("page", "?")
                tit = ""
                for pp in session.get("papers", []):
                    if pp.get("paper_id") == pid_p:
                        tit = pp.get("title", "")[:60]
                        break
                parts.append(f"【{tit or pid_p} (第{pg}页)】\n{p['text']}")
            rag_context = "\n\n---\n\n".join(parts)
    except Exception:
        pass

    revise_prompt = f"""你是一名严谨的学术研究员。请根据用户的反馈意见，对现有的研究笔记进行修订。
    
研究主题：{payload.topic}

【用户反馈意见】：
{payload.feedback}

【现有研究笔记】：
{notes}

请按照用户的反馈意见修改现有研究笔记，输出修改后的完整笔记内容，不要保留未修改部分的省略号，不要输出额外的解释。
"""
    try:
        new_notes = llm.chat("你是学术笔记修改专家。", revise_prompt, []).strip()
        
        if is_paper_notes and payload.paper_id:
            session_mgr.batch_update_paper_notes(session_id, {payload.paper_id: new_notes})
        else:
            session_mgr.save_notes(session_id, new_notes)
            
        return {"notes": new_notes, "message": "笔记已根据反馈修订"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"笔记修订执行失败: {str(e)}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/{session_id}/run/analyze")
def run_analysis_phase(session_id: str, payload: AnalysisRequest) -> dict:
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")

    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic 不能为空")

    notes = session.get("notes", "")
    papers = session.get("papers", [])

    if not notes.strip() and papers:
        parts = []
        for paper in papers:
            paper_notes = (paper.get("notes") or "").strip()
            if paper_notes:
                title = paper.get("title") or paper.get("paper_id") or "Unknown"
                parts.append(f"## {title}\n\n{paper_notes}")
        notes = "\n\n---\n\n".join(parts)

    try:
        from tools.analysis_tools import compare_papers, trace_lineage, find_gaps

        analysis_type = payload.analysis_type
        if analysis_type not in {"compare", "lineage", "gaps", "all"}:
            raise HTTPException(status_code=400, detail="analysis_type 必须是 compare、lineage、gaps 或 all")

        result = {"phase": "analysis", "session_id": session_id}
        if analysis_type in ("compare", "all"):
            result["compare"] = compare_papers(topic, notes, papers)
        if analysis_type in ("lineage", "all"):
            result["lineage"] = trace_lineage(topic, notes, papers)
        if analysis_type in ("gaps", "all"):
            result["gaps"] = find_gaps(topic, notes, papers)

        analysis_dir = SESSIONS_DIR / session_id / "analysis"
        os.makedirs(analysis_dir, exist_ok=True)
        (analysis_dir / "analysis_results.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析阶段执行失败: {str(e)}")




def _run_auto_pipeline_in_background(session_id: str, topic: str, max_loops: int, min_papers: int) -> None:
    """后台自动执行完整流水线：规划 → 搜索 → 笔记 → 综述"""
    import time as _time

    run_key = f"session_{session_id}"
    _stop_flag = [False]

    def _update_run_status(phase: str, status: str, **kwargs):
        with RUN_LOCK:
            if run_key in RUNS:
                entry = RUNS[run_key]
                entry["phase"] = phase
                entry["status"] = status
                entry.update(kwargs)

    try:
        # ━━ 阶段 1：规划 ━━
        _update_run_status("planning", "running", message="正在生成关键词规划...")

        if _stop_flag[0]:
            return

        plan_result = run_agent_pipeline_session(
            session_id=session_id,
            user_topic=topic,
            start_phase="plan",
        )
        if plan_result.get("initial_plan"):
            session_mgr.save_initial_plan(session_id, plan_result["initial_plan"])
        if plan_result.get("keywords"):
            session_mgr.save_keywords(session_id, plan_result["keywords"])
        if plan_result.get("traces"):
            session_mgr.save_traces(session_id, plan_result["traces"])

        keywords = plan_result.get("keywords", [])
        _update_run_status("planning", "running",
                          message=f"关键词规划完成，共 {len(keywords)} 个候选项，即将开始搜索...",
                          keywords=keywords)

        if _stop_flag[0]:
            return

        # ━━ 阶段 2：搜索 ━━
        try:
            session_mgr.update_session_state(session_id, "searching")
        except ValueError:
            pass

        _update_run_status("searching", "running", message="正在检索论文并收集元数据...")

        # 设置最低论文数
        os.environ["AGENT_MIN_PAPERS"] = str(min_papers)

        _agent_holder = {}

        # 启动周期性 trace 同步线程，将 Agent 实时 traces 同步到 RUNS 供前端轮询
        def _auto_trace_saver():
            while not _stop_flag[0]:
                _time.sleep(3)
                try:
                    agent = _agent_holder.get("agent")
                    traces = list(agent.traces) if agent else []
                    if traces:
                        with RUN_LOCK:
                            if run_key in RUNS:
                                RUNS[run_key]["traces"] = traces
                except Exception:
                    pass

        _auto_saver_thread = threading.Thread(target=_auto_trace_saver, daemon=True)
        _auto_saver_thread.start()

        search_result = run_agent_pipeline_session(
            session_id=session_id,
            user_topic=topic,
            start_phase="search",
            user_keywords=keywords,
            max_loops=max_loops,
            agent_callback=lambda agent, wd: _agent_holder.update({"agent": agent}),
        )

        if _stop_flag[0]:
            return

        if search_result.get("papers"):
            session_mgr.save_papers_list(session_id, search_result["papers"])
        if search_result.get("traces"):
            session_mgr.save_traces(session_id, search_result["traces"], append=True)
        try:
            session_mgr.update_session_state(session_id, "search_complete")
        except ValueError:
            pass

        papers = search_result.get("papers", [])
        _update_run_status("search_complete", "running",
                          message=f"搜索完成，找到 {len(papers)} 篇论文，即将生成笔记...",
                          papers=papers)

        if _stop_flag[0]:
            return

        # ━━ 阶段 3：生成笔记 ━━
        try:
            session_mgr.update_session_state(session_id, "reviewing_notes")
        except ValueError:
            pass

        _update_run_status("reviewing_notes", "running",
                          message=f"正在为 {len(papers)} 篇论文生成深度笔记...")

        if papers:
            from llms.client import LLMClient
            from tools.rag_note_generator import RAGNoteGenerator
            llm = LLMClient()
            rag = RAGNoteGenerator()
            notes_map = {}

            # ━━━ Skill 注入：加载 notes 类型的自定义提示词 ━━━
            _auto_notes_skill = ""
            _auto_session = session_mgr.load_session(session_id)
            if _auto_session:
                _auto_skills = _auto_session.get("skills", {})
                _auto_notes_id = _auto_skills.get("notes")
                if _auto_notes_id:
                    try:
                        _auto_notes_data = skill_mgr.get_skill(_auto_notes_id)
                        if _auto_notes_data and not _auto_notes_data.get("deleted"):
                            _auto_notes_skill = str(_auto_notes_data.get("content", ""))
                            if _auto_notes_skill:
                                print(f"[NotesSkill] Auto-pipeline loaded skill {_auto_notes_id}: len={len(_auto_notes_skill)}")
                            else:
                                print(f"[NotesSkill] Auto-pipeline skill {_auto_notes_id} has empty content, using default")
                        else:
                            print(f"[NotesSkill] Auto-pipeline skill {_auto_notes_id} deleted/invalid, using default")
                    except Exception as e:
                        print(f"[NotesSkill] Auto-pipeline failed to load skill {_auto_notes_id}: {e}")
            else:
                print(f"[NotesSkill] Auto-pipeline: no notes skill configured, using default")

            for idx, paper in enumerate(papers):
                if _stop_flag[0]:
                    break
                pid = paper.get("paper_id", "")
                title = paper.get("title", pid)
                abstract = paper.get("abstract", "")
                source_info = paper.get("source", "")

                _update_run_status("reviewing_notes", "running",
                                  message=f"正在生成笔记 ({idx+1}/{len(papers)})：{title[:50]}...")

                try:
                    paper_path = None
                    if source_info == "agent_search":
                        paper_path = session_mgr.get_agent_search_paper_path(session_id, pid)
                    elif source_info == "user_custom":
                        paper_path = session_mgr.get_user_custom_paper_path(session_id, pid)
                    elif source_info == "user_upload":
                        paper_path = session_mgr.get_user_upload_paper_path(session_id, title)

                    note_text = rag.generate(
                        pdf_path=str(paper_path) if paper_path else "",
                        paper_title=title,
                        abstract=abstract,
                        topic=topic,
                        skill_content=_auto_notes_skill,
                    )
                    notes_map[pid] = note_text
                except Exception as exc:
                    notes_map[pid] = f"## 论文笔记：{title}\n\n生成笔记时出错：{str(exc)}"

            if notes_map:
                session_mgr.batch_update_paper_notes(session_id, notes_map)

        _update_run_status("reviewing_notes", "running",
                          message=f"笔记生成完成，共 {len(notes_map) if papers else 0} 篇，即将撰写综述...")

        if _stop_flag[0]:
            return

        # ━━ 阶段 4：撰写综述 ━━
        try:
            session_mgr.update_session_state(session_id, "writing")
        except ValueError:
            pass

        _update_run_status("writing", "running", message="正在撰写综述草稿...")

        # 重新加载 session 获取最新笔记
        session = session_mgr.load_session(session_id)
        notes = session.get("notes", "")
        if not notes.strip():
            papers_data = session.get("papers", [])
            aggregated = []
            for p in papers_data:
                pn = (p.get("notes") or "").strip()
                if pn:
                    aggregated.append(f"## {p.get('title', p.get('paper_id', ''))}\n\n{pn}")
            notes = "\n\n---\n\n".join(aggregated)

        if notes.strip():
            from main import run_write_from_notes  # noqa
            write_result = run_write_from_notes(
                user_topic=topic,
                notes_content=notes,
                session_id=session_id,
            )
            if write_result.get("review"):
                session_mgr.save_review(session_id, write_result["review"])
            # 状态机要求 writing → reviewing_draft → complete，不能直接跳
            try:
                session_mgr.update_session_state(session_id, "reviewing_draft")
            except ValueError:
                pass
            try:
                session_mgr.update_session_state(session_id, "complete")
            except ValueError:
                pass

        # ━━ 完成 ━━
        _update_run_status("complete", "done",
                          message="🎉 自动流程全部完成！综述已生成，可在右侧查看。",
                          result={"phase": "complete"})

    except Exception as exc:
        _update_run_status("failed", "error",
                          message=f"自动流程失败：{str(exc)}",
                          error=str(exc))
        try:
            session_mgr.update_session_state(session_id, "search_complete")
        except ValueError:
            pass


@router.post("/{session_id}/run/auto")
def run_auto_pipeline(session_id: str, payload: AutoRunRequest) -> dict:
    """【自动模式】一键触发 规划→搜索→笔记→综述 全流程自动执行"""
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")

    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="主题不能为空")

    run_key = f"session_{session_id}"

    # 检查是否已有任务在运行
    with RUN_LOCK:
        existing = RUNS.get(run_key)
        if existing and existing.get("status") == "running":
            raise HTTPException(status_code=409, detail="该 Session 已有正在运行的任务，请等待完成或取消后再试")

    # 初始化运行状态
    _stop_flag = [False]
    with RUN_LOCK:
        RUNS[run_key] = {
            "status": "running",
            "phase": "queued",
            "message": "自动流程已启动...",
            "_stop_flag": _stop_flag,
        }

    # 后台执行
    worker = threading.Thread(
        target=_run_auto_pipeline_in_background,
        args=(session_id, topic, payload.max_loops, payload.min_papers),
        daemon=True,
    )
    worker.start()

    return {
        "session_id": session_id,
        "status": "started",
        "message": "自动流程已启动，请通过 GET /api/sessions/{session_id}/run/status 轮询进度",
    }

