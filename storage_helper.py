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
    return f"gs://{GCS_BUCKET}/{rel_path}"
