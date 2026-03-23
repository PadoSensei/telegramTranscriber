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
from telegram.request import HTTPXRequest

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

# Intent memory: {user_id: {"project": "Name", "expires": datetime}}
USER_PROJECT_INTENT = {}

# Credentials
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
    """Decorator to only allow authorized IDs."""
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
    """Identifies #2ndBrain and project name. Returns (should_sync, project_name)."""
    if not text: return False, None
    text_lower = text.lower()
    
    intent_pattern = r"(#?2nd\s?brain|#?second\s?brain)"
    has_sync_intent = bool(re.search(intent_pattern, text_lower))
    if not has_sync_intent: return False, None

    known_projects = ["Feena", "AISolutions", "Zil"]
    tags = re.findall(r"#(\w+)", text)
    found_project = None
    
    for t in tags:
        match = next((p for p in known_projects if p.lower() == t.lower()), None)
        if match:
            found_project = match
            break
            
    if not found_project:
        for project in known_projects:
            if project.lower() in text_lower:
                found_project = project
                break

    return True, (found_project or "00_Inbox")

def get_clean_content(text):
    """Strips hashtags and sync keywords to keep AI analysis clean."""
    if not text: return ""
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"(?i)second\s?brain|2nd\s?brain", "", text)
    return text.strip()

async def send_large_message(context, chat_id, text, parse_mode="Markdown"):
    """Splits long text and falls back to plain text on error."""
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

# --- 4. BRAIN LOGIC ---

@restricted
async def process_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_name = message.from_user.first_name
    
    file_id = message.voice.file_id if message.voice else (message.audio.file_id if message.audio else None)
    if not file_id: return 

    status_msg = await context.bot.send_message(chat_id=chat_id, text=f"⏳ Processing {user_name}'s audio...")
    temp_path = f"temp_{int(datetime.now().timestamp())}.oga"

    try:
        # A. WHISPER TRANSCRIPTION
        voice_file = await context.bot.get_file(file_id)
        await voice_file.download_to_drive(temp_path)
        raw_transcript = await asyncio.get_event_loop().run_in_executor(executor, lambda: model.transcribe(temp_path, fp16=False)["text"])

        # B. CONTEXT COORDINATION (Check buffer for hashtags sent in previous message)
        current_time = datetime.now()
        buffered = USER_PROJECT_INTENT.get(user_id)
        project_context = "00_Inbox"
        is_syncing = False
        
        # Priority 1: Audio Caption | Priority 2: 60s Buffer | Priority 3: Transcript words
        should_sync_cap, cap_proj = parse_vault_request(message.caption or "")
        if should_sync_cap:
            project_context, is_syncing = cap_proj, True
        elif buffered and buffered["expires"] > current_time:
            project_context, is_syncing = buffered["project"], True
            del USER_PROJECT_INTENT[user_id] # Use once and clear
        else:
            should_sync_trans, trans_proj = parse_vault_request(raw_transcript)
            if should_sync_trans:
                project_context, is_syncing = trans_proj, True

        # C. AI ANALYSIS (Scrubbed of technical tags)
        clean_content = get_clean_content(raw_transcript)
        if not clean_content: clean_content = "[No spoken words detected]"

        clean_transcript = await asyncio.get_event_loop().run_in_executor(None, call_gemini, f"Fix grammar and punctuation for {user_name}:\n\n{clean_content}")
        analysis_output = await asyncio.get_event_loop().run_in_executor(None, call_gemini, f"Analyze for Second Brain. Provide Summary & Action Items:\n\n{clean_transcript}")

        # D. VAULT SYNC
        if is_syncing and vault:
            await status_msg.edit_text(f"🚀 Syncing to `{project_context}`...")
            success = await asyncio.get_event_loop().run_in_executor(executor, vault.push_to_obsidian, project_context, clean_transcript, analysis_output)
            if success:
                await context.bot.send_message(chat_id=chat_id, text=f"✅ *2nd Brain updated successfully* in project `{project_context}`!")
            else:
                await context.bot.send_message(chat_id=chat_id, text="⚠️ Vault sync failed.")
        else:
            # Traditional behavior: Output everything to Telegram if no hashtags found
            await send_large_message(context, chat_id, f"📜 *Full Transcript*\n\n{clean_transcript}")
            await send_large_message(context, chat_id, f"🧠 *Second Brain Analysis*\n\n{analysis_output}")

        await status_msg.delete()

    except Exception as e:
        logger.error(f"Failure: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Failed: {e}")
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

@restricted
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    should_sync, project = parse_vault_request(text)
    clean_text = get_clean_content(text)
    
    # If message is JUST tags (e.g. #2ndbrain #zil), store context for 60 seconds
    if should_sync and not clean_text:
        USER_PROJECT_INTENT[user_id] = {
            "project": project,
            "expires": datetime.now() + timedelta(seconds=60)
        }
        await context.bot.send_message(chat_id=chat_id, text=f"🏷️ Context set: `{project}`. Send your audio now!")
        return

    # Normal text processing
    response = await asyncio.get_event_loop().run_in_executor(None, call_gemini, f"Analyze: {clean_text}")

    if should_sync and vault:
        await asyncio.get_event_loop().run_in_executor(executor, vault.push_to_obsidian, project, clean_text, response)
        await context.bot.send_message(chat_id=chat_id, text=f"✅ *2nd Brain updated successfully* in `{project}`!")
    else:
        await send_large_message(context, chat_id, f"📝 *Note Captured*\n\n{response}")

# --- 5. ENTRY POINT ---
if __name__ == '__main__':
    request_config = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).request(request_config).build()

    application.add_handler(MessageHandler((filters.VOICE | filters.AUDIO), process_media))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    
    print(f"🚀 Second Brain Online")
    application.run_polling(drop_pending_updates=True)