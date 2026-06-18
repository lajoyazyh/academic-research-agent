#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Agent 评估独立运行脚本（迭代三）
=====================================

无需启动 Web 服务，从命令行一键完成：
    1. 从 eval_platform.db 加载数据集
    2. 调用 Agent Pipeline（agent/main.py 中的 run_agent_pipeline）
    3. 使用 evaluation_methods 中的评估器进行评测
    4. 将结果保存到数据库 + 输出 JSON 文件

支持三种运行模式：
    【模式 A：完整评估】运行 Agent + 评估（默认）
        python run_eval.py --dataset-id 1

    【模式 B：从文件分别导入 traces 和 answer 直接评估】
        python run_eval.py --dataset-id 1 --from-traces traces.json --from-answer answer.txt --method result_oriented

    【模式 C：从数据库已存任务导入 answer + traces 重新评估】
        python run_eval.py --dataset-id 1 --from-task 5 --method process_oriented

用法示例：
    # 完整评估
    python run_eval.py --dataset-id 1

    # traces 和 answer 分别从独立文件导入（跳过 Agent 执行）
    python run_eval.py --dataset-id 1 --from-traces my_traces.json --from-answer my_answer.txt --method result_oriented

    # 仅导入 traces 文件（需同时指定 --from-answer 提供 answer）
    python run_eval.py --dataset-id 1 --from-traces traces.json --from-answer review.md

    # 从数据库任务 ID=3 的已有结果中提取 traces 重新评估
    python run_eval.py --dataset-id 1 --from-task 3 --method process_oriented

    # 指定参数
    python run_eval.py --dataset-id 1 --method result_oriented --max-loops 15 --timeout 1200

    # 不保存到数据库，仅输出 JSON
    python run_eval.py --dataset-id 1 --no-save-db --output my_results.json
"""

import sys
import os
import json
import time
import argparse
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════
# 0. 修复 Windows asyncio 事件循环策略
# ═══════════════════════════════════════════════════════════════
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ═══════════════════════════════════════════════════════════════
# 1. 路径设置：确保能导入 agent 和 evaluation/code 模块
# ═══════════════════════════════════════════════════════════════
SCRIPT_DIR = Path(__file__).resolve().parent          # 迭代三/evaluation/
CODE_DIR = SCRIPT_DIR / "code"                        # 迭代三/evaluation/code/
AGENT_DIR = SCRIPT_DIR.parent                         # 迭代三/
AGENT_PKG_DIR = AGENT_DIR / "agent"                   # 迭代三/agent/
ROOT_DIR = AGENT_DIR.parent                           # code_repository/

# 将路径加入 sys.path（避免污染已有路径）
for p in [str(CODE_DIR), str(AGENT_DIR), str(AGENT_PKG_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# ═══════════════════════════════════════════════════════════════
# 2. 加载 .env 环境变量
# ═══════════════════════════════════════════════════════════════
from dotenv import load_dotenv, find_dotenv

# 优先加载仓库根 .env；如果不存在，自动回退到迭代三/agent/.env。
env_candidates = [
    ROOT_DIR / ".env",
    AGENT_DIR / ".env",
    AGENT_PKG_DIR / ".env",
]
for env_path in env_candidates:
    if env_path.exists():
        load_dotenv(env_path, override=False)
fallback_env = find_dotenv(usecwd=True)
if fallback_env:
    load_dotenv(fallback_env, override=False)

# ═══════════════════════════════════════════════════════════════
# 3. 导入评估相关模块
# ═══════════════════════════════════════════════════════════════
from database import SessionLocal, engine
from ModelS import Base, EvaluationTask, EvaluationDataset
import crud
import schemas
from evaluation_methods import get_evaluator


# ═══════════════════════════════════════════════════════════════
# 4. 默认 ground truth（当数据集未提供时使用）
# ═══════════════════════════════════════════════════════════════
FIXED_GROUND_TRUTH = "成功检索相关文献、完成多源证据综合，并输出含引用的结构化综述结论。"


def _resolve_ground_truths(raw_ground_truths) -> List[str]:
    """优先使用数据集中的 ground_truths；为空时回退默认 ground truth。"""
    import json as _json

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
                parsed = _json.loads(stripped)
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


# ═══════════════════════════════════════════════════════════════
# 5. Agent Pipeline 导入
# ═══════════════════════════════════════════════════════════════
run_agent_pipeline = None

def _import_agent_pipeline():
    """尝试多种方式导入 run_agent_pipeline。"""
    global run_agent_pipeline
    if run_agent_pipeline is not None:
        return

    # 方式 1：从 agent 子目录直接导入（AGENT_PKG_DIR 已在 sys.path 中）
    try:
        from main import run_agent_pipeline as rap
        run_agent_pipeline = rap
        print("[导入] 从 agent/main.py 导入 run_agent_pipeline 成功")
        return
    except Exception as e:
        print(f"[导入] 方式1 失败: {e}")

    # 方式 2：通过 agent 包名导入
    try:
        from agent.main import run_agent_pipeline as rap
        run_agent_pipeline = rap
        print("[导入] 从 agent.main 导入 run_agent_pipeline 成功")
        return
    except Exception as e:
        print(f"[导入] 方式2 失败: {e}")

    raise ImportError(
        "无法导入 run_agent_pipeline。请确保 agent/main.py 中存在该函数，"
        "且所有依赖（core、tools、llms 等）已正确安装。"
    )


def _run_agent_in_agent_dir(user_query: str, max_loops: int):
    """在 agent 目录工作上下文中运行 agent pipeline，确保 .env 正确加载。"""
    original_cwd = os.getcwd()
    try:
        os.chdir(str(AGENT_PKG_DIR))
        return run_agent_pipeline(user_query, max_loops, None)
    finally:
        os.chdir(original_cwd)


# ═══════════════════════════════════════════════════════════════
# 6. 数据库初始化
# ═══════════════════════════════════════════════════════════════
def init_db():
    """创建所有表（如果不存在）。"""
    Base.metadata.create_all(bind=engine)


# ═══════════════════════════════════════════════════════════════
# 7. 单次评估执行（对齐 services.py 的评估流程）
# ═══════════════════════════════════════════════════════════════
async def run_single_evaluation(
    dataset: EvaluationDataset,
    method: str = "explicit_metrics",
    max_loops: int = 10,
    timeout_sec: int = 1800,
    task_name: str = "Auto Eval",
) -> Dict[str, Any]:
    """
    对单个数据集执行一次完整的 Agent 运行 + 评估。
    流程与 services.py 的 perform_evaluation() 保持一致：
        1. 从数据集获取 user_query 和 ground_truths
        2. 调用 run_agent_pipeline 获取 answer + traces（上下文）
        3. 使用 get_evaluator(method) 创建评估器并评测
        4. 组装结果（与 services.py 同构）

    Args:
        dataset: 数据库中的数据集对象
        method: 评估方法 (result_oriented / process_oriented / explicit_metrics)
        max_loops: Agent 最大循环数
        timeout_sec: 单次 Agent 执行超时（秒）
        task_name: 任务名称

    Returns:
        dict: 评估结果（结构对齐 services.py）
    """
    # 1. 获取问题与 ground truth
    user_query = dataset.data_samples
    ground_truths = _resolve_ground_truths(dataset.ground_truths)

    print(f"\n{'='*70}")
    print(f"  任务: {task_name}")
    print(f"  数据集: {dataset.dataset_name} (ID={dataset.id})")
    print(f"  方法: {method}")
    print(f"  问题: {user_query[:100]}{'...' if len(user_query) > 100 else ''}")
    print(f"  Max Loops: {max_loops} | Timeout: {timeout_sec}s")
    print(f"{'='*70}")

    # 2. 调用 Agent Pipeline — 在独立线程中执行，对齐 services.py
    if run_agent_pipeline is None:
        raise RuntimeError("Agent pipeline not available (failed to import agent.main.run_agent_pipeline)")

    print(f"\n🚀 [Agent] 开始执行 Agent Pipeline ...")
    agent_start = time.time()

    try:
        res = await asyncio.wait_for(
            asyncio.to_thread(_run_agent_in_agent_dir, user_query, max_loops),
            timeout=timeout_sec,
        )
    except asyncio.TimeoutError:
        timeout_message = f"Agent execution timed out after {timeout_sec} seconds"
        print(f"⏱️  [Agent] {timeout_message}")
        return {
            "status": "failed",
            "error_message": timeout_message,
        }
    except Exception as e:
        import traceback as _tb
        full_error = f"Agent execution error: {str(e)}\n{_tb.format_exc()}"
        print(f"❌ [Agent] {full_error}")
        return {
            "status": "failed",
            "error_message": f"Agent execution error: {str(e)}",
        }

    agent_elapsed = time.time() - agent_start
    print(f"✅ [Agent] 执行完成，耗时 {agent_elapsed:.1f}s")

    # 3. 从 agent 返回值中抽取信息（与 services.py 一致）
    answer = res.get("writer_result", "No answer") if isinstance(res, dict) else "No answer"
    traces = res.get("traces", []) if isinstance(res, dict) else []

    # 构建上下文列表：从 traces 中提取 observation 字段
    contexts_list = [
        step.get("observation", "")
        for step in traces
        if isinstance(step, dict)
    ]

    print(f"  📝 Answer 长度: {len(answer)} 字符")
    print(f"  📊 Traces 步数: {len(traces)}")
    print(f"  📚 Contexts 条数: {len(contexts_list)}")

    # 4. 使用评估器进行评测（与 services.py 一致）
    print(f"\n📏 [Eval] 开始评估 (method={method}) ...")
    eval_start = time.time()

    try:
        evaluator = get_evaluator(method)
        if evaluator is None:
            raise RuntimeError(f"Unsupported evaluation method: {method}")

        # 构造为列表形式，对齐 services.py 的调用签名
        answers = [answer]
        contexts = [contexts_list]

        evaluation_result = evaluator.evaluate(
            [user_query], answers, contexts, ground_truths,
        )
    except Exception as e:
        import traceback as _tb
        full_error = f"Evaluation error: {str(e)}\n{_tb.format_exc()}"
        print(f"❌ [Eval] {full_error}")
        return {
            "status": "failed",
            "error_message": str(e),
        }

    eval_elapsed = time.time() - eval_start
    print(f"✅ [Eval] 评估完成，耗时 {eval_elapsed:.1f}s")

    # 打印评分摘要
    if isinstance(evaluation_result, dict):
        scores = evaluation_result.get("scores", {})
        if scores:
            print(f"\n  📊 评分摘要:")
            for k, v in scores.items():
                print(f"     {k}: {v:.4f}" if isinstance(v, float) else f"     {k}: {v}")

    # 5. 组装结果（结构对齐 services.py）
    results = {
        "task_name": task_name,
        "dataset_id": dataset.id,
        "method": method,
        "question": user_query,
        "answer": answer,
        "ground_truths": ground_truths,
        "traces": traces,
        **(evaluation_result if isinstance(evaluation_result, dict) else {"raw_result": evaluation_result}),
    }

    return {
        "status": "completed",
        "results": results,
    }


# ═══════════════════════════════════════════════════════════════
# 7b. 仅评估模式（跳过 Agent 执行，直接对已有 answer/trace 打分）
# ═══════════════════════════════════════════════════════════════
def run_eval_only(
    dataset: EvaluationDataset,
    method: str,
    answer: str,
    traces: List[dict],
    task_name: str = "Eval Only",
) -> Dict[str, Any]:
    """
    仅执行评估器，不运行 Agent Pipeline。
    用于对已有的 answer + traces 进行重新评估（更换评估方法）。

    Args:
        dataset: 数据集对象（提供 user_query 和 ground_truths）
        method: 评估方法
        answer: 已有的 Agent 回答文本
        traces: 已有的 Agent 执行轨迹
        task_name: 任务名称

    Returns:
        dict: 评估结果（与 run_single_evaluation 同构）
    """
    user_query = dataset.data_samples
    ground_truths = _resolve_ground_truths(dataset.ground_truths)

    # 从 traces 中提取 observation 作为上下文
    contexts_list = [
        step.get("observation", "")
        for step in traces
        if isinstance(step, dict)
    ]

    print(f"\n{'='*70}")
    print(f"  任务: {task_name}")
    print(f"  数据集: {dataset.dataset_name} (ID={dataset.id})")
    print(f"  方法: {method}")
    print(f"  问题: {user_query[:100]}{'...' if len(user_query) > 100 else ''}")
    print(f"  模式: 仅评估（跳过 Agent 执行）")
    print(f"  📝 Answer 长度: {len(answer)} 字符")
    print(f"  📊 Traces 步数: {len(traces)}")
    print(f"  📚 Contexts 条数: {len(contexts_list)}")
    print(f"{'='*70}")

    # ━━━ 评估器评测 ━━━
    print(f"\n📏 [Eval] 开始评估 (method={method}) ...")
    eval_start = time.time()

    try:
        evaluator = get_evaluator(method)
        if evaluator is None:
            raise RuntimeError(f"Unsupported evaluation method: {method}")

        evaluation_result = evaluator.evaluate(
            [user_query],
            [answer],
            [contexts_list],
            ground_truths,
        )
    except Exception as e:
        import traceback as _tb
        full_error = f"Evaluation error: {str(e)}\n{_tb.format_exc()}"
        print(f"❌ [Eval] {full_error}")
        return {
            "status": "failed",
            "error_message": str(e),
        }

    eval_elapsed = time.time() - eval_start
    print(f"✅ [Eval] 评估完成，耗时 {eval_elapsed:.1f}s")

    # 打印评分摘要
    if isinstance(evaluation_result, dict):
        scores = evaluation_result.get("scores", {})
        if scores:
            print(f"\n  📊 评分摘要:")
            for k, v in scores.items():
                print(f"     {k}: {v:.7f}" if isinstance(v, float) else f"     {k}: {v}")

    # 组装结果
    results = {
        "task_name": task_name,
        "dataset_id": dataset.id,
        "method": method,
        "question": user_query,
        "answer": answer,
        "ground_truths": ground_truths,
        "traces": traces,
        **(evaluation_result if isinstance(evaluation_result, dict) else {"raw_result": evaluation_result}),
    }

    return {
        "status": "completed",
        "results": results,
    }


# ═══════════════════════════════════════════════════════════════
# 7c. 数据加载辅助函数
# ═══════════════════════════════════════════════════════════════
def _load_traces_from_file(file_path: str) -> List[dict]:
    """
    从 JSON 文件加载 traces（执行轨迹）。
    支持格式：
        - 纯数组: [{"thought": ..., "action": ..., "observation": ...}, ...]
        - 对象含 traces 键: {"traces": [...]}
        - 对象含 results.traces: {"results": {"traces": [...]}}
        - 对象含 samples[0].traces: {"samples": [{"traces": [...]}]}
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        # 检查是否为 trace 数组（包含 thought/action/observation 字段）
        if data and isinstance(data[0], dict) and "observation" in data[0]:
            return data
        # 否则尝试取第一个元素的 traces
        return _pick_traces(data[0]) if data else []

    if isinstance(data, dict):
        # 尝试多种嵌套路径
        return _pick_traces(data)

    raise ValueError(f"无法从文件 {file_path} 解析 traces，格式不支持")


def _load_answer_from_file(file_path: str) -> str:
    """
    从文件加载 answer（Agent 回答）。
    支持格式：
        - JSON 含 answer 键: {"answer": "..."} / {"results": {"answer": "..."}}
        - 纯文本文件 (.txt / .md)：直接读取全部内容作为 answer
        - JSON 对象含 writer_result: {"writer_result": "..."}
    """
    # 判断是否为纯文本（.txt / .md）
    ext = Path(file_path).suffix.lower()
    if ext in {".txt", ".md"}:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    # JSON 文件
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, str):
        return data

    if isinstance(data, dict):
        return _pick_answer(data)

    raise ValueError(f"无法从文件 {file_path} 解析 answer，格式不支持")


def _load_answer_and_traces_from_task(task_id: int, db) -> list:
    """从数据库任务记录中提取 answer 和 traces。"""
    task = crud.get_evaluation_task(db, task_id)
    if not task:
        raise ValueError(f"任务 ID={task_id} 不存在")
    if not task.results:
        raise ValueError(f"任务 ID={task_id} 的 results 字段为空")

    results = task.results if isinstance(task.results, dict) else json.loads(str(task.results))

    answer = results.get("answer", "")
    traces = results.get("traces", [])
    return [(results, answer, traces)]


def _pick_answer(data: dict) -> str:
    """从字典中查找 answer 字段。"""
    return data.get("answer") or data.get("writer_result") or data.get("researcher_result") or ""


def _pick_traces(data: dict) -> list:
    """从字典中查找 traces 字段。"""
    return data.get("traces") or data.get("results", {}).get("traces") or []


def _extract_samples(items: list) -> list:
    """从列表中提取 (source_dict, answer, traces) 三元组。"""
    samples = []
    for item in items:
        if isinstance(item, dict):
            inner = item.get("results", item)
            answer = _pick_answer(inner)
            traces = _pick_traces(inner)
            samples.append((inner, answer, traces))
        else:
            samples.append(({}, str(item), []))
    return samples


# ═══════════════════════════════════════════════════════════════
# 8. 主入口
# ═══════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="Agent 评估独立运行器（迭代三）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 模式 A：完整评估（运行 Agent + 评估）
  python run_eval.py --dataset-id 1
  python run_eval.py --dataset-id 1 --method result_oriented --max-loops 15

  # 模式 B：从独立文件分别导入 traces 和 answer 直接评估
  python run_eval.py --dataset-id 1 --from-traces traces.json --from-answer answer.txt --method result_oriented

  # 模式 C：从数据库已有任务导入重新评估
  python run_eval.py --dataset-id 1 --from-task 3 --method process_oriented

  # 其他
  python run_eval.py --dataset-id 1 --no-save-db --output my_results.json
  python run_eval.py --dataset-id 1 --sample 3 --timeout 600
        """,
    )

    parser.add_argument(
        "--dataset-id", "-d",
        type=int,
        required=True,
        help="从数据库 evaluation_datasets 表加载的数据集 ID",
    )
    parser.add_argument(
        "--method", "-m",
        type=str,
        default="explicit_metrics",
        choices=["result_oriented", "process_oriented", "explicit_metrics"],
        help="评估方法（默认: explicit_metrics）",
    )

    # ━━━ 模式 A 参数：完整评估 ━━━
    parser.add_argument(
        "--max-loops",
        type=int,
        default=20,
        help="[模式A] Agent 最大执行循环数（默认: 10）",
    )
    parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=None,
        help="[模式A] Agent 执行超时秒数（默认读取 EVAL_AGENT_TIMEOUT_SEC，未设置则为 1800）",
    )

    # ━━━ 模式 B：从文件导入 traces / answer ━━━
    parser.add_argument(
        "--from-traces",
        type=str,
        default=None,
        metavar="PATH",
        help="[模式B] 从 JSON 文件导入 traces（执行轨迹），跳过 Agent 执行。需配合 --from-answer 使用",
    )
    parser.add_argument(
        "--from-answer",
        type=str,
        default=None,
        metavar="PATH",
        help="[模式B] 从文本文件导入 answer（Agent 回答）。需配合 --from-traces 使用",
    )

    # ━━━ 模式 C：从数据库任务导入 ━━━
    parser.add_argument(
        "--from-task",
        type=int,
        default=None,
        metavar="TASK_ID",
        help="[模式C] 从数据库已有任务中提取 answer + traces，跳过 Agent 执行，重新评估",
    )

    # ━━━ 通用参数 ━━━
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="eval_results.json",
        help="结果 JSON 输出路径（默认: eval_results.json）",
    )
    parser.add_argument(
        "--task-name",
        type=str,
        default=None,
        help="数据库中的任务名称（默认: 自动生成）",
    )
    parser.add_argument(
        "--save-db",
        action="store_true",
        default=True,
        help="保存结果到 eval_platform.db（默认开启）",
    )
    parser.add_argument(
        "--no-save-db",
        action="store_false",
        dest="save_db",
        help="不保存结果到数据库",
    )
    parser.add_argument(
        "--sample", "-s",
        type=int,
        default=0,
        help="[模式B/模式A多样本] 只处理前 N 个样本（0=全部）",
    )

    args = parser.parse_args()

    # 互斥检查
    from_file = bool(args.from_traces or args.from_answer)
    from_task = bool(args.from_task)

    if from_file and from_task:
        print("❌ --from-traces/--from-answer 和 --from-task 不能同时使用")
        sys.exit(1)

    if from_file and not (args.from_traces and args.from_answer):
        print("❌ --from-traces 和 --from-answer 必须同时指定")
        sys.exit(1)

    is_eval_only = from_file or from_task

    # 超时时间（仅模式 A 使用）
    if args.timeout is None:
        args.timeout = int(os.getenv("EVAL_AGENT_TIMEOUT_SEC", "1800"))

    # ━━━ 初始化 ━━━
    mode_label = "仅评估" if is_eval_only else "完整评估"
    if from_file:
        mode_label += f"（traces: {args.from_traces}, answer: {args.from_answer}）"
    elif from_task:
        mode_label += f"（从任务 ID={args.from_task}）"

    print("=" * 70)
    print("  Agent 评估独立运行器（迭代三）")
    print(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  模式: {mode_label}")
    print("=" * 70)

    # 初始化数据库
    init_db()
    print(f"📂 数据库: {CODE_DIR.parent / 'eval_platform.db'}")

    # ━━━ 加载数据集 ━━━
    db = SessionLocal()
    try:
        dataset = crud.get_evaluation_dataset(db, args.dataset_id)
        if not dataset:
            print(f"❌ 未找到数据集 ID={args.dataset_id}")
            db.close()
            sys.exit(1)

        print(f"📋 数据集: {dataset.dataset_name}")
        print(f"   描述: {dataset.description or '(无)'}")
        print(f"   问题: {dataset.data_samples[:120]}{'...' if len(dataset.data_samples) > 120 else ''}")

        # 生成任务名称
        suffix = "_evalonly" if is_eval_only else ""
        task_name = args.task_name or f"eval_{dataset.dataset_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{suffix}"

        # ━━━ 创建数据库任务记录 ━━━
        if args.save_db:
            task_create = schemas.EvaluationTaskCreate(
                task_name=task_name,
                agent_id="default-agent",
                dataset_id=dataset.id,
                method=args.method,
            )
            db_task = crud.create_evaluation_task(db, task_create)
            task_id = db_task.id
            print(f"📝 数据库任务已创建: ID={task_id}")
            crud.update_evaluation_task_status(db, task_id, "running")
        else:
            task_id = None

        # ━━━ 分支：完整评估 vs 仅评估 ━━━
        if is_eval_only:
            # ============ 模式 B / C：仅评估 ============
            _run_eval_only_main(args, dataset, db, task_name, task_id)
        else:
            # ============ 模式 A：完整评估 ============
            _run_full_eval_main(args, dataset, db, task_name, task_id)

    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
# 8a. 模式 A：完整评估主流程
# ═══════════════════════════════════════════════════════════════
def _run_full_eval_main(args, dataset, db, task_name, task_id):
    """模式 A：运行 Agent Pipeline + 评估器。"""
    # 导入 Agent Pipeline（仅模式 A 需要）
    _import_agent_pipeline()

    # 多样本支持
    raw_samples = dataset.data_samples
    try:
        parsed = json.loads(raw_samples)
        if isinstance(parsed, list) and len(parsed) > 0:
            samples = parsed
            is_multi_sample = True
        else:
            samples = [raw_samples]
            is_multi_sample = False
    except (json.JSONDecodeError, TypeError):
        samples = [raw_samples]
        is_multi_sample = False

    if args.sample > 0:
        samples = samples[:args.sample]

    print(f"\n📊 共 {len(samples)} 个样本待评估" + (" (JSON 数组模式)" if is_multi_sample else ""))

    all_results = []
    for idx, sample in enumerate(samples):
        sample_query = sample if isinstance(sample, str) else sample.get("user_query", str(sample))
        print(f"\n{'─'*50}")
        print(f"  📌 样本 {idx + 1}/{len(samples)}: {sample_query[:80]}...")
        print(f"{'─'*50}")

        dataset.data_samples = sample_query

        eval_outcome = asyncio.run(
            run_single_evaluation(
                dataset=dataset,
                method=args.method,
                max_loops=args.max_loops,
                timeout_sec=args.timeout,
                task_name=f"{task_name}_sample{idx + 1}",
            )
        )
        all_results.append(eval_outcome)

        if eval_outcome.get("status") == "completed":
            print(f"  ✅ 样本 {idx + 1} 完成")
        else:
            print(f"  ❌ 样本 {idx + 1} 失败: {eval_outcome.get('error_message', 'Unknown')}")

    dataset.data_samples = raw_samples

    # 汇总 & 保存
    _summarize_and_save(all_results, args, dataset, db, task_name, task_id, is_multi_sample)


# ═══════════════════════════════════════════════════════════════
# 8b. 模式 B / C：仅评估主流程
# ═══════════════════════════════════════════════════════════════
def _run_eval_only_main(args, dataset, db, task_name, task_id):
    """模式 B/C：跳过 Agent，从文件或数据库任务加载 answer + traces 直接评估。"""
    # 加载 answer + traces
    if args.from_traces and args.from_answer:
        # ━━━ 模式 B：分别从独立文件导入 traces 和 answer ━━━
        traces_path = args.from_traces
        answer_path = args.from_answer
        if not os.path.isabs(traces_path):
            traces_path = str(SCRIPT_DIR / traces_path)
        if not os.path.isabs(answer_path):
            answer_path = str(SCRIPT_DIR / answer_path)

        print(f"📂 从文件加载 traces: {traces_path}")
        print(f"📂 从文件加载 answer: {answer_path}")

        try:
            traces = _load_traces_from_file(traces_path)
        except Exception as e:
            print(f"❌ 加载 traces 文件失败: {e}")
            if args.save_db and task_id:
                crud.update_evaluation_task_status(db, task_id, "failed", error_message=str(e))
            return

        try:
            answer = _load_answer_from_file(answer_path)
        except Exception as e:
            print(f"❌ 加载 answer 文件失败: {e}")
            if args.save_db and task_id:
                crud.update_evaluation_task_status(db, task_id, "failed", error_message=str(e))
            return

        # 单样本：包装为 (source_dict, answer, traces)
        loaded = [({"question": dataset.data_samples}, answer, traces)]

    else:
        # ━━━ 模式 C：从数据库任务加载 ━━━
        print(f"📂 从数据库任务加载: ID={args.from_task}")
        try:
            loaded = _load_answer_and_traces_from_task(args.from_task, db)
        except Exception as e:
            print(f"❌ 加载任务失败: {e}")
            if args.save_db and task_id:
                crud.update_evaluation_task_status(db, task_id, "failed", error_message=str(e))
            return

    # 限制样本数
    if args.sample > 0:
        loaded = loaded[:args.sample]

    is_multi_sample = len(loaded) > 1
    print(f"📊 共 {len(loaded)} 个样本待评估" + (" (多样本)" if is_multi_sample else ""))

    all_results = []
    for idx, (src, answer, traces) in enumerate(loaded):
        if not answer and not traces:
            print(f"\n  ⚠️  样本 {idx + 1}: answer 和 traces 均为空，跳过")
            all_results.append({"status": "failed", "error_message": "answer and traces are empty"})
            continue

        # 尝试从来源数据中提取 question 和 ground_truths
        question = src.get("question") or dataset.data_samples
        ground_truths_raw = src.get("ground_truths")
        if ground_truths_raw is None:
            ground_truths_raw = dataset.ground_truths

        # 构建临时 dataset-like 对象
        class _TempDataset:
            pass
        temp_ds = _TempDataset()
        temp_ds.id = dataset.id
        temp_ds.dataset_name = dataset.dataset_name
        temp_ds.data_samples = question
        temp_ds.ground_truths = ground_truths_raw

        sample_task_name = f"{task_name}_sample{idx + 1}"

        print(f"\n{'─'*50}")
        print(f"  📌 样本 {idx + 1}/{len(loaded)}: {question[:80]}...")
        print(f"{'─'*50}")

        eval_outcome = run_eval_only(
            dataset=temp_ds,
            method=args.method,
            answer=answer,
            traces=traces if isinstance(traces, list) else [],
            task_name=sample_task_name,
        )
        all_results.append(eval_outcome)

        if eval_outcome.get("status") == "completed":
            print(f"  ✅ 样本 {idx + 1} 完成")
        else:
            print(f"  ❌ 样本 {idx + 1} 失败: {eval_outcome.get('error_message', 'Unknown')}")

    # 汇总 & 保存
    _summarize_and_save(all_results, args, dataset, db, task_name, task_id, is_multi_sample)

    if eval_outcome.get("status") == "completed":
        print(f"  ✅ 样本 {idx + 1} 完成")
    else:
        print(f"  ❌ 样本 {idx + 1} 失败: {eval_outcome.get('error_message', 'Unknown')}")

    # 汇总 & 保存
    _summarize_and_save(all_results, args, dataset, db, task_name, task_id, is_multi_sample)


# ═══════════════════════════════════════════════════════════════
# 9. 汇总 & 保存（A/B/C 模式共用）
# ═══════════════════════════════════════════════════════════════
def _summarize_and_save(all_results, args, dataset, db, task_name, task_id, is_multi_sample):
    """汇总评估结果并保存到数据库 + JSON 文件。"""
    if is_multi_sample and len(all_results) > 1:
        sample_results = [r.get("results", r) for r in all_results]
        completed = [r for r in all_results if r.get("status") == "completed"]

        summary_scores = {}
        if completed:
            all_scores_keys = set()
            for r in completed:
                inner = r.get("results", {})
                scores = inner.get("scores", {})
                all_scores_keys.update(scores.keys())
            for key in all_scores_keys:
                values = []
                for r in completed:
                    val = r.get("results", {}).get("scores", {}).get(key)
                    if isinstance(val, (int, float)):
                        values.append(float(val))
                if values:
                    import numpy as np
                    summary_scores[key] = float(np.mean(values))

        final_results = {
            "task_name": task_name,
            "dataset_id": dataset.id,
            "method": args.method,
            "total_samples": len(all_results),
            "completed_samples": len(completed),
            "failed_samples": len(all_results) - len(completed),
            "summary_scores": summary_scores,
            "samples": sample_results,
        }
    else:
        outcome = all_results[0]
        final_results = outcome.get("results", outcome) if outcome.get("status") == "completed" else outcome
        final_results["task_name"] = task_name
        final_results["dataset_id"] = dataset.id
        final_results["method"] = args.method
        final_results["total_samples"] = 1

    # ━━━ 保存到数据库 ━━━
    if args.save_db and task_id:
        try:
            final_status = "completed" if any(r.get("status") == "completed" for r in all_results) else "failed"
            crud.update_evaluation_task_status(db, task_id, final_status, results=final_results)
            print(f"\n💾 结果已保存到数据库 (task_id={task_id})")
        except Exception as e:
            print(f"⚠️  保存到数据库失败: {e}")
            crud.update_evaluation_task_status(db, task_id, "failed", error_message=str(e))

    # ━━━ 保存到 JSON 文件 ━━━
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = SCRIPT_DIR / output_path

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_results, f, ensure_ascii=False, indent=2, default=str)

    print(f"📄 结果已保存到 {output_path}")

    # ━━━ 最终摘要 ━━━
    print(f"\n{'='*70}")
    print(f"  评估完成")
    if isinstance(final_results.get("summary_scores"), dict):
        print(f"  汇总评分:")
        for k, v in final_results["summary_scores"].items():
            print(f"    {k}: {v:.4f}" if isinstance(v, float) else f"    {k}: {v}")
    elif isinstance(final_results.get("scores"), dict):
        print(f"  评分:")
        for k, v in final_results["scores"].items():
            print(f"    {k}: {v:.4f}" if isinstance(v, float) else f"    {k}: {v}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
