# config.py
import os
from dotenv import load_dotenv

# 載入 .env（若你用 .env 存放）
load_dotenv()

# 不給預設值，缺就讓啟動失敗，避免不小心用到錯的值
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN", "nQdkvAMzlHpv/qnKAIumRcljZS3AdXXSMYXkqnm7oYkHC+uLYUvRpUtsxsibuw6SY0bkTQZK2qBTA3pJ2vEwLLtDpOZ/XCDYBuTNuVkNN8POlb/XmUMqG0d4oyvNuXwFAm+sQM1HMPDWnT61JidGWwdB04t89/1O/w1cDnyilFU=")
CHANNEL_SECRET       = os.getenv("CHANNEL_SECRET", "30f565cf9ed35cddd703da9f8896b701")

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    raise RuntimeError(
        "Missing CHANNEL_ACCESS_TOKEN or CHANNEL_SECRET. "
        "Please set them in .env or environment variables."
    )

# 圖片儲存根目錄
BASE_DIR = os.path.join(os.path.dirname(__file__), "photos")
