from sqlalchemy.orm import Session
import ModelS 
from schemas import EvaluationTaskCreate, EvaluationDatasetCreate
from typing import List

# 数据库操作
def create_evaluation_task(db: Session, task: EvaluationTaskCreate):
    db_task = ModelS.EvaluationTask(**task.model_dump())
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task

def get_evaluation_task(db: Session, task_id: int):
    return db.query(ModelS.EvaluationTask).filter(ModelS.EvaluationTask.id == task_id).first()

def get_evaluation_tasks(db: Session, skip: int = 0, limit: int = 100):
    return db.query(ModelS.EvaluationTask).offset(skip).limit(limit).all()

def update_evaluation_task_status(db: Session, task_id: int, status: str, results: dict = None, error_message: str = None):
    db_task = db.query(ModelS.EvaluationTask).filter(ModelS.EvaluationTask.id == task_id).first()
    if db_task:
        db_task.status = status
        if results:
            db_task.results = results
        if error_message:
            db_task.error_message = error_message
        db.commit()
        db.refresh(db_task)
    return db_task

def delete_evaluation_task(db: Session, task_id: int):
    db_task = db.query(ModelS.EvaluationTask).filter(ModelS.EvaluationTask.id == task_id).first()
    if db_task:
        db.delete(db_task)
        db.commit()
    return db_task

# Evaluation Datasets CRUD
def create_evaluation_dataset(db: Session, dataset: EvaluationDatasetCreate):
    db_dataset = ModelS.EvaluationDataset(**dataset.model_dump())
    db.add(db_dataset)
    db.commit()
    db.refresh(db_dataset)
    return db_dataset

def get_evaluation_dataset(db: Session, dataset_id: int):
    return db.query(ModelS.EvaluationDataset).filter(ModelS.EvaluationDataset.id == dataset_id).first()

def get_evaluation_datasets(db: Session, skip: int = 0, limit: int = 100):
    return db.query(ModelS.EvaluationDataset).offset(skip).limit(limit).all()

def delete_evaluation_dataset(db: Session, dataset_id: int):
    db_dataset = db.query(ModelS.EvaluationDataset).filter(ModelS.EvaluationDataset.id == dataset_id).first()
    if db_dataset:
        db.delete(db_dataset)
        db.commit()
    return db_dataset
