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

# API Keys & Git Config
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
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
    logger.info("📦 Vault Manager initialized.")

print(f"\n{'='*50}")
print(f"🧠 SECOND BRAIN SYSTEM ONLINE")
model = whisper.load_model("tiny", device="cpu") 
print(f"--- ✅ Whisper Loaded ---")
print(f"{'='*50}\n")

executor = ThreadPoolExecutor(max_workers=1)

# --- 2. SECURITY LAYER ---

def restricted(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ALLOWED_IDS:
            logger.warning(f"🚫 Unauthorized access attempt by ID: {user_id}")
            await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ *Access Denied.*")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- 3. UTILITY FUNCTIONS ---

def parse_vault_request(text):
    """
    Identifies sync intent and project name.
    Returns (should_sync, project_name, error_msg)
    """
    if not text: return False, None, None
    text_lower = text.lower()
    
    # Check for #2ndBrain or spoken variations
    intent_pattern = r"(#?2nd\s?brain|#?second\s?brain)"
    has_sync_intent = bool(re.search(intent_pattern, text_lower))
    
    if not has_sync_intent:
        return False, None, None

    known_projects = ["Feena", "AISolutions", "Zil"]
    tags = re.findall(r"#(\w+)", text)
    found_project = None
    
    # 1. Match Hashtags
    for t in tags:
        match = next((p for p in known_projects if p.lower() == t.lower()), None)
        if match:
            found_project = match
            break
            
    # 2. Match Spoken words
    if not found_project:
        for project in known_projects:
            if project.lower() in text_lower:
                found_project = project
                break

    if found_project:
        return True, found_project, None
    else:
        return True, "00_Inbox", "💡 *Tip:* Mention a project name (e.g. `#Feena`) to sort."

async def send_large_message(context, chat_id, text, parse_mode="Markdown"):
    """Splits long text to avoid Telegram limits."""
    if not text: return
    parts = [text[i:i+3900] for i in range(0, len(text), 3900)]
    for part in parts:
        try:
            await context.bot.send_message(chat_id=chat_id, text=part, parse_mode=parse_mode)
        except Exception:
            await context.bot.send_message(chat_id=chat_id, text=part, parse_mode=None)

def call_gemini(prompt):
    try:
        response = gemini.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Gemini Error: {e}")
        return f"⚠️ AI Error: {e}"

def transcribe_sync(file_path: str):
    result = model.transcribe(file_path, fp16=False)
    return result["text"]

# --- 4. BOT LOGIC ---

@restricted
async def process_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = update.effective_chat.id
    user_name = message.from_user.first_name
    
    file_id = message.voice.file_id if message.voice else (message.audio.file_id if message.audio else message.document.file_id if message.document else None)
    if not file_id: return 

    status_msg = await context.bot.send_message(chat_id=chat_id, text=f"⏳ Processing audio note...")
    temp_path = f"temp_{int(datetime.now().timestamp())}.oga"

    try:
        # A. DOWNLOAD & PROCESS
        voice_file = await context.bot.get_file(file_id)
        await voice_file.download_to_drive(temp_path)
        
        await status_msg.edit_text("⚙️ Transcribing...")
        loop = asyncio.get_event_loop()
        raw_transcript = await loop.run_in_executor(executor, transcribe_sync, temp_path)

        await status_msg.edit_text("🧠 Analyzing...")
        clean_transcript = await loop.run_in_executor(None, call_gemini, f"Clean up grammar for {user_name}:\n{raw_transcript}")
        analysis_output = await loop.run_in_executor(None, call_gemini, f"Analyze for {user_name}'s Second Brain. Summary & Action Items:\n{clean_transcript}")

        # B. DETERMINE PATH
        trigger_text = f"{message.caption or ''} {clean_transcript or ''}"
        should_sync, project, warning = parse_vault_request(trigger_text)

        # C. CONDITIONAL EXECUTION
        if should_sync and vault:
            await status_msg.edit_text(f"🚀 Syncing to `{project}`...")
            success = await loop.run_in_executor(executor, vault.push_to_obsidian, project, clean_transcript, analysis_output)
            
            if success:
                # OPTION 1: SYNCED - Send simple success message
                await context.bot.send_message(chat_id=chat_id, text=f"✅ *2nd Brain updated successfully* in project `{project}`!")
                if warning: await context.bot.send_message(chat_id=chat_id, text=warning)
            else:
                await context.bot.send_message(chat_id=chat_id, text="⚠️ Vault sync failed. Check server logs.")
        else:
            # OPTION 2: NOT SYNCED - Send full results to Telegram
            await send_large_message(context, chat_id, f"📜 *Full Transcript*\n\n{clean_transcript}")
            await send_large_message(context, chat_id, f"🧠 *Second Brain Analysis*\n\n{analysis_output}")

        await status_msg.delete()

    except Exception as e:
        logger.error(f"Error: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Failed: {e}")
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

@restricted
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id
    
    should_sync, project, warning = parse_vault_request(text)
    response = await asyncio.get_event_loop().run_in_executor(None, call_gemini, f"Analyze this note: {text}")

    if should_sync and vault:
        # SYNCED: Report success only
        await asyncio.get_event_loop().run_in_executor(executor, vault.push_to_obsidian, project, text, response)
        await context.bot.send_message(chat_id=chat_id, text=f"✅ *2nd Brain updated successfully* in project `{project}`!")
        if warning: await context.bot.send_message(chat_id=chat_id, text=warning)
    else:
        # NOT SYNCED: Report full analysis
        await send_large_message(context, chat_id, f"📝 *Note Captured*\n\n{response}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"⚠️ System Error: {context.error}")

if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(MessageHandler((filters.VOICE | filters.AUDIO | filters.Document.ALL), process_media))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    application.add_error_handler(error_handler)
    application.run_polling(drop_pending_updates=True)