import os
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

from config import VAULT_CONFIGS
from bot_utils import restricted, parse_vault_request, send_large_message
from transcriber import Transcriber
from processor import TaskProcessor

# --- 1. SETUP ---
load_dotenv()
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
)
logger = logging.getLogger("2ndBrain")

# Initialize Services
transcriber = Transcriber(model_name="tiny") 
processor = TaskProcessor()

# Short-term memory to handle follow-up hashtags
# Structure: { user_id: "Last transcribed or sent text" }
USER_TRANSCRIPT_CACHE = {}

# --- 2. CORE LOGIC ---

@restricted
async def process_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Unified handler for Voice, Audio, and Text.
    Supports follow-up hashtags (#star) for previous voice notes.
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name
    user_cfg = VAULT_CONFIGS.get(user_id)

    # Detect input type
    is_audio = bool(update.message.voice or update.message.audio)
    incoming_text = update.message.text or update.message.caption or ""
    
    logger.info(f"[USER:{user_id}] Received {'AUDIO' if is_audio else 'TEXT'} from {user_name}")

    status_msg = await context.bot.send_message(chat_id=chat_id, text="⏳ Processing...")

    try:
        raw_content = ""

        # PHASE A: Content Acquisition
        if is_audio:
            logger.info(f"[USER:{user_id}] Downloading/Transcribing audio...")
            temp_path = await transcriber.get_voice_file(update, context)
            raw_content = await transcriber.transcribe(temp_path)
            
            # If user included a caption (text with the audio), append it
            if update.message.caption:
                raw_content = f"{raw_content} {update.message.caption}"
            
            # Save to memory in case they send a hashtag in the next message
            USER_TRANSCRIPT_CACHE[user_id] = raw_content
            logger.info(f"[USER:{user_id}] Transcription saved to cache.")

        else:
            # It's a text message. Check if it's a "Follow-up Hashtag"
            # Logic: If text starts with '#' and is only one word
            is_single_hashtag = incoming_text.startswith("#") and len(incoming_text.split()) == 1
            
            if is_single_hashtag and user_id in USER_TRANSCRIPT_CACHE:
                cached_text = USER_TRANSCRIPT_CACHE[user_id]
                raw_content = f"{cached_text} {incoming_text}"
                logger.info(f"[USER:{user_id}] FOLLOW-UP: Applying {incoming_text} to cached content.")
                await status_msg.edit_text(f"🔗 Linking `{incoming_text}` to your last voice note...")
            else:
                raw_content = incoming_text
                # Update cache with latest text as well
                USER_TRANSCRIPT_CACHE[user_id] = raw_content

        # Safety check for empty content
        if not raw_content or len(raw_content.strip()) < 2:
            await status_msg.edit_text("🤷 I didn't catch that. Message is too short.")
            return

        # PHASE B: Routing Logic
        should_sync, target_cat, target_proj, _ = parse_vault_request(raw_content, user_cfg["category_map"])

        # Fallback to Inbox if no hashtag was found
        if not should_sync:
            target_cat = "00_Inbox"
            target_proj = "00_Inbox"
            logger.info(f"[USER:{user_id}] ROUTING: No hashtag. Defaulting to Inbox.")
        else:
            logger.info(f"[USER:{user_id}] ROUTING: Mapped to {target_cat}")

        # PHASE C: AI Processing & Vault Sync
        logger.info(f"[USER:{user_id}] Starting AI Stack...")
        await status_msg.edit_text(f"🚀 Syncing to `{target_proj}`...")
        
        clean_text, analysis, success = await processor.run_sync_stack(
            user_id, target_cat, target_proj, raw_content, user_name
        )

        # PHASE D: Feedback
        if success:
            logger.info(f"[USER:{user_id}] SUCCESS: Vault Updated.")
            confirm_icon = "🌟" if "#star" in raw_content.lower() else "📥"
            
            # Send confirmation and transcript
            await context.bot.send_message(
                chat_id=chat_id, 
                text=f"{confirm_icon} *Obsidian Updated!*\nSaved to: `{target_proj}`",
                parse_mode="Markdown"
            )
            await send_large_message(context, chat_id, f"📝 *Content Preview:*\n\n{clean_text}")
            await status_msg.delete()
        else:
            await status_msg.edit_text("⚠️ Sync finished with errors. Check GitHub logs.")
            logger.error(f"[USER:{user_id}] FAILURE: Sync finished with errors.")

    except Exception as e:
        logger.error(f"[USER:{user_id}] ERROR: {str(e)}", exc_info=True)
        await status_msg.edit_text(f"❌ System Error: {str(e)}")

# --- 3. ENTRY POINT ---
if __name__ == '__main__':
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not found in environment!")

    # Request config with increased timeouts for large voice files
    request_config = HTTPXRequest(connect_timeout=30.0, read_timeout=60.0)
    app = ApplicationBuilder().token(token).request(request_config).build()

    # Route Voice, Audio, and Text to the processor
    app.add_handler(MessageHandler((filters.VOICE | filters.AUDIO), process_entry))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), process_entry))
    
    logger.info("🧠 2ndBrain Orchestrator: Multi-Tenant Mode Online")
    app.run_polling(drop_pending_updates=True)