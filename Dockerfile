FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip \
  && python -m pip install -r requirements.txt

COPY agent ./agent
COPY docs ./docs
COPY evaluation ./evaluation
COPY tests ./tests

WORKDIR /app/agent

EXPOSE 8000

CMD ["sh", "-c", "uvicorn web_app:app --host 0.0.0.0 --port ${PORT:-8000}"]

