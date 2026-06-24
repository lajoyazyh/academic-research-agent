import math
import json as _json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from database import engine
from ModelS import Base
from routers.tasks import router as tasks_router
from routers.datasets import router as datasets_router

Base.metadata.create_all(bind=engine)


def _sanitize_nan(obj):
    """Replace NaN/Inf float with 0.0 recursively."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return 0.0
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nan(v) for v in obj]
    return obj


class SafeJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return _json.dumps(
            _sanitize_nan(content),
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")


app = FastAPI(
    title="Agent Evaluation Platform Backend",
    version="1.0.0",
    default_response_class=SafeJSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks_router)
app.include_router(datasets_router)

@app.get("/")
def read_root():
    return {"message": "Agent Evaluation Platform Backend"}

