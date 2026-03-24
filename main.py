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
from config import ALLOWED_IDS, VAULT_CONFIGS
from vault_manager import VaultManager

# --- 1. SETUP & CONFIG ---
load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Intent memory: {user_id: {"project": "Name", "category": "Folder", "expires": datetime}}
USER_PROJECT_INTENT = {}

# Credentials
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise ValueError("❌ Missing core API Keys in .env file!")

# Initialize AI
genai.configure(api_key=GEMINI_API_KEY)
gemini = genai.GenerativeModel("gemini-2.0-flash")

print(f"\n{'='*50}")
print(f"🧠 MULTI-TENANT SECOND BRAIN ONLINE")
model = whisper.load_model("tiny", device="cpu") 
print(f"--- ✅ Whisper Loaded ---")
print(f"{'='*50}\n")

executor = ThreadPoolExecutor(max_workers=1)

# --- 2. SECURITY & MULTI-TENANCY ---

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

def get_vault_for_user(user_id):
    """Factory function to retrieve the correct VaultManager based on User ID."""
    cfg = VAULT_CONFIGS.get(user_id)
    if not cfg:
        return None
    return VaultManager(
        repo_url=cfg["repo_url"],
        token=cfg["token"],
        username=cfg["username"]
    )

# --- 3. UTILITY FUNCTIONS ---

def parse_vault_request(text, user_map):
    """
    Identifies intent based on the specific user's category map.
    Returns (should_sync, category, project, warning)
    """
    if not text: return False, None, None, None
    text_lower = text.lower()
    
    # 1. Check for sync intent
    intent_pattern = r"(#?2nd\s?brain|#?second\s?brain)"
    if not bool(re.search(intent_pattern, text_lower)): 
        return False, None, None, None

    # 2. Get tags valid ONLY for this specific user
    known_tags = list(user_map.keys())
    tags = re.findall(r"#(\w+)", text)
    
    found_tag = None
    for t in tags:
        match = next((p for p in known_tags if p.lower() == t.lower()), None)
        if match:
            found_tag = match
            break
            
    if not found_tag:
        for tag in known_tags:
            if tag.lower() in text_lower:
                found_tag = tag
                break

    if found_tag:
        # Success: Return sync=True, the mapped Category, and the Project name
        return True, user_map[found_tag], found_tag, None
    else:
        # Fallback to Inbox
        return True, "00_Inbox", "00_Inbox", "💡 *Tip:* Mention a project name to sort this note."

def get_clean_content(text):
    """Strips hashtags and sync keywords to keep AI analysis clean."""
    if not text: return ""
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"(?i)second\s?brain|2nd\s?brain", "", text)
    return text.strip()

async def send_large_message(context, chat_id, text, parse_mode="Markdown"):
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
    print(f"🎙️  [Whisper] Transcribing {file_path}...")
    result = model.transcribe(file_path, fp16=False)
    return result["text"]

# --- 4. BOT BRAIN LOGIC ---

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
        loop = asyncio.get_event_loop()
        raw_transcript = await loop.run_in_executor(executor, transcribe_sync, temp_path)

        # B. CONTEXT COORDINATION
        user_cfg = VAULT_CONFIGS.get(user_id)
        user_map = user_cfg.get("category_map", {})
        
        current_time = datetime.now()
        buffered = USER_PROJECT_INTENT.get(user_id)
        
        target_category = "00_Inbox"
        target_project = "00_Inbox"
        is_syncing = False
        
        # Priority: Caption > Buffer > Transcript keywords
        should_sync_cap, cap_cat, cap_proj, _ = parse_vault_request(message.caption or "", user_map)
        if should_sync_cap:
            target_category, target_project, is_syncing = cap_cat, cap_proj, True
        elif buffered and buffered["expires"] > current_time:
            target_category, target_project, is_syncing = buffered["category"], buffered["project"], True
            del USER_PROJECT_INTENT[user_id] 
        else:
            should_sync_trans, trans_cat, trans_proj, _ = parse_vault_request(raw_transcript, user_map)
            if should_sync_trans:
                target_category, target_project, is_syncing = trans_cat, trans_proj, True

        # C. AI ANALYSIS
        clean_content = get_clean_content(raw_transcript)
        if not clean_content: clean_content = "[No spoken words detected]"
        clean_transcript = await loop.run_in_executor(None, call_gemini, f"Fix grammar and punctuation for {user_name}:\n\n{clean_content}")
        analysis_output = await loop.run_in_executor(None, call_gemini, f"Analyze for Second Brain Summary & Action Items:\n\n{clean_transcript}")

        # D. DYNAMIC VAULT SYNC
        if is_syncing:
            user_vault = get_vault_for_user(user_id)
            if user_vault:
                await status_msg.edit_text(f"🚀 Syncing to `{target_project}`...")
                success = await loop.run_in_executor(
                    executor, 
                    user_vault.push_to_obsidian, 
                    target_category, 
                    target_project, 
                    clean_transcript, 
                    analysis_output
                )
                if success:
                    await context.bot.send_message(chat_id=chat_id, text=f"✅ *2nd Brain updated successfully* in project `{target_project}`!")
                else:
                    await context.bot.send_message(chat_id=chat_id, text="⚠️ Vault sync failed.")
        else:
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
    
    user_cfg = VAULT_CONFIGS.get(user_id)
    user_map = user_cfg.get("category_map", {})
    
    # UNPACK 4 VALUES
    should_sync, category, project, warning = parse_vault_request(text, user_map)
    clean_text = get_clean_content(text)
    
    # If message is JUST tags, store context for 60 seconds (Include category!)
    if should_sync and not clean_text:
        USER_PROJECT_INTENT[user_id] = {
            "project": project,
            "category": category,
            "expires": datetime.now() + timedelta(seconds=60)
        }
        await context.bot.send_message(chat_id=chat_id, text=f"🏷️ Context set: `{project}`. Send your audio now!")
        return

    # Normal text processing
    response = await asyncio.get_event_loop().run_in_executor(None, call_gemini, f"Analyze: {clean_text}")

    if should_sync:
        user_vault = get_vault_for_user(user_id)
        if user_vault:
            await asyncio.get_event_loop().run_in_executor(
                executor, 
                user_vault.push_to_obsidian, 
                category, 
                project, 
                clean_text, 
                response
            )
            await context.bot.send_message(chat_id=chat_id, text=f"✅ *2nd Brain updated successfully* in `{project}`!")
            if warning: await context.bot.send_message(chat_id=chat_id, text=warning)
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