import os
import re
import asyncio
import whisper
import logging
import time
from datetime import datetime, timedelta
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import google.generativeai as genai

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# Project Modules
from config import ALLOWED_IDS
from vault_manager import VaultManager

# --- 1. SETUP & CONFIG ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Intent memory: {user_id: {"project": "Name", "expires": datetime}}
USER_PROJECT_INTENT = {}

# Load credentials
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO_URL = os.getenv("GITHUB_REPO_URL")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")

genai.configure(api_key=GEMINI_API_KEY)
gemini = genai.GenerativeModel("gemini-2.0-flash")

vault = None
if all([GITHUB_TOKEN, GITHUB_REPO_URL, GITHUB_USERNAME]):
    vault = VaultManager(GITHUB_REPO_URL, GITHUB_TOKEN, GITHUB_USERNAME)

model = whisper.load_model("tiny", device="cpu") 
executor = ThreadPoolExecutor(max_workers=1)

# --- 2. SECURITY ---
def restricted(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id not in ALLOWED_IDS:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ *Access Denied.*")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- 3. UTILITY FUNCTIONS ---
def parse_vault_request(text):
    if not text: return False, None
    text_lower = text.lower()
    intent_pattern = r"(#?2nd\s?brain|#?second\s?brain)"
    if not bool(re.search(intent_pattern, text_lower)): return False, None

    known_projects = ["Feena", "AISolutions", "Zil"]
    tags = re.findall(r"#(\w+)", text)
    found_project = next((p for p in known_projects if any(t.lower() == p.lower() for t in tags)), None)
    
    if not found_project:
        found_project = next((p for p in known_projects if p.lower() in text_lower), None)

    return True, (found_project or "00_Inbox")

def get_clean_content(text):
    if not text: return ""
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"(?i)second\s?brain|2nd\s?brain", "", text)
    return text.strip()

async def send_large_message(context, chat_id, text):
    if not text: return
    parts = [text[i:i+3900] for i in range(0, len(text), 3900)]
    for part in parts:
        try:
            await context.bot.send_message(chat_id=chat_id, text=part, parse_mode="Markdown")
        except Exception:
            await context.bot.send_message(chat_id=chat_id, text=part, parse_mode=None)

# --- 4. BOT LOGIC ---

@restricted
async def process_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    file_id = message.voice.file_id if message.voice else (message.audio.file_id if message.audio else None)
    if not file_id: return 

    status_msg = await context.bot.send_message(chat_id=chat_id, text="⏳ Processing audio...")
    temp_path = f"temp_{int(datetime.now().timestamp())}.oga"

    try:
        # A. WHISPER TRANSCRIPTION
        voice_file = await context.bot.get_file(file_id)
        await voice_file.download_to_drive(temp_path)
        raw_transcript = await asyncio.get_event_loop().run_in_executor(executor, lambda: model.transcribe(temp_path, fp16=False)["text"])

        # B. CONTEXT COORDINATION (The "Memory" Logic)
        current_time = datetime.now()
        buffered = USER_PROJECT_INTENT.get(user_id)
        project_context = "00_Inbox"
        is_coordinated = False
        
        # 1. Check if audio has its own tags (Caption)
        should_sync, found_proj = parse_vault_request(message.caption or "")
        
        if should_sync:
            project_context = found_proj
            is_coordinated = True
        # 2. If no caption, check if user sent tags in the last 1 MINUTE
        elif buffered and buffered["expires"] > current_time:
            project_context = buffered["project"]
            is_coordinated = True
            del USER_PROJECT_INTENT[user_id] # Clear after use
        # 3. Last fallback: Check spoken words in transcript
        else:
            should_sync, spoken_proj = parse_vault_request(raw_transcript)
            if should_sync:
                project_context = spoken_proj
                is_coordinated = True

        # C. AI ANALYSIS
        clean_text = get_clean_content(raw_transcript)
        clean_transcript = await asyncio.get_event_loop().run_in_executor(None, lambda: gemini.generate_content(f"Clean up grammar:\n{clean_text}").text)
        analysis_output = await asyncio.get_event_loop().run_in_executor(None, lambda: gemini.generate_content(f"Extract action items and summary:\n{clean_transcript}").text)

        # D. SYNC OR DISPLAY
        if is_coordinated and vault:
            await status_msg.edit_text(f"🚀 Syncing to `{project_context}`...")
            success = await asyncio.get_event_loop().run_in_executor(executor, vault.push_to_obsidian, project_context, clean_transcript, analysis_output)
            if success:
                await context.bot.send_message(chat_id=chat_id, text=f"✅ *Vault updated:* `{project_context}`")
            else:
                await context.bot.send_message(chat_id=chat_id, text="⚠️ Sync failed.")
        else:
            # Traditional behavior if no #2ndbrain tag found anywhere
            await send_large_message(context, chat_id, f"📜 *Transcript*\n\n{clean_transcript}")
            await send_large_message(context, chat_id, f"🧠 *Analysis*\n\n{analysis_output}")

        await status_msg.delete()

    except Exception as e:
        logger.error(f"Error: {e}")
        await context.bot.send_message(chat_id=chat_id, text="❌ Processing failed.")
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

@restricted
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    should_sync, project = parse_vault_request(text)
    clean_text = get_clean_content(text)
    
    # If it's JUST tags (like #2ndbrain #zil), store context for 1 minute
    if should_sync and not clean_text:
        USER_PROJECT_INTENT[user_id] = {
            "project": project,
            "expires": datetime.now() + timedelta(seconds=60) # 1 Minute Window
        }
        # Subtle confirmation
        await context.bot.send_message(chat_id=chat_id, text=f"🏷️ Context: `{project}` (Ready for audio)")
        return

    # Normal text note processing
    response = await asyncio.get_event_loop().run_in_executor(None, lambda: gemini.generate_content(f"Analyze note: {clean_text}").text)

    if should_sync and vault:
        await asyncio.get_event_loop().run_in_executor(executor, vault.push_to_obsidian, project, clean_text, response)
        await context.bot.send_message(chat_id=chat_id, text=f"✅ *Vault updated:* `{project}`")
    else:
        await send_large_message(context, chat_id, f"📝 *Note Captured*\n\n{response}")

if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(MessageHandler((filters.VOICE | filters.AUDIO), process_media))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    application.run_polling()