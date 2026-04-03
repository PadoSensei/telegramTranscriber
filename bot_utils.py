import re
import logging
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from config import ALLOWED_IDS

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
def parse_vault_request(text, user_map):
    """
    Identifies intent based on the specific user's category map.
    Returns: (bool: should_sync, str: path, str: tag_name, str: warning)
    """
    if not text:
        return False, None, None, None
    
    text_lower = text.lower()
    known_tags = list(user_map.keys()) # e.g., ['Star', 'Bloom', 'Source', 'Inbox']
    
    # 1. Check for hashtags that match our Category Map (Explicit Sync)
    # This allows Katie to just say "#star" to trigger a sync
    tags_in_text = re.findall(r"#(\w+)", text_lower)
    found_tag = None
    
    for t in tags_in_text:
        # Match case-insensitive against the keys in config.py
        match = next((k for k in known_tags if k.lower() == t), None)
        if match:
            found_tag = match
            break

    # 2. If no matching hashtag, check for "2nd brain" keywords (Implicit Sync)
    if not found_tag:
        # Look for "#2ndbrain", "2nd brain", or "second brain"
        sync_trigger = r"(#?2nd\s?brain|#?second\s?brain)"
        if not re.search(sync_trigger, text_lower):
            return False, None, None, None
        
        # If "2nd brain" is mentioned but no tag found, default to Inbox
        found_tag = "Inbox"

    # 3. Finalize the target path
    target_path = user_map.get(found_tag, "00_Inbox")
    
    # Optional warning if they used a tag not in their map
    warning = None
    if found_tag == "Inbox" and not any(tag.lower() in text_lower for tag in known_tags):
        warning = "💡 *Tip:* Use `#star` or `#bloom` to sort this automatically next time."

    return True, target_path, found_tag, warning

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