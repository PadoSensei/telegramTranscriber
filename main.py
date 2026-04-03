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
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Services
transcriber = Transcriber(model_name="tiny") 
processor = TaskProcessor()

# --- 2. CORE LOGIC ---

@restricted
async def process_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Unified handler for Voice, Audio, and Text.
    ALWAYS pushes to Obsidian. Routes based on spoken hashtags.
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name
    user_cfg = VAULT_CONFIGS.get(user_id)

    status_msg = await context.bot.send_message(chat_id=chat_id, text="⏳ Processing...")

    try:
        # A. Get Content (Transcribe if audio, else take text)
        if update.message.voice or update.message.audio:
            temp_path = await transcriber.get_voice_file(update, context)
            raw_content = await transcriber.transcribe(temp_path)
        else:
            raw_content = update.message.text

        if not raw_content or len(raw_content.strip()) < 2:
            await status_msg.edit_text("🤷 I didn't catch that. Audio might be too short.")
            return

        # B. Routing Logic
        # parse_vault_request checks for hashtags like #star in the transcript
        should_sync, target_cat, target_proj, _ = parse_vault_request(raw_content, user_cfg["category_map"])

        # SENIOR MOVE: If no hashtag was found, we FORCE a sync to the Inbox anyway
        if not should_sync:
            target_cat = "00_Inbox"
            target_proj = "00_Inbox"
            logger.info(f"No hashtag found. Defaulting to Inbox for {user_name}")

        # C. Execute Processing & Parallel Pushing
        await status_msg.edit_text(f"🚀 Syncing to `{target_proj}`...")
        
        clean_text, analysis, success = await processor.run_sync_stack(
            user_id, target_cat, target_proj, raw_content, user_name
        )

        # D. Feedback Loop
        if success:
            # We send a fresh message for the confirmation so it doesn't get lost
            confirm_icon = "🌟" if "#star" in raw_content.lower() else "📥"
            await context.bot.send_message(
                chat_id=chat_id, 
                text=f"{confirm_icon} *Obsidian Updated!*\nSaved to: `{target_proj}`"
            )
            # Send back the transcript so the user can see what the AI processed
            await send_large_message(context, chat_id, f"📝 *Transcript Preview:*\n\n{clean_text}")
            await status_msg.delete()
        else:
            await status_msg.edit_text("⚠️ Sync finished with errors. Check GitHub/Google Docs.")

    except Exception as e:
        logger.error(f"Error in process_entry: {e}")
        await status_msg.edit_text(f"❌ System Error: {str(e)}")

# --- 3. ENTRY POINT ---
if __name__ == '__main__':
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not found in environment!")

    # Increased timeouts for larger voice note processing
    request_config = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    app = ApplicationBuilder().token(token).request(request_config).build()

    # We route all inputs (Voice, Audio, Text) through the same logic
    app.add_handler(MessageHandler((filters.VOICE | filters.AUDIO), process_entry))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), process_entry))
    
    logger.info("🧠 Katie's 2nd Brain: Orchestrator Mode Online")
    app.run_polling(drop_pending_updates=True)