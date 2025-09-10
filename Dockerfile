# 使用輕量 Python 映像
FROM python:3.12-slim

# 讓 Python 輸出不緩衝，方便看日誌
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先裝依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製專案程式
COPY . .

# Cloud Run 會把對外埠號放在 $PORT
ENV PORT=8080

# 使用 gunicorn 對外服務（app.py 內的 Flask 物件名為 app）
CMD exec gunicorn --bind :$PORT --workers 2 --threads 4 --timeout 0 app:app
