from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import crud, ModelS, schemas, database

router = APIRouter(prefix="/datasets", tags=["datasets"])

# 创建评测数据集
@router.post("/create", response_model=schemas.EvaluationDatasetResponse)
def create_evaluation_dataset(dataset: schemas.EvaluationDatasetCreate, db: Session = Depends(database.get_db)):
    return crud.create_evaluation_dataset(db=db, dataset=dataset)

# 获取数据集列表
@router.get("/list", response_model=schemas.EvaluationDatasetList)
def get_evaluation_datasets(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    datasets = crud.get_evaluation_datasets(db, skip=skip, limit=limit)
    return {"datasets": datasets}

# 获取数据集详情
@router.get("/detail/{dataset_id}", response_model=schemas.EvaluationDatasetResponse)
def get_evaluation_dataset_detail(dataset_id: int, db: Session = Depends(database.get_db)):
    dataset = crud.get_evaluation_dataset(db, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset

# 删除数据集
@router.delete("/delete/{dataset_id}", response_model=schemas.StatusResponse)
def delete_evaluation_dataset(dataset_id: int, db: Session = Depends(database.get_db)):
    dataset = crud.delete_evaluation_dataset(db, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"status": "success"}

