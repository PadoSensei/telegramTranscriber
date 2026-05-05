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

from config import VAULT_CONFIGS, get_user_config, HTTP_CONNECT_TIMEOUT, HTTP_READ_TIMEOUT, HTTP_WRITE_TIMEOUT
from bot_utils import restricted, parse_vault_request, send_large_message, validate_media_file
from exceptions import MediaIngestionError, TelegramDownloadError, GitPersistenceError
from transcriber import Transcriber, HallucinationError
from factory import ManagerFactory
from state_manager import StateManager

# --- 1. SETUP ---
load_dotenv()
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
)
logger = logging.getLogger("2ndBrain")

def system_check():
    """
    Validates infrastructure, environment variables, and user configurations at boot.
    Fails fast if critical components are missing or misconfigured.
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

    logger.info("🚀 System Diagnostics Passed. Bot is ready to boot.")

# Initialize Services
transcriber = Transcriber(model_name="tiny") 
state_manager = StateManager()
processor = ManagerFactory.get_processor()

# In-memory storage for media group debouncing
# Format: {media_group_id: {'updates': [Update], 'task': asyncio.Task, 'status_msg': Message}}
_media_groups_processing = {}

# --- 2. ERROR HANDLING ---

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and handle network-related blips."""
    logger.error("Exception while handling an update:", exc_info=context.error)

    # Handle Network and Read errors specifically to prevent loop termination
    if isinstance(context.error, (NetworkError, httpx.ReadError, httpx.WriteError, httpx.ConnectError)):
        logger.warning(f"Network-related error detected: {type(context.error).__name__}. Loop recovery should handle this.")
        return

    # For other types of errors, we might want to notify the user if update is valid
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
    Supports follow-up hashtags (#star) for previous voice notes.
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name
    try:
        user_cfg_model = get_user_config(user_id)
        user_cfg = user_cfg_model.dict() # For backward compatibility with existing code
    except ValueError as e:
        logger.error(f"Config error for user {user_id}: {e}")
        await context.bot.send_message(chat_id=chat_id, text="❌ Configuration Error. Please contact admin.")
        return

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
            try:
                temp_path = await transcriber.get_voice_file(update, context)
                raw_content = await transcriber.transcribe(temp_path)
            except HallucinationError:
                await status_msg.edit_text("I caught some background noise, but nothing clear enough to save.")
                return
            
            # If user included a caption (text with the audio), append it
            if update.message.caption:
                raw_content = f"{raw_content} {update.message.caption}"
            
            # BI-DIRECTIONAL CACHE: Check for Primed Tag
            pending_tag = state_manager.get_pending_tag(user_id)
            if pending_tag:
                logger.info(f"[USER:{user_id}] PRIMED: Applying pending tag {pending_tag} to new audio.")
                raw_content = f"{raw_content} {pending_tag}"
                state_manager.clear_pending_tag(user_id)
                await status_msg.edit_text(f"🔗 Primed tag `{pending_tag}` applied.")

            # Save to persistent state in case they send a hashtag in the next message
            state_manager.set_transcript(user_id, raw_content)
            logger.info(f"[USER:{user_id}] Transcription saved to state.")

        else:
            # It's a text message. Check if it's a "Follow-up Hashtag"
            # Logic: If text starts with '#' and is only one word
            is_single_hashtag = incoming_text.startswith("#") and len(incoming_text.split()) == 1
            
            cached_text = state_manager.get_transcript(user_id)
            if is_single_hashtag:
                if cached_text:
                    # Case 1: Tag sent AFTER audio
                    raw_content = f"{cached_text} {incoming_text}"
                    logger.info(f"[USER:{user_id}] FOLLOW-UP: Applying {incoming_text} to cached content.")
                    await status_msg.edit_text(f"🔗 Linking `{incoming_text}` to your last voice note...")
                else:
                    # Case 2: Tag sent BEFORE audio (Priming)
                    state_manager.set_pending_tag(user_id, incoming_text)
                    logger.info(f"[USER:{user_id}] PRIMING: User {user_id} primed {incoming_text}")
                    await status_msg.edit_text(f"⏳ Tag `{incoming_text}` primed. Send your voice note now!")
                    return # Exit early, we wait for audio
            else:
                raw_content = incoming_text
                # Update state with latest text as well
                state_manager.set_transcript(user_id, raw_content)

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
        
        # Unified stateless processor handling the request
        clean_text, analysis, git_success, google_success = await processor.run_sync_stack(
            user_cfg_model, target_cat, target_proj, raw_content
        )

        # PHASE D: Feedback
        if git_success:
            logger.info(f"[USER:{user_id}] SYNC SUCCESS: GitHub updated.")

            # Use exact wording requested for soft-fail
            status_text = "🌟 *Obsidian Updated!*"
            if user_cfg_model.gdrive_doc_id and not google_success:
                status_text += "\n(⚠️ Google Sync failed)"
            
            # Send confirmation and transcript
            await context.bot.send_message(
                chat_id=chat_id, 
                text=status_text,
                parse_mode="Markdown"
            )
            await send_large_message(context, chat_id, f"📝 *Content Preview:*\n\n{clean_text}")
            await status_msg.delete()
        else:
            await status_msg.edit_text("⚠️ All sync operations failed. Check logs.")
            logger.error(f"[USER:{user_id}] FAILURE: Both Git and Google sync failed.")

    except Exception as e:
        logger.error(f"[USER:{user_id}] ERROR: {str(e)}", exc_info=True)
        await status_msg.edit_text(f"❌ System Error: {str(e)}")

@restricted
async def process_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for non-textual media (Images, Videos, Documents).
    Implements debouncing for media groups to provide consolidated feedback.
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    media_group_id = update.message.media_group_id

    if not media_group_id:
        # SINGLE FILE PATH
        status_msg = await update.message.reply_text("⏳ Processing Media...")
        try:
            # 1. Validation
            is_valid, file_info, error_message = validate_media_file(update.message)
            if not is_valid:
                await status_msg.edit_text(error_message)
                return

            file_info['caption'] = update.message.caption
            user_cfg = get_user_config(user_id)

            # 2. Progress Feedback
            await status_msg.edit_text(f"🛰️ Downloading '{file_info['original_name']}'...")

            # 3. Ingestion
            # We add a small intermediate status for "Securing" as requested.
            # Note: processor handles heavy lifting. We pass status_msg to it
            # so it can update the user when it transitions from Downloading to Securing.

            # First update to Downloading is already done above.
            await processor.ingest_single_media(user_cfg, file_info, file_info['file_id'], context, status_msg=status_msg)

            await status_msg.edit_text(f"✅ Data Secured! '{file_info['original_name']}' saved to your Inbox.")
            logger.info(f"[USER:{user_id}] Media secured: {file_info['file_name']}")

        except TelegramDownloadError as e:
            logger.error(f"[USER:{user_id}] Telegram Download Error: {e}")
            await status_msg.edit_text("⚠️ Failed to download your file from Telegram. This might be a temporary network issue. Please try again.")
        except GitPersistenceError as e:
            logger.error(f"[USER:{user_id}] Git Persistence Error: {e}")
            await status_msg.edit_text("❌ Failed to save your file to the Obsidian vault. This might be a temporary issue with GitHub or your repository settings. Please try again.")
        except MediaIngestionError as e:
            logger.error(f"[USER:{user_id}] Media Ingestion Error: {e}")
            await status_msg.edit_text(f"❌ {str(e)}")
        except Exception as e:
            logger.error(f"[USER:{user_id}] Unexpected Media Ingestion Error: {e}", exc_info=True)
            await status_msg.edit_text(f"❌ An internal error occurred while processing your request. The admin has been notified.")
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

    # Debounce: Cancel previous timer and start a new one
    if group_data['task']:
        group_data['task'].cancel()

    group_data['task'] = asyncio.create_task(
        debounced_ingest_group(media_group_id, user_id, context)
    )

async def debounced_ingest_group(media_group_id: str, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """
    Waits for 1.5s of silence for a media group before processing all items at once.
    """
    try:
        await asyncio.sleep(1.5)

        # Retrieve and clear from tracking
        group_data = _media_groups_processing.pop(media_group_id, None)
        if not group_data:
            return

        updates = group_data['updates']
        status_msg = group_data['status_msg']

        user_cfg = get_user_config(user_id)

        await status_msg.edit_text(f"🛰️ Downloading {len(updates)} files from group...")

        results = await processor.ingest_media_group(user_cfg, updates, context)

        # Consolidated Feedback
        succeeded = results['succeeded']
        failed = results['failed']
        total = results['total_files']

        if failed == 0:
            await status_msg.edit_text(f"✅ Data Secured! {succeeded} items saved to your Inbox.")
        elif succeeded > 0:
            first_fail = results['failed_details'][0]
            await status_msg.edit_text(
                f"⚠️ Data Secured! {succeeded} files saved. {failed} files failed "
                f"(e.g., '{first_fail['filename']}' - {first_fail['reason']}). Please check your vault."
            )
        else:
            fail_summary = "\n".join([f"- {d['filename']}: {d['reason']}" for d in results['failed_details']])
            await status_msg.edit_text(f"❌ All items in media group failed:\n{fail_summary}")

    except asyncio.CancelledError:
        # Expected when a new item arrives before the timer expires
        pass
    except Exception as e:
        logger.error(f"Error in debounced_ingest_group: {e}", exc_info=True)
        # Attempt to notify the user if we still have access to the group_data or status_msg
        try:
            if 'status_msg' in locals() and status_msg:
                await status_msg.edit_text(f"❌ Failed to process media group: {str(e)}")
        except Exception as notify_error:
            logger.error(f"Failed to send group error notification: {notify_error}")

async def _shutdown_media_group_timers():
    """
    Cancels any active media group debouncing timers and clears the state.
    """
    if not _media_groups_processing:
        return

    logger.info(f"Shutting down {len(_media_groups_processing)} active media group timers...")

    for media_group_id, group_data in _media_groups_processing.items():
        task = group_data.get('task')
        if task and not task.done():
            task.cancel()
            logger.debug(f"Cancelled timer for media group: {media_group_id}")

    _media_groups_processing.clear()
    logger.info("Media group processing state cleared.")

# --- 3. ENTRY POINT ---
def main():
    """Main entry point with supervisor loop and exponential back-off."""
    import time

    # Run boot diagnostics before starting the bot
    system_check()

    backoff_delay = 5
    max_backoff = 60

    while True:
        try:
            token = os.getenv("TELEGRAM_BOT_TOKEN")
            if not token:
                logger.critical("TELEGRAM_BOT_TOKEN not found in environment!")
                return

            # Request config with optimized timeouts for heavy IO (transcription)
            request_config = HTTPXRequest(
                connect_timeout=HTTP_CONNECT_TIMEOUT,
                read_timeout=HTTP_READ_TIMEOUT,
                write_timeout=HTTP_WRITE_TIMEOUT
            )
            app = ApplicationBuilder().token(token).request(request_config).build()

            # Route Voice, Audio, and Text to the processor
            app.add_handler(MessageHandler((filters.VOICE | filters.AUDIO), process_entry))

            # Route other media attachments to security handler
            # filters.ATTACHMENT includes VOICE/AUDIO/PHOTO/VIDEO/DOCUMENT/etc.
            # We exclude VOICE/AUDIO because process_entry handles them, and TEXT.
            app.add_handler(MessageHandler(
                filters.ATTACHMENT & ~filters.VOICE & ~filters.AUDIO & ~filters.TEXT,
                process_media
            ))

            app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), process_entry))

            # Global Error Registry
            app.add_error_handler(error_handler)

            logger.info("🧠 2ndBrain Orchestrator: Multi-Tenant Mode Online")

            # Start polling (blocking)
            app.run_polling(drop_pending_updates=True)

            # If polling exits gracefully, reset backoff for next attempt
            backoff_delay = 5

        except (KeyboardInterrupt, SystemExit):
            logger.info("Bot stopping...")
            # Create a new event loop to run the async shutdown task if the current one is closed
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(_shutdown_media_group_timers())
                else:
                    loop.run_until_complete(_shutdown_media_group_timers())
            except Exception as shutdown_error:
                logger.error(f"Error during graceful shutdown: {shutdown_error}")

            logger.info("Bot stopped by user.")
            break
        except Exception as e:
            logger.error(f"Application crash detected: {e}. Restarting in {backoff_delay}s...", exc_info=True)
            time.sleep(backoff_delay)
            # Exponential back-off capped at 60s
            backoff_delay = min(backoff_delay * 2, max_backoff)

if __name__ == '__main__':
    main()