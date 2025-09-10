import os
from datetime import datetime
from typing import Union
from google.cloud import storage

GCS_BUCKET = os.getenv("GCS_BUCKET")
_storage_client = storage.Client()

def today_dir() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def save_bytes(content: Union[bytes, bytearray], rel_path: str) -> str:
    bucket = _storage_client.bucket(GCS_BUCKET)
    blob = bucket.blob(rel_path)
    blob.upload_from_string(bytes(content))
    # 回傳公開可用的 URL（需要 bucket 設定允許 public read）
    return f"https://storage.googleapis.com/{GCS_BUCKET}/{rel_path}"
