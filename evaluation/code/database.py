from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 数据库地址固定指向 evaluation 目录，避免从不同工作目录启动时落到空库
SQLITE_DB_PATH = Path(__file__).resolve().parents[1] / "eval_platform.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{SQLITE_DB_PATH.as_posix()}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# 获取数据库
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
