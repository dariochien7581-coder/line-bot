FROM python:3.11-slim

# 避免產生 pyc，加快 log
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 先安裝依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製所有程式碼
COPY . .

# 用 gunicorn 啟動 Flask app
# app:app = app.py 裡的變數 app
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8080", "app:app"]
