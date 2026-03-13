# 1. 依然使用 slim 保持基底乾淨
FROM python:3.14-slim

# 2. 設定工作目錄
WORKDIR /app

# 3. 安裝基礎系統工具
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 4. 安裝 Python 套件 (包含 playwright)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 【關鍵】安裝 Playwright 瀏覽器及其所需的系統依賴庫
# --with-deps 會自動幫你在 slim 上補齊所有漏掉的 Linux 函式庫
RUN playwright install chromium --with-deps

# 6. 複製原始碼
COPY . .

# 7. 啟動指令
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]