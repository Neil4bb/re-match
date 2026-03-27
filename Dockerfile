FROM python:3.11-slim
WORKDIR /app

# 安裝 cron 與 gcc
RUN apt-get update && apt-get install -y cron gcc && rm -rf /var/lib/apt/lists/*

# 安裝套件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製程式碼
COPY . .

# 設定排程

COPY crontab_file /etc/cron.d/game-crawler
RUN chmod 0644 /etc/cron.d/game-crawler && crontab /etc/cron.d/game-crawler
RUN touch /var/log/cron.log

# 同時啟動 cron 和 web 服務
# 1. 把環境變數導出到 /etc/environment，這是 Linux 讓所有服務（含 Cron）讀取變數的標準做法
# 2. 啟動 cron，然後啟動 gunicorn
CMD ["sh", "-c", "printenv > /etc/environment && service cron start && gunicorn -b 0.0.0.0:5000 --timeout 120 --workers 3 app:app"]