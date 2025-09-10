import os
from dotenv import load_dotenv

load_dotenv()

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")
GCS_BUCKET = os.getenv("GCS_BUCKET")  # Cloud Storage bucket 名稱
BASE_DIR = os.path.join(os.path.dirname(__file__), "storage")
os.makedirs(BASE_DIR, exist_ok=True)

def validate_config():
    miss = []
    if not CHANNEL_ACCESS_TOKEN:
        miss.append("CHANNEL_ACCESS_TOKEN")
    if not CHANNEL_SECRET:
        miss.append("CHANNEL_SECRET")
    if not GCS_BUCKET:
        miss.append("GCS_BUCKET")
    return miss
