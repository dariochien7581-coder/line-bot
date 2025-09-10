# 使用 Python 官方輕量版本
FROM python:3.10-slim

# 設定容器內的工作目錄
WORKDIR /app

# 複製需求套件並安裝
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製專案所有檔案進容器
COPY . .

# Cloud Run 預設會提供環境變數 PORT
ENV PORT=8000

# 啟動 Flask 伺服器
CMD ["python", "app.py"]
