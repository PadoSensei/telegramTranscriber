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
from bot_utils import restricted, parse_vault_request, send_large_message
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
            app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), process_entry))

            # Global Error Registry
            app.add_error_handler(error_handler)

            logger.info("🧠 2ndBrain Orchestrator: Multi-Tenant Mode Online")

            # Start polling (blocking)
            app.run_polling(drop_pending_updates=True)

            # If polling exits gracefully, reset backoff for next attempt
            backoff_delay = 5

        except (KeyboardInterrupt, SystemExit):
            logger.info("Bot stopped by user.")
            break
        except Exception as e:
            logger.error(f"Application crash detected: {e}. Restarting in {backoff_delay}s...", exc_info=True)
            time.sleep(backoff_delay)
            # Exponential back-off capped at 60s
            backoff_delay = min(backoff_delay * 2, max_backoff)

if __name__ == '__main__':
    main()