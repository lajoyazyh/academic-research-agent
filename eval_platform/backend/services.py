from sqlalchemy.orm import Session
import crud, ModelS, schemas
from evaluation_methods import get_evaluator
import asyncio
import sys
import os
import json
from pathlib import Path
from database import SessionLocal

FIXED_GROUND_TRUTH = "成功检索相关文献、完成多源证据综合，并输出含引用的结构化综述结论。"


def _resolve_ground_truths(raw_ground_truths):
    """优先使用数据集中的 ground_truths；为空时回退默认 ground truth。"""
    if raw_ground_truths is None:
        return [FIXED_GROUND_TRUTH]

    if isinstance(raw_ground_truths, list):
        normalized = []
        for item in raw_ground_truths:
            if item is None:
                continue
            if isinstance(item, dict) and item.get("answer") is not None:
                normalized.append(str(item.get("answer")))
            else:
                normalized.append(str(item))
        return normalized or [FIXED_GROUND_TRUTH]

    if isinstance(raw_ground_truths, str):
        stripped = raw_ground_truths.strip()
        if not stripped:
            return [FIXED_GROUND_TRUTH]

        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    normalized = []
                    for item in parsed:
                        if item is None:
                            continue
                        if isinstance(item, dict) and item.get("answer") is not None:
                            normalized.append(str(item.get("answer")))
                        else:
                            normalized.append(str(item))
                    return normalized or [FIXED_GROUND_TRUTH]
            except Exception:
                pass

        return [stripped]

    return [str(raw_ground_truths)]

# 设置路径以导入 agent 模块（将仓库根加入 sys.path，以便 import agent）
CURRENT_DIR = Path(__file__).resolve().parent
AGENT_DIR = CURRENT_DIR.parent.parent  # points to repository root (迭代二)
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))
# 为了让 agent/main.py 中的 `from core...` 这类顶级导入生效，
# 还需要把 `agent` 子目录加入 sys.path，使其内部模块可作为顶级模块被导入（例如 core、tools 等）。
AGENT_PKG_DIR = AGENT_DIR / 'agent'
if str(AGENT_PKG_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_PKG_DIR))

# 从 agent 目录导入共享的 pipeline：先尝试按模块名 `main` 导入（agent 目录已加入 sys.path），
# 若仓库中存在 `agent` 包并可通过 `agent.main` 导入，也一并尝试。
try:
    from main import run_agent_pipeline
except Exception:
    try:
        from agent.main import run_agent_pipeline
    except Exception:
        run_agent_pipeline = None


def _run_agent_in_agent_dir(user_query: str, max_loops: int, agent_callback):
    """在 agent 目录工作上下文中运行 agent pipeline，以确保 .env 被正确加载"""
    original_cwd = os.getcwd()
    agent_dir = AGENT_PKG_DIR.parent / 'agent'  # 指向 迭代二/agent
    try:
        os.chdir(agent_dir)
        return run_agent_pipeline(user_query, max_loops, agent_callback)
    finally:
        os.chdir(original_cwd)


# 进行评估
async def perform_evaluation(db: Session, task_id: int):
    '''
    先获取评估任务信息与对应的数据集，将数据集的user_query作为问题输入给agent，获取agent的回答、相关上下文和ground truth，然后进行评测，并将结果保存到数据库中。
    '''
    # 在后台任务内使用新的 DB session，避免使用请求作用域的 session 导致生命周期问题
    db_internal = SessionLocal()
    try:
        task = crud.get_evaluation_task(db_internal, task_id)
    except Exception as e:
        db_internal.close()
        raise e
    if not task:
        db_internal.close()
        return {"status": "failed", "error_message": "Task not found"}

    dataset = crud.get_evaluation_dataset(db_internal, task.dataset_id)
    if not dataset:
        crud.update_evaluation_task_status(db_internal, task_id, "failed", error_message="Dataset not found")
        db_internal.close()
        return {"status": "failed", "error_message": "Dataset not found"}

    crud.update_evaluation_task_status(db_internal, task_id, "running")

    try:
        evaluator = get_evaluator(task.method)
        if evaluator is not None:
            # 获取数据集的 user_query 作为问题（pipeline 接收单个字符串）
            user_query = dataset.data_samples

            # 初始化容器
            answers = []
            contexts = []
            ground_truths = _resolve_ground_truths(dataset.ground_truths)

            # 调用 Agent 的 pipeline（在独立线程中执行以不阻塞事件循环）
            if run_agent_pipeline is None:
                raise RuntimeError("Agent pipeline not available (failed to import agent.main.run_agent_pipeline)")

            # 使用 asyncio.to_thread 在线程池中运行阻塞的 pipeline（通过包装器以确保工作目录正确 .env 可加载）
            try:
                agent_timeout_sec = int(os.getenv("EVAL_AGENT_TIMEOUT_SEC", "1800"))
                res = await asyncio.wait_for(
                    asyncio.to_thread(_run_agent_in_agent_dir, user_query, 10, None),
                    timeout=agent_timeout_sec,
                )
            except asyncio.TimeoutError:
                timeout_message = f"Agent execution timed out after {agent_timeout_sec} seconds"
                print(f"[Task {task_id}] {timeout_message}")
                crud.update_evaluation_task_status(db_internal, task_id, "failed", error_message=timeout_message)
                db_internal.close()
                return {"status": "failed", "error_message": timeout_message}
            except Exception as e:
                import traceback
                full_error = f"Agent execution error: {str(e)}\n{traceback.format_exc()}"
                print(f"[Task {task_id}] {full_error}")
                crud.update_evaluation_task_status(db_internal, task_id, "failed", error_message=f"Agent execution error: {str(e)}")
                db_internal.close()
                return {"status": "failed", "error_message": str(e)}

            # 从 agent 返回值中抽取信息
            answer = res.get('writer_result', 'No answer') if isinstance(res, dict) else 'No answer'
            answers.append(answer)

            traces = res.get('traces', []) if isinstance(res, dict) else []
            contexts_list = [step.get('observation', '') for step in traces if isinstance(step, dict)]
            contexts.append(contexts_list)

            # 使用评估器进行评测
            evaluation_result = evaluator.evaluate([user_query], answers, contexts, ground_truths)
            results = {
                "task_id": task_id,
                "task_name": task.task_name,
                "dataset_id": task.dataset_id,
                "method": task.method,
                "question": user_query,
                "answer": answer,
                "ground_truths": ground_truths,
                "traces": traces,
                **(evaluation_result if isinstance(evaluation_result, dict) else {"raw_result": evaluation_result}),
            }

            # 将结果保存到数据库
            crud.update_evaluation_task_status(db_internal, task_id, "completed", results=results)
            db_internal.close()
            return {"status": "completed", "results": results}
        else:
            crud.update_evaluation_task_status(db_internal, task_id, "failed", error_message="Unsupported method")
            db_internal.close()
            return {"status": "failed", "error_message": "Unsupported method"}

    except Exception as e:
        try:
            crud.update_evaluation_task_status(db_internal, task_id, "failed", error_message=str(e))
        except Exception:
            pass
        db_internal.close()
        return {"status": "failed", "error_message": str(e)}
