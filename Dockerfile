# 1. 使用 slim 保持基底乾淨
FROM python:3.11-slim

# 2. 設定工作目錄
WORKDIR /app

# 3. 安裝基礎系統工具 (保留必要的編譯工具以安裝 psycopg2 等套件)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 4. 安裝 Python 套件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 複製原始碼
COPY . .

# 6. 設定環境變數路徑
ENV PYTHONPATH=.

# 7. 預設啟動 Web 服務 (Worker 會在 docker-compose 中被覆蓋指令)
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]