FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# 运行时系统库：OpenCV / PaddlePaddle 依赖 + Tesseract（僧伽罗语/泰米尔语姓名第二引擎）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 \
    tesseract-ocr tesseract-ocr-sin tesseract-ocr-tam \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# 进程数量由环境变量 NIC_OCR_WORKERS 控制（默认 2）
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${NIC_OCR_WORKERS:-2}"]
