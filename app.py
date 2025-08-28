# app.py
# -*- coding: utf-8 -*-
import os, sys, hashlib, datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import (
    MessageEvent,
    ImageMessage,
    SourceUser, SourceGroup, SourceRoom,
    TextSendMessage,
)

from config import CHANNEL_ACCESS_TOKEN, CHANNEL_SECRET, BASE_DIR

# ------------------------------
# Flask & LINE 初始化
# ------------------------------
app = Flask(__name__)
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# 健康檢查（給 ngrok 或監控用）
@app.get("/health")
def health():
    return "OK", 200

# 確保根資料夾存在
os.makedirs(BASE_DIR, exist_ok=True)

# 請求簡易日誌
@app.before_request
def _log_req():
    print(f"[REQ] {request.method} {request.path}", file=sys.stdout, flush=True)

# Webhook 入口
@app.post("/callback")
def callback():
    signature = request.headers.get("X-Line-Signature")
    if not signature:
        print("[ERR] missing X-Line-Signature", file=sys.stdout, flush=True)
        abort(400)

    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("[ERR] invalid signature", file=sys.stdout, flush=True)
        abort(400)
    except Exception as e:
        print(f"[ERR] handler exception: {e}", file=sys.stdout, flush=True)
        # 回 200 告知 LINE 我們已收下，避免重送
        return "OK"
    return "OK"

# ------------------------------
# 工具：安全回覆（避免 reply token 失效）
# ------------------------------
def reply_safely(event, message):
    """優先 reply，失敗再依來源改用 push（群組/多人/個人）"""
    try:
        line_bot_api.reply_message(event.reply_token, message)
        return
    except LineBotApiError as e:
        print(f"[WARN] reply failed: {e}", file=sys.stdout, flush=True)

    try:
        if isinstance(event.source, SourceGroup):
            line_bot_api.push_message(event.source.group_id, message)
        elif isinstance(event.source, SourceRoom):
            line_bot_api.push_message(event.source.room_id, message)
        elif isinstance(event.source, SourceUser):
            line_bot_api.push_message(event.source.user_id, message)
    except LineBotApiError as e:
        print(f"[ERR] push failed: {e}", file=sys.stdout, flush=True)

# ------------------------------
# 只處理「圖片」訊息：存檔 + 回覆「已存檔」
# （文字/貼圖/其他一律不回，符合“偵測到圖片才說話”）
# ------------------------------
@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    # 取得圖片位元組
    try:
        content = line_bot_api.get_message_content(event.message.id)
        img_data = content.content
    except LineBotApiError as e:
        print(f"[ERR] get_message_content error: {e}", file=sys.stdout, flush=True)
        return

    # 來源資訊（用於分門別類存檔）
    # user_XXX / group_XXX / room_XXX
    subdir = "unknown"
    if isinstance(event.source, SourceUser):
        subdir = f"user_{event.source.user_id}"
    elif isinstance(event.source, SourceGroup):
        subdir = f"group_{event.source.group_id}"
    elif isinstance(event.source, SourceRoom):
        subdir = f"room_{event.source.room_id}"

    # 以日期建立資料夾
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    save_dir = os.path.join(BASE_DIR, date_str, subdir)
    os.makedirs(save_dir, exist_ok=True)

    # 檔名：時間戳 + SHA1 前 8 碼（即使重複也會重新存檔，不覆蓋）
    sha1 = hashlib.sha1(img_data).hexdigest()[:8]
    ts = datetime.datetime.now().strftime("%H%M%S_%f")
    filename = f"{ts}_{sha1}.jpg"
    file_path = os.path.join(save_dir, filename)

    try:
        with open(file_path, "wb") as f:
            f.write(img_data)
        print(f"✅ 已存圖: {file_path}", file=sys.stdout, flush=True)
    except Exception as e:
        print(f"[ERR] save file failed: {e}", file=sys.stdout, flush=True)
        return

    # 只在收到圖片時回一句話（個人/群組/多人都行）
    reply_safely(event, TextSendMessage(text="✅ 已存檔"))

# ------------------------------
# 其他訊息（文字/貼圖/檔案…）不回覆
# 若未來要加邏輯，可在這裡擴充
# ------------------------------
# 例：什麼都不做 -> 只要不註冊 TextMessage/StickerMessage handler 就不會回

# ------------------------------
# 啟動
# ------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))   # Railway 會塞 PORT
    app.run(host="0.0.0.0", port=port)
