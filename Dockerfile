FROM python:3.11-slim

# Playwright + ChromaDB + torch 의존 시스템 라이브러리
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl git libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU 전용 torch 먼저 설치 (CUDA 빌드 대비 ~2GB 절약)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# 나머지 의존성
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright Chromium 설치 (보험다모아 실시간 스크래핑용)
RUN playwright install --with-deps chromium

# 한국어 임베딩 모델을 빌드 시 내려받아 이미지에 포함
# → 컨테이너 첫 실행 시 2~5분 대기 없이 즉시 시작
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('jhgan/ko-sroberta-multitask')"

COPY . .

# ChromaDB 영구 저장 경로 (Railway Volume은 이 경로에 마운트)
VOLUME ["/app/chroma_db"]

EXPOSE 5000

CMD ["python", "web_app.py"]
