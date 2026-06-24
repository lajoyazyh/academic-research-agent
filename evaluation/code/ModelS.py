from sqlalchemy import Column, Integer, String, DateTime, Text, JSON
from sqlalchemy.sql import func
from database import Base

# 数据模型 评测任务和评测数据集
class EvaluationTask(Base):
    __tablename__ = "evaluation_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_name = Column(String, index=True)
    agent_id = Column(String)
    dataset_id = Column(Integer)
    method = Column(String)
    status = Column(String, default="pending")  # pending, running, completed, failed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    results = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

class EvaluationDataset(Base):
    __tablename__ = "evaluation_datasets"

    id = Column(Integer, primary_key=True, index=True)
    dataset_name = Column(String, index=True)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    data_samples = Column(String)  # Single user_query string
    ground_truths = Column(JSON, nullable=True)

