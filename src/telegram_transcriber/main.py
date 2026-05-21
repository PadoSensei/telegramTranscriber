import os
import sys
import logging
import asyncio
import httpx
from datetime import datetime
from dotenv import load_dotenv

from telegram import Update
from telegram.error import NetworkError
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

from .config import (
    VAULT_CONFIGS, get_user_config,
    HTTP_CONNECT_TIMEOUT, HTTP_READ_TIMEOUT, HTTP_WRITE_TIMEOUT,
    MEDIA_GROUP_DEBOUNCE_TIME
)
from .bot_utils import restricted, send_large_message, validate_media_file
from .exceptions import MediaIngestionError, TelegramDownloadError, GitPersistenceError
from .transcriber import Transcriber, HallucinationError
from .factory import ManagerFactory

# --- 1. SETUP ---
load_dotenv()
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
)
logger = logging.getLogger("KnowledgeIngestionEngine")

def system_check():
    """
    Validates infrastructure, environment variables, and user configurations at boot.
    """
    logger.info("🔍 Running System Boot Diagnostics...")

    # 1. Infrastructure Checks
    critical_env_vars = ["TELEGRAM_BOT_TOKEN", "GEMINI_API_KEY"]
    missing_vars = [var for var in critical_env_vars if not os.getenv(var)]
    if missing_vars:
        logger.critical(f"❌ Missing critical environment variables: {', '.join(missing_vars)}")
        sys.exit(1)

    # 2. Dependency Checks (Smoke Test)
    try:
        import fasteners
        import pydantic
        import whisper
        logger.info("✅ Core dependencies verified (fasteners, pydantic, whisper)")
    except ImportError as e:
        logger.critical(f"❌ Dependency check failed: {e}")
        sys.exit(1)

    # 3. User Schema Validation
    try:
        for user_id, cfg in VAULT_CONFIGS.items():
            get_user_config(user_id)
            logger.info(f"✅ Configuration for user {cfg.get('name')} (ID: {user_id}) is valid.")
    except Exception as e:
        logger.critical(f"❌ User Schema Validation failed: {e}")
        sys.exit(1)

    logger.info("🚀 Knowledge Ingestion Engine is ready to boot.")

# Initialize Services
transcriber = Transcriber(model_name="base")
processor = ManagerFactory.get_processor()

# In-memory storage for media group debouncing
_media_groups_processing = {}

# --- 2. ERROR HANDLING ---

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and handle network-related blips."""
    logger.error("Exception while handling an update:", exc_info=context.error)

    if isinstance(context.error, (NetworkError, httpx.ReadError, httpx.WriteError, httpx.ConnectError)):
        logger.warning(f"Network-related error detected: {type(context.error).__name__}. Loop recovery should handle this.")
        return

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ An internal error occurred. Admin has been notified."
            )
        except Exception as e:
            logger.error(f"Failed to send error notification to user: {e}")

# --- 3. CORE LOGIC ---

@restricted
async def process_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Unified handler for Voice, Audio, and Text.
    Directly routes all captures to the Inbox.
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name
    try:
        user_cfg_model = get_user_config(user_id)
    except ValueError as e:
        logger.error(f"Config error for user {user_id}: {e}")
        await context.bot.send_message(chat_id=chat_id, text="❌ Configuration Error. Please contact admin.")
        return

    # Detect input type
    is_audio = bool(update.message.voice or update.message.audio)
    input_type = "voice" if is_audio else "text"
    incoming_text = update.message.text or update.message.caption or ""
    
    logger.info(f"[USER:{user_id}] Received {input_type.upper()} from {user_name}")

    status_msg = await context.bot.send_message(chat_id=chat_id, text="⏳ Processing...")

    try:
        raw_content = ""

        # PHASE A: Content Acquisition
        if is_audio:
            logger.info(f"[USER:{user_id}] Downloading/Transcribing audio...")
            try:
                temp_path = await transcriber.get_voice_file(update, context)
                transcription_result = await transcriber.transcribe(temp_path)
                raw_content = transcription_result.get("text", "")
            except HallucinationError:
                await status_msg.edit_text("I caught some background noise, but nothing clear enough to save.")
                return
            
            # If user included a caption, append it
            if update.message.caption:
                raw_content = f"{raw_content} {update.message.caption}"
        else:
            raw_content = incoming_text

        # Safety check for empty content
        if not raw_content or len(raw_content.strip()) < 2:
            await status_msg.edit_text("🤷 I didn't catch that. Message is too short.")
            return

        # PHASE B: AI Processing & Vault Sync (Direct to Inbox)
        logger.info(f"[USER:{user_id}] Starting AI Stack...")
        await status_msg.edit_text(f"🚀 Syncing to `00_Inbox`...")
        
        clean_text, analysis, git_success = await processor.run_sync_stack(
            user_cfg_model, raw_content, input_type=input_type
        )

        # PHASE C: Feedback
        if git_success:
            logger.info(f"[USER:{user_id}] SYNC SUCCESS: GitHub updated.")
            await context.bot.send_message(
                chat_id=chat_id, 
                text="🌟 *Obsidian Updated!*",
                parse_mode="Markdown"
            )
            await send_large_message(context, chat_id, f"📝 *Content Preview:*\n\n{clean_text}")
            await status_msg.delete()
        else:
            await status_msg.edit_text("⚠️ Sync operation failed. Check logs.")
            logger.error(f"[USER:{user_id}] FAILURE: Git sync failed.")

    except Exception as e:
        logger.error(f"[USER:{user_id}] ERROR: {str(e)}", exc_info=True)
        await status_msg.edit_text(f"❌ System Error: {str(e)}")

@restricted
async def process_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for non-textual media (Images, Videos, Documents).
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    media_group_id = update.message.media_group_id

    if not media_group_id:
        # SINGLE FILE PATH
        status_msg = await update.message.reply_text("⏳ Processing Media...")
        try:
            is_valid, file_info, error_message = validate_media_file(update.message)
            if not is_valid:
                await status_msg.edit_text(error_message)
                return

            file_info['caption'] = update.message.caption
            user_cfg = get_user_config(user_id)

            await status_msg.edit_text(f"🛰️ Downloading '{file_info['original_name']}'...")
            await processor.ingest_single_media(user_cfg, file_info, file_info['file_id'], context, status_msg=status_msg)

            await status_msg.edit_text(f"✅ Data Secured! '{file_info['original_name']}' saved to your Inbox.")
            logger.info(f"[USER:{user_id}] Media secured: {file_info['file_name']}")

        except Exception as e:
            logger.error(f"[USER:{user_id}] Media Ingestion Error: {e}", exc_info=True)
            await status_msg.edit_text(f"❌ Error: {str(e)}")
        return

    # MEDIA GROUP (ALBUM) PATH
    if media_group_id not in _media_groups_processing:
        _media_groups_processing[media_group_id] = {
            'updates': [],
            'task': None,
            'status_msg': await update.message.reply_text("⏳ Processing Media Group...")
        }

    group_data = _media_groups_processing[media_group_id]
    group_data['updates'].append(update)

    if group_data['task']:
        group_data['task'].cancel()

    group_data['task'] = asyncio.create_task(
        debounced_ingest_group(media_group_id, user_id, context)
    )

async def debounced_ingest_group(media_group_id: str, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        await asyncio.sleep(MEDIA_GROUP_DEBOUNCE_TIME)
        group_data = _media_groups_processing.pop(media_group_id, None)
        if not group_data:
            return

        updates = group_data['updates']
        status_msg = group_data['status_msg']
        user_cfg = get_user_config(user_id)

        await status_msg.edit_text(f"🛰️ Downloading {len(updates)} files from group...")
        results = await processor.ingest_media_group(user_cfg, updates, context)

        succeeded = results.get('succeeded', 0)
        failed = results.get('failed', 0)

        if failed == 0:
            await status_msg.edit_text(f"✅ Data Secured! {succeeded} items saved to your Inbox.")
        elif succeeded > 0:
            await status_msg.edit_text(f"⚠️ Data Secured! {succeeded} files saved. {failed} failed. Check vault.")
        else:
            await status_msg.edit_text(f"❌ All items in media group failed.")

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in debounced_ingest_group: {e}", exc_info=True)

async def _shutdown_media_group_timers():
    if not _media_groups_processing:
        return
    for media_group_id, group_data in _media_groups_processing.items():
        task = group_data.get('task')
        if task and not task.done():
            task.cancel()
    _media_groups_processing.clear()

# --- 4. ENTRY POINT ---
def main():
    system_check()
    backoff_delay = 5
    max_backoff = 60

    while True:
        try:
            token = os.getenv("TELEGRAM_BOT_TOKEN")
            if not token:
                logger.critical("TELEGRAM_BOT_TOKEN not found!")
                return

            request_config = HTTPXRequest(
                connect_timeout=HTTP_CONNECT_TIMEOUT,
                read_timeout=HTTP_READ_TIMEOUT,
                write_timeout=HTTP_WRITE_TIMEOUT
            )
            app = ApplicationBuilder().token(token).request(request_config).build()

            app.add_handler(MessageHandler((filters.VOICE | filters.AUDIO), process_entry))
            app.add_handler(MessageHandler(
                filters.ATTACHMENT & ~filters.VOICE & ~filters.AUDIO & ~filters.TEXT,
                process_media
            ))
            app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), process_entry))
            app.add_error_handler(error_handler)

            logger.info("🧠 Knowledge Ingestion Engine: Online")
            app.run_polling(drop_pending_updates=True)
            backoff_delay = 5

        except (KeyboardInterrupt, SystemExit):
            logger.info("Bot stopping...")
            break
        except Exception as e:
            logger.error(f"Application crash: {e}. Restarting in {backoff_delay}s...", exc_info=True)
            time.sleep(backoff_delay)
            backoff_delay = min(backoff_delay * 2, max_backoff)

if __name__ == '__main__':
    main()
