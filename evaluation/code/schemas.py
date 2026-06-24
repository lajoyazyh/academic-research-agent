from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

# 数据传递模型
class EvaluationTaskCreate(BaseModel):
    task_name: str
    agent_id: str
    dataset_id: int
    method: str

class EvaluationTaskResponse(BaseModel):
    id: int
    task_name: str
    agent_id: str
    dataset_id: int
    method: str
    status: str
    created_at: datetime
    results: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

class EvaluationTaskList(BaseModel):
    tasks: List[EvaluationTaskResponse]

# Evaluation Dataset Schemas
class EvaluationDatasetCreate(BaseModel):
    dataset_name: str
    description: str
    data_samples: str  # Single user_query string
    ground_truths: str

class EvaluationDatasetResponse(BaseModel):
    id: int
    dataset_name: str
    description: str
    created_at: datetime
    data_samples: str  # Single user_query string
    ground_truths: str

class EvaluationDatasetList(BaseModel):
    datasets: List[EvaluationDatasetResponse]

# Generic Response
class StatusResponse(BaseModel):
    status: str
    error_message: Optional[str] = None

