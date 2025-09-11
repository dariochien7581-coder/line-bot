# ---- Base image ----
FROM python:3.11-slim

# 更小的映像 & 比較好除錯的 Python 行為
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 安裝依賴
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製程式碼
COPY . .

# Cloud Run 會注入 $PORT；用 gunicorn 綁到該埠
# app:app = 檔名 app.py 裡面的變數 app (Flask 物件)
CMD ["gunicorn", "-b", ":$PORT", "app:app"]
