import os
import re
import time
import uuid
import datetime
import mimetypes
from typing import Optional

from flask import Flask
app = Flask(__name__)

from flask import Flask, request, abort
from google.cloud import storage

# v2：收訊息/抓內容/回覆
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import (
    MessageEvent,
    ImageMessage,
    FileMessage,
    TextMessage,
    StickerMessage,
    TextSendMessage,
)

# v3：查群組名稱（群組摘要）
from linebot.v3.messaging import (
    Configuration as V3Configuration,
    ApiClient as V3ApiClient,
    MessagingApi as V3MessagingApi,
)

from config import CHANNEL_ACCESS_TOKEN, CHANNEL_SECRET, BASE_DIR

# -------------------- 基本設定 --------------------
app = Flask(__name__)

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# v3：查群組名稱
_v3_cfg = V3Configuration(access_token=CHANNEL_ACCESS_TOKEN)
_v3_client = V3ApiClient(_v3_cfg)
_v3_msg_api = V3MessagingApi(_v3_client)

os.makedirs(BASE_DIR, exist_ok=True)

# GCS 設定
GCS_BUCKET = os.getenv("GCS_BUCKET")
_gcs_client: Optional[storage.Client] = None

def _get_gcs_client() -> storage.Client:
    global _gcs_client
    if _gcs_client is None:
        _gcs_client = storage.Client()
    return _gcs_client

# -------------------- 健康檢查 --------------------
@app.get("/health")
def health():
    return "OK", 200

# -------------------- Webhook 入口 --------------------
@app.post("/callback")
def callback():
    signature = request.headers.get("X-Line-Signature")
    if not signature:
        abort(400)

    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        print(f"[ERR] handler exception: {e}", flush=True)
    return "OK"

# -------------------- 群組名稱快取 --------------------
_SAFE_PAT = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
SAFE_NAME_MAXLEN = 60

def sanitize_folder_name(name: str) -> str:
    if not name:
        return "unknown"
    name = _SAFE_PAT.sub("_", name).strip().strip(".")
    if not name:
        name = "unknown"
    if len(name) > SAFE_NAME_MAXLEN:
        name = name[:SAFE_NAME_MAXLEN].rstrip()
    return name

_GROUP_NAME_CACHE: dict[str, tuple[str, float]] = {}
GROUP_NAME_TTL_SEC = 6 * 60 * 60

def get_group_name_with_cache(group_id: str) -> Optional[str]:
    now = time.time()
    cached = _GROUP_NAME_CACHE.get(group_id)
    if cached and cached[1] > now:
        return cached[0]
    try:
        summary = _v3_msg_api.get_group_summary(group_id)
        raw = getattr(summary, "group_name", None) or getattr(summary, "groupName", None)
        name = sanitize_folder_name(raw or "")
        _GROUP_NAME_CACHE[group_id] = (name, now + GROUP_NAME_TTL_SEC)
        return name
    except Exception as e:
        print(f"[WARN] get_group_summary failed for {group_id}: {e}", flush=True)
        return None

# -------------------- 儲存路徑 --------------------
def _source_folder(event) -> str:
    st = event.source.type
    if st == "group":
        gid = event.source.group_id
        gname = get_group_name_with_cache(gid)
        return gname if gname else f"group_{gid}"
    elif st == "room":
        return f"room_{event.source.room_id}"
    else:
        return f"user_{event.source.user_id}"

def _album_dir(image_set) -> str:
    if image_set and getattr(image_set, "id", None):
        return f"album_{image_set.id}"
    return ""

def _build_dir(event, album_subdir: str) -> str:
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    who = _source_folder(event)
    parts = [BASE_DIR, date_str, who]
    if album_subdir:
        parts.append(album_subdir)
    dir_path = os.path.join(*parts)
    os.makedirs(dir_path, exist_ok=True)
    return dir_path

def _save_bytes(dir_path: str, filename: str, data: bytes) -> str:
    file_path = os.path.join(dir_path, filename)
    with open(file_path, "wb") as f:
        f.write(data)
    print(f"✅ 已存圖: {file_path}", flush=True)
    return file_path

def _to_gcs_rel_path(local_file_path: str) -> str:
    base = os.path.abspath(BASE_DIR)
    abs_path = os.path.abspath(local_file_path)
    rel = os.path.relpath(abs_path, base)
    return rel.replace("\\", "/")

# -------------------- GCS 上傳工具 --------------------
def upload_to_gcs(local_path: str, rel_path_in_bucket: str) -> str:
    if not GCS_BUCKET:
        raise RuntimeError("GCS_BUCKET is not set")
    client = _get_gcs_client()
    bucket = client.bucket(GCS_BUCKET)
    blob = bucket.blob(rel_path_in_bucket)
    blob.upload_from_filename(local_path)
    return f"gs://{GCS_BUCKET}/{rel_path_in_bucket}"

def gcs_signed_url(rel_path_in_bucket: str, ttl_seconds: int = 3600) -> str:
    client = _get_gcs_client()
    bucket = client.bucket(GCS_BUCKET)
    blob = bucket.blob(rel_path_in_bucket)
    url = blob.generate_signed_url(
        expiration=datetime.timedelta(seconds=ttl_seconds),
        method="GET",
    )
    return url

def after_save_hook(file_path: str) -> Optional[str]:
    try:
        if not GCS_BUCKET:
            return None
        rel = _to_gcs_rel_path(file_path)
        gs_uri = upload_to_gcs(file_path, rel)
        url = gcs_signed_url(rel, ttl_seconds=3600)
        print(f"☁️ Uploaded to {gs_uri}", flush=True)
        print(f"🔗 Signed URL (1h): {url}", flush=True)
        return url
    except Exception as e:
        print(f"[WARN] after_save_hook failed: {e}", flush=True)
        return None

# -------------------- 圖片訊息 --------------------
@handler.add(MessageEvent, message=ImageMessage)
def on_image(event: MessageEvent):
    cp = getattr(event.message, "content_provider", None)
    if cp and getattr(cp, "type", "") != "line":
        print("[INFO] non-line image, skip", flush=True)
        return

    try:
        content = line_bot_api.get_message_content(event.message.id)
        img_bytes = content.content
        ctype = getattr(content, "content_type", None)
        ext = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
        }.get(ctype, ".jpg")
    except LineBotApiError as e:
        print(f"[ERR] get_message_content(Image) failed: {e}", flush=True)
        return

    iset = getattr(event.message, "image_set", None)
    album_subdir = _album_dir(iset)
    dir_path = _build_dir(event, album_subdir)

    if iset and getattr(iset, "index", None) and getattr(iset, "total", None):
        index = int(iset.index)
        total = int(iset.total)
        filename = f"{index:03d}{ext}"
        is_album = True
    else:
        ts = datetime.datetime.now().strftime("%H%M%S_%f")
        filename = f"{ts}_{uuid.uuid4().hex[:6]}{ext}"
        is_album = False
        total = 1
        index = 1

    file_path = _save_bytes(dir_path, filename, img_bytes)
    signed_url = after_save_hook(file_path)

    reply_text = "✅ 已存檔"
    if signed_url:
        reply_text += f"\n{signed_url}"

    try:
        if is_album:
            if index == total:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"{reply_text}（相簿/連拍，共 {total} 張）")
                )
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
    except Exception as e:
        print(f"[WARN] reply skipped: {e}", flush=True)

# -------------------- 檔案訊息（僅圖片） --------------------
@handler.add(MessageEvent, message=FileMessage)
def on_file(event: MessageEvent):
    name = event.message.file_name
    mime = event.message.mime_type or mimetypes.guess_type(name)[0]
    if not (mime and mime.startswith("image/")):
        print(f"[SKIP] 非圖片檔案 {name} ({mime})", flush=True)
        return

    try:
        content = line_bot_api.get_message_content(event.message.id)
        img_bytes = content.content
        ext = mimetypes.guess_extension(mime) or ".jpg"
    except LineBotApiError as e:
        print(f"[ERR] get_message_content(File) failed: {e}", flush=True)
        return

    dir_path = _build_dir(event, album_subdir="")
    filename = sanitize_folder_name(os.path.splitext(name)[0]) + ext
    file_path = _save_bytes(dir_path, filename, img_bytes)
    signed_url = after_save_hook(file_path)

    reply_text = "✅ 已存檔"
    if signed_url:
        reply_text += f"\n{signed_url}"

    try:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
    except Exception as e:
        print(f"[WARN] reply skipped: {e}", flush=True)

# -------------------- 文字/貼圖：不回覆 --------------------
@handler.add(MessageEvent, message=TextMessage)
def on_text(event: MessageEvent):
    print("[INFO] text received (silenced).", flush=True)

@handler.add(MessageEvent, message=StickerMessage)
def on_sticker(event: MessageEvent):
    print("[INFO] sticker received (silenced).", flush=True)

# =============== 取圖 API / 圖庫頁面（方式 C） ===============
from flask import jsonify, render_template

API_KEY = os.getenv("API_KEY", "")  # 在 Cloud Run 設定

def _auth_ok(req) -> bool:
    # 允許用 Header：X-API-Key 或 query：?key=
    k = req.headers.get("X-API-Key") or req.args.get("key")
    return bool(API_KEY) and (k == API_KEY)

def _list_prefixes_and_blobs(prefix: str):
    """回傳 (資料夾清單, 檔案清單)。使用 GCS delimiter 模擬資料夾。"""
    client = _get_gcs_client()
    bucket = client.bucket(GCS_BUCKET)

    iterator = client.list_blobs(
        GCS_BUCKET,
        prefix=prefix if prefix.endswith("/") else prefix + "/",
        delimiter="/",
    )
    folders = []
    files = []

    # 需要先消耗 iterator 才會有 prefixes
    for b in iterator:
        files.append(b)

    folders = list(iterator.prefixes)  # e.g. ['base/2025-09-11/groupA/', ...]

    return folders, files

@app.get("/api/groups")
def api_groups():
    if not _auth_ok(request):
        return jsonify({"error": "unauthorized"}), 401

    date = request.args.get("date")  # YYYY-MM-DD
    if not date:
        return jsonify({"error": "missing 'date' (YYYY-MM-DD)"}), 400
    if not GCS_BUCKET:
        return jsonify({"error": "GCS_BUCKET not configured"}), 500

    # 結構: BASE_DIR/<date>/<group>/...
    date_prefix = f"{date}"   # 2025-09-12
    folders, _ = _list_prefixes_and_blobs(date_prefix)

    groups = []
    for p in folders:
        # p 例： 'line-bot/2025-09-11/數學群組/'
        tail = p.rstrip("/").split("/")  # ['line-bot','2025-09-11','數學群組']
        if len(tail) >= 3:
            groups.append(tail[-1])

    groups = sorted(set(groups))
    return jsonify({"date": date, "groups": groups})

@app.get("/api/files")
def api_files():
    if not _auth_ok(request):
        return jsonify({"error": "unauthorized"}), 401

    date = request.args.get("date")
    group = request.args.get("group")
    if not date or not group:
        return jsonify({"error": "missing 'date' or 'group'"}), 400
    if not GCS_BUCKET:
        return jsonify({"error": "GCS_BUCKET not configured"}), 500

    # 支援是否包含相簿子資料夾（若你有 album_xxx）
    album = request.args.get("album", "")
    base_prefix = f"{BASE_DIR}/{date}/{group}"
    prefix = f"{base_prefix}/{album}" if album else base_prefix

    _, files = _list_prefixes_and_blobs(prefix)

    items = []
    for b in files:
        # b.name e.g. 'line-bot/2025-09-11/數學群組/001.jpg'
        rel = b.name  # 就當作 bucket 內相對路徑
        url = gcs_signed_url(rel, ttl_seconds=86400)  # 24h
        items.append({
            "name": os.path.basename(rel),
            "path": rel,
            "url": url,
            "gs_uri": f"gs://{GCS_BUCKET}/{rel}",
            "size": b.size,
            "updated": b.updated.isoformat() if getattr(b, "updated", None) else None,
        })

    # 依檔名排序（有 001.jpg、002.jpg 會很順）
    items.sort(key=lambda x: x["name"])
    return jsonify({"date": date, "group": group, "count": len(items), "items": items})

# 圖庫頁面
@app.get("/gallery")
def gallery():
    # 用前端輸入 API Key，後端不擋
    return render_template("gallery.html", bucket=GCS_BUCKET, base_dir=BASE_DIR)

# -------------------- 入口 --------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
