import os
import logging
from dotenv import load_dotenv

# Telegram Imports
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

# Project Modules (The Service Layer)
from config import ALLOWED_IDS, VAULT_CONFIGS
from bot_utils import restricted, parse_vault_request, send_large_message
from transcriber import Transcriber
from processor import TaskProcessor

# --- 1. SETUP ---
load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Services
# We load the heavy Whisper model once here
transcriber = Transcriber(model_name="tiny") 
processor = TaskProcessor()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# --- 2. CORE HANDLERS ---

@restricted
async def process_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles Voice and Audio notes: Download -> Transcribe -> AI -> Sync."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name

    status_msg = await context.bot.send_message(chat_id=chat_id, text="⏳ Processing audio...")

    try:
        # A. Audio Lifecycle (Transcriber)
        temp_path = await transcriber.get_voice_file(update, context)
        if not temp_path:
            return
            
        raw_transcript = await transcriber.transcribe(temp_path)
        if not raw_transcript:
            await status_msg.edit_text("🤷 I couldn't hear any words in that audio.")
            return

        # B. Intent Parsing (Bot Utils)
        user_cfg = VAULT_CONFIGS.get(user_id)
        should_sync, cat, proj, warning = parse_vault_request(raw_transcript, user_cfg["category_map"])

        # C. Processing & Persistence (Processor)
        if should_sync:
            await status_msg.edit_text(f"🚀 Syncing to `{proj}`...")
            clean, analysis, success = await processor.run_sync_stack(
                user_id, cat, proj, raw_transcript, user_name
            )
            
            if success:
                await context.bot.send_message(chat_id=chat_id, text=f"✅ *Vault & NotebookLM Updated* in `{proj}`!")
            else:
                await context.bot.send_message(chat_id=chat_id, text="⚠️ Partial failure: Check GitHub/Google Docs.")
        else:
            # Fallback for notes with no hashtags (Inbox)
            await status_msg.edit_text("📝 Note captured to Inbox (No sync requested).")
            # You could add a call to processor here too if you want AI cleaning for Inbox notes

    except Exception as e:
        logger.error(f"Error in process_media: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"❌ System Error: {e}")
    finally:
        await status_msg.delete()

@restricted
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles raw text notes similarly to audio."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    text = update.message.text
    user_cfg = VAULT_CONFIGS.get(user_id)

    should_sync, cat, proj, _ = parse_vault_request(text, user_cfg["category_map"])

    if should_sync:
        clean, analysis, success = await processor.run_sync_stack(
            user_id, cat, proj, text, update.effective_user.first_name
        )
        if success:
            await context.bot.send_message(chat_id=chat_id, text=f"✅ *Text Note Synced* to `{proj}`!")
    else:
        # Default text handling logic
        await context.bot.send_message(chat_id=chat_id, text="📝 Note saved to Inbox.")

# --- 3. ENTRY POINT ---
if __name__ == '__main__':
    # Build with increased timeouts for large voice files
    request_config = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(request_config).build()

    # Register Handlers
    app.add_handler(MessageHandler((filters.VOICE | filters.AUDIO), process_media))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    
    print(f"🚀 Katie's 2nd Brain Online (Orchestrator Mode)")
    app.run_polling(drop_pending_updates=True)