import re
import logging
import os
import mimetypes
from datetime import datetime
from functools import wraps
from telegram import Update, Message
from telegram.ext import ContextTypes
from .config import ALLOWED_IDS, MAX_FILE_SIZE_MB, FILE_TYPE_BLACKLIST, MIME_TYPE_BLACKLIST

logger = logging.getLogger(__name__)

# --- 1. SECURITY DECORATOR ---
def restricted(func):
    """
    Decorator to only allow authorized IDs defined in config.py.
    """
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ALLOWED_IDS:
            logger.warning(f"🚫 Unauthorized access attempt by ID: {user_id}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text="❌ *Access Denied.* Your ID is not on the whitelist."
            )
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- 2. TEXT CLEANING ---
def get_clean_content(text):
    """
    Strips hashtags and sync keywords to keep the final vault notes clean.
    """
    if not text:
        return ""
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"(?i)second\s?brain|2nd\s?brain", "", text)
    return text.strip()

# --- 3. TELEGRAM LIMIT HANDLER ---
async def send_large_message(context, chat_id, text, parse_mode="Markdown"):
    """
    Splits long Gemini responses to avoid Telegram's 4096 character limit.
    """
    if not text:
        return

    parts = [text[i:i+3900] for i in range(0, len(text), 3900)]
    
    for part in parts:
        try:
            await context.bot.send_message(
                chat_id=chat_id, 
                text=part, 
                parse_mode=parse_mode,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Markdown parsing failed, sending as plain text: {e}")
            await context.bot.send_message(
                chat_id=chat_id, 
                text=part, 
                parse_mode=None
            )

# --- 4. MEDIA VALIDATION ---
def validate_media_file(message: Message):
    """
    Extracts file metadata and performs security checks.
    Returns (is_valid, file_info, error_message)
    """
    file_id = None
    file_name = None
    mime_type = None
    file_size = 0
    media_type = "FILE"

    if message.document:
        doc = message.document
        file_id = doc.file_id
        file_name = doc.file_name
        mime_type = doc.mime_type
        file_size = doc.file_size
        media_type = "DOC"
    elif message.photo:
        photo = message.photo[-1]
        file_id = photo.file_id
        file_size = photo.file_size
        media_type = "IMG"
        mime_type = "image/jpeg"
    elif message.video:
        video = message.video
        file_id = video.file_id
        file_name = video.file_name
        mime_type = video.mime_type
        file_size = video.file_size
        media_type = "VID"
    else:
        return False, {}, "⚠️ Unsupported media type."

    size_mb = file_size / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        return False, {}, f"❌ Sorry, that file is too large ({size_mb:.1f}MB). Max: {MAX_FILE_SIZE_MB}MB."

    now = datetime.now()
    timestamp_filename = now.strftime('%Y%m%d_%H%M%S')
    timestamp_metadata = now.strftime('%Y-%m-%d %H:%M:%S')

    ext = ""
    if file_name:
        _, ext = os.path.splitext(file_name)

    if not ext and mime_type:
        ext = mimetypes.guess_extension(mime_type) or ""
        if not ext:
            if mime_type == "image/jpeg": ext = ".jpg"
            elif mime_type == "video/mp4": ext = ".mp4"
            else: ext = ".bin"

    generated_name = f"{media_type}_{timestamp_filename}{ext}"
    original_name = file_name if file_name else generated_name

    ext_lower = ext.lower()
    if ext_lower in FILE_TYPE_BLACKLIST:
        return False, {}, f"⛔ Unsupported extension: '{ext_lower}'."

    if mime_type in MIME_TYPE_BLACKLIST:
         return False, {}, f"⛔ Unsupported MIME type: '{mime_type}'."

    file_info = {
        "file_id": file_id,
        "file_name": generated_name,
        "original_name": original_name,
        "mime_type": mime_type,
        "media_type": media_type,
        "file_size": file_size,
        "size_mb": size_mb,
        "timestamp": timestamp_metadata
    }

    return True, file_info, None
