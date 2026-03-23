import os
import re
import asyncio
import whisper
import logging
import time
from datetime import datetime
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import google.generativeai as genai

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest
from telegram.error import BadRequest

# Project Modules
from config import ALLOWED_IDS
from vault_manager import VaultManager

# --- 1. SETUP & CONFIG ---
load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# API Keys
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Git Config
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO_URL = os.getenv("GITHUB_REPO_URL")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise ValueError("❌ Missing core API Keys in .env file!")

# Initialize AI
genai.configure(api_key=GEMINI_API_KEY)
gemini = genai.GenerativeModel("gemini-2.0-flash")

# Initialize Vault Manager
vault = None
if all([GITHUB_TOKEN, GITHUB_REPO_URL, GITHUB_USERNAME]):
    vault = VaultManager(GITHUB_REPO_URL, GITHUB_TOKEN, GITHUB_USERNAME)
    logger.info("📦 Vault Manager initialized and ready for sync.")
else:
    logger.warning("⚠️ Git environment variables missing. Obsidian sync disabled.")

print(f"\n{'='*50}")
print(f"🧠 SECOND BRAIN SYSTEM STARTING AT {datetime.now().strftime('%H:%M:%S')}")
print("--- 🌀 Loading Whisper 'tiny' on CPU ---")
start_load = time.time()
model = whisper.load_model("tiny", device="cpu") 
print(f"--- ✅ Whisper Loaded in {time.time() - start_load:.2f}s ---")
print(f"{'='*50}\n")

executor = ThreadPoolExecutor(max_workers=1)

# --- 2. SECURITY LAYER ---

def restricted(func):
    """Decorator to only allow authorized IDs."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ALLOWED_IDS:
            logger.warning(f"🚫 Unauthorized access attempt by ID: {user_id}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text="❌ *Access Denied.*\nThis is a private Second Brain bot.",
                parse_mode="Markdown"
            )
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- 3. UTILITY FUNCTIONS ---

def parse_vault_request(text):
    """
    Super-robust intent parser.
    Matches: #2ndBrain, 'second brain', '2nd brain' (case insensitive).
    Returns (should_sync, project_name, error_msg)
    """
    if not text:
        return False, None, None
    
    text_lower = text.lower()
    
    # 1. Broad intent check using regex for hashtags or spoken variations
    intent_pattern = r"(#?2nd\s?brain|#?second\s?brain)"
    has_sync_intent = bool(re.search(intent_pattern, text_lower))
    
    if not has_sync_intent:
        return False, None, None

    # 2. Extract hashtags for project identification
    tags = re.findall(r"#(\w+)", text)
    known_projects = ["Feena", "AISolutions", "Zil"]
    found_project = None
    
    # Check hashtag matches first (Priority)
    for t in tags:
        match = next((p for p in known_projects if p.lower() == t.lower()), None)
        if match:
            found_project = match
            break
            
    # Fallback: check if the raw text mentions the project name (for native voice notes)
    if not found_project:
        for project in known_projects:
            if project.lower() in text_lower:
                found_project = project
                break

    # Log the decision to Railway Console for debugging
    logger.info(f"🔍 Intent Parser: Sync={has_sync_intent}, Project={found_project}, Input='{text[:50]}...' ")

    if found_project:
        return True, found_project, None
    else:
        # User intended to sync but didn't specify a valid project
        return True, "00_Inbox", "💡 *Tip:* Mention a project (e.g. `#Feena`) to sort this note."

async def send_large_message(context, chat_id, text, parse_mode="Markdown"):
    """Handles long text and aggressively falls back to plain text on parser errors."""
    parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for part in parts:
        try:
            await context.bot.send_message(chat_id=chat_id, text=part, parse_mode=parse_mode)
        except Exception as e:
            logger.warning(f"⚠️ Markdown failed, sending as plain text: {e}")
            await context.bot.send_message(chat_id=chat_id, text=part, parse_mode=None)

def call_gemini(prompt):
    try:
        response = gemini.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Gemini Error: {e}")
        return f"⚠️ AI Error: {e}"

def transcribe_sync(file_path: str):
    start_t = time.time()
    print(f"🎙️  [Whisper] Transcribing {file_path}...")
    result = model.transcribe(file_path, fp16=False)
    print(f"✨ [Whisper] Finished in {time.time() - start_t:.2f}s")
    return result["text"]

# --- 4. BRAIN LOGIC ---

@restricted
async def process_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = update.effective_chat.id
    user_name = message.from_user.first_name
    
    file_id = None
    file_label = "Audio"

    if message.voice:
        file_id = message.voice.file_id
        file_label = "Voice Note"
    elif message.audio:
        file_id = message.audio.file_id
        file_label = "Audio File"
    elif message.document:
        mime = message.document.mime_type
        if mime and ("audio" in mime or "ogg" in mime or "opus" in mime):
            file_id = message.document.file_id
            file_label = "Shared Audio"
    
    if not file_id: return 

    print(f"\n📩 {file_label.upper()} FROM {user_name.upper()}")
    status_msg = await context.bot.send_message(chat_id=chat_id, text=f"⏳ *{file_label} received.* Processing...")
    temp_path = f"temp_{int(datetime.now().timestamp())}.oga"

    try:
        # A. DOWNLOAD & TRANSCRIBE
        voice_file = await context.bot.get_file(file_id)
        await voice_file.download_to_drive(temp_path)
        
        await status_msg.edit_text("⚙️ *Transcribing audio...*")
        loop = asyncio.get_event_loop()
        raw_transcript = await loop.run_in_executor(executor, transcribe_sync, temp_path)

        # B. AI PROCESSING
        await status_msg.edit_text("✍️ *Refining transcript...*")
        clean_prompt = f"Clean up grammar and punctuation for {user_name}. Verbatim but readable:\n\n{raw_transcript}"
        clean_transcript = await loop.run_in_executor(None, call_gemini, clean_prompt)

        await status_msg.edit_text("🧠 *Generating analysis...*")
        analysis_prompt = f"Analyze for {user_name}'s Second Brain. Use ** for bold. Summarize and list Action Items:\n\n{clean_transcript}"
        analysis_output = await loop.run_in_executor(None, call_gemini, analysis_prompt)

        # C. DISPLAY RESULTS (Decoupled with Try/Except)
        try:
            await send_large_message(context, chat_id, f"📜 *Full Transcript*\n\n{clean_transcript}")
            await send_large_message(context, chat_id, f"🧠 *Second Brain Analysis*\n\n{analysis_output}")
        except Exception as msg_err:
            logger.error(f"Display Error: {msg_err}")
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Display error occurred, proceeding to vault sync...")

        # D. OBSIDIAN SYNC (Triggered by Caption OR Spoken words)
        trigger_text = f"{message.caption or ''} {clean_transcript or ''}"
        should_sync, project, warning = parse_vault_request(trigger_text)

        if should_sync and vault:
            if warning:
                await context.bot.send_message(chat_id=chat_id, text=warning)

            await status_msg.edit_text(f"🚀 *Syncing to Obsidian:* `{project}`...")
            success = await loop.run_in_executor(
                executor, 
                vault.push_to_obsidian, 
                project, 
                clean_transcript, 
                analysis_output
            )
            
            if success:
                await context.bot.send_message(chat_id=chat_id, text=f"✅ Saved to `{project}/TelegramCaptures`.")
            else:
                await context.bot.send_message(chat_id=chat_id, text="⚠️ Vault sync failed. Check server logs.")

        await status_msg.delete()

    except Exception as e:
        logger.error(f"Critical process failure: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Failed: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@restricted
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id
    
    print(f"💬 TEXT NOTE FROM {update.message.from_user.first_name.upper()}")
    
    # Corrected Unpacking (3 values)
    should_sync, project, warning = parse_vault_request(text)
    
    prompt = f"Analyze this note for a Second Brain. Extract insights/tasks: {text}"
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, call_gemini, prompt)
    
    await context.bot.send_message(chat_id=chat_id, text=f"📝 *Note Captured*\n\n{response}")

    if should_sync and vault:
        if warning:
            await context.bot.send_message(chat_id=chat_id, text=warning)
        await loop.run_in_executor(executor, vault.push_to_obsidian, project, text, response)
        await context.bot.send_message(chat_id=chat_id, text=f"✅ Text synced to `{project}`.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"⚠️ System Error: {context.error}")

# --- 5. ENTRY POINT ---
if __name__ == '__main__':
    request_config = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).request(request_config).build()

    application.add_handler(MessageHandler((filters.VOICE | filters.AUDIO | filters.Document.ALL), process_media))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    application.add_error_handler(error_handler)

    print(f"🚀 Second Brain Monolith Online (Security Active)")
    application.run_polling(drop_pending_updates=True)