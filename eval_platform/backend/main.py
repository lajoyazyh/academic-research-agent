import sys
import asyncio

# 修复 Windows 上 "Event loop is closed" 问题
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn
from api import app
from dotenv import load_dotenv
from pathlib import Path

# 显式加载仓库根的 .env，保证无论从哪个工作目录启动都能读取到配置
ROOT_ENV = Path(__file__).resolve().parents[2] / '.env'
load_dotenv(ROOT_ENV)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)
