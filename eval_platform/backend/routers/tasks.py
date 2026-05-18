from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import crud,ModelS,schemas,database,services
import asyncio

router = APIRouter(prefix="/tasks", tags=["tasks"])

# 创建评估任务
@router.post("/create", response_model=schemas.EvaluationTaskResponse)
def create_evaluation_task(task: schemas.EvaluationTaskCreate, db: Session = Depends(database.get_db)):
    return crud.create_evaluation_task(db=db, task=task)

# 进行评测
@router.post("/evaluate/{task_id}")
async def perform_evaluation(task_id: int, db: Session = Depends(database.get_db)):
    task = crud.get_evaluation_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    crud.update_evaluation_task_status(db, task_id, "queued")
    # Run evaluation in background
    asyncio.create_task(services.perform_evaluation(db, task_id))
    return {"status": "Evaluation started"}

# 获取评测任务状态
@router.get("/status/{task_id}", response_model=schemas.EvaluationTaskResponse)
def get_evaluation_status(task_id: int, db: Session = Depends(database.get_db)):
    task = crud.get_evaluation_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

# 获取评测任务结果
@router.get("/results/{task_id}", response_model=schemas.EvaluationTaskResponse)
def get_evaluation_results(task_id: int, db: Session = Depends(database.get_db)):
    task = crud.get_evaluation_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="Evaluation not completed")
    return task

# 获取评测任务列表
@router.get("/list", response_model=schemas.EvaluationTaskList)
def get_evaluation_tasks(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    tasks = crud.get_evaluation_tasks(db, skip=skip, limit=limit)
    if not tasks:
        raise HTTPException(status_code=404, detail="No tasks found")
    return {"tasks": tasks}

# 获取评测任务详情
@router.get("/detail/{task_id}", response_model=schemas.EvaluationTaskResponse)
def get_evaluation_task_detail(task_id: int, db: Session = Depends(database.get_db)):
    task = crud.get_evaluation_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

# 删除评测任务
@router.delete("/delete/{task_id}", response_model=schemas.StatusResponse)
def delete_evaluation_task(task_id: int, db: Session = Depends(database.get_db)):
    task = crud.delete_evaluation_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "success"}
