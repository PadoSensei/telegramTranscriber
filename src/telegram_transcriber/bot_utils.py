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
    Ensures multi-tenant privacy and prevents unauthorized API usage.
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

# --- 2. INTENT & CATEGORY PARSING ---
def parse_vault_request(text, user_map=None):
    """
    Global Inbox-Only Routing.
    Every message processed by the bot is now automatically synced to the Inbox.
    Returns: (bool: should_sync, str: path, str: tag_name, str: warning)
    """
    if not text or len(text.strip()) < 2:
        return False, None, None, None
    
    # Global Policy: Always sync to Inbox, no hashtags or keywords required.
    return True, "00_Inbox", "Inbox", None

# --- 3. TEXT CLEANING ---
def get_clean_content(text):
    """
    Strips hashtags and sync keywords to keep the final vault notes clean.
    """
    if not text:
        return ""
    # Remove all hashtags (e.g., #star, #2ndbrain)
    text = re.sub(r"#\w+", "", text)
    # Remove "second brain" or "2nd brain" phrases (case-insensitive)
    text = re.sub(r"(?i)second\s?brain|2nd\s?brain", "", text)
    return text.strip()

# --- 4. TELEGRAM LIMIT HANDLER ---
async def send_large_message(context, chat_id, text, parse_mode="Markdown"):
    """
    Splits long Gemini responses to avoid Telegram's 4096 character limit.
    Includes a fallback to plain text if Markdown parsing fails.
    """
    if not text:
        return

    # Split into chunks of 3900 characters (buffer for safety)
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

# --- 5. MEDIA VALIDATION ---
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
        # Use the largest photo
        photo = message.photo[-1]
        file_id = photo.file_id
        file_size = photo.file_size
        media_type = "IMG"
        mime_type = "image/jpeg" # Telegram photos are always jpegs
    elif message.video:
        video = message.video
        file_id = video.file_id
        file_name = video.file_name
        mime_type = video.mime_type
        file_size = video.file_size
        media_type = "VID"
    else:
        return False, {}, "⚠️ Unsupported media type."

    # 1. Size Check
    size_mb = file_size / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        return False, {}, f"❌ Sorry, that file is too large ({size_mb:.1f}MB). We currently support files up to {MAX_FILE_SIZE_MB}MB."

    # 2. Determine Filenames
    now = datetime.now()
    timestamp_filename = now.strftime('%Y%m%d_%H%M%S')
    timestamp_metadata = now.strftime('%Y-%m-%d %H:%M:%S')

    # Extract extension
    ext = ""
    if file_name:
        _, ext = os.path.splitext(file_name)

    if not ext and mime_type:
        ext = mimetypes.guess_extension(mime_type) or ""
        # Fix for common types if guess fails
        if not ext:
            if mime_type == "image/jpeg": ext = ".jpg"
            elif mime_type == "video/mp4": ext = ".mp4"
            else: ext = ".bin"

    generated_name = f"{media_type}_{timestamp_filename}{ext}"
    original_name = file_name if file_name else generated_name

    # 3. Security Checks (Blacklist)
    ext_lower = ext.lower()
    if ext_lower in FILE_TYPE_BLACKLIST:
        return False, {}, f"⛔ For security reasons, files with the extension '{ext_lower}' are not supported. Your file was not saved."

    if mime_type in MIME_TYPE_BLACKLIST:
         return False, {}, f"⛔ For security reasons, files with the MIME type '{mime_type}' are not supported. Your file was not saved."

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