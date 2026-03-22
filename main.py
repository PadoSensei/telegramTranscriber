import os
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

# Import the security allow-list
from config import ALLOWED_IDS

# --- 1. SETUP & CONFIG ---
load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise ValueError("❌ Missing API Keys in .env file!")

genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.0-flash" 
gemini = genai.GenerativeModel(MODEL_NAME)

print(f"\n{'='*50}")
print(f"🤖 SYSTEM STARTING AT {datetime.now().strftime('%H:%M:%S')}")
print("--- 🌀 Loading Whisper 'tiny' on CPU ---")
start_load = time.time()
model = whisper.load_model("tiny", device="cpu") 
print(f"--- ✅ Whisper Loaded in {time.time() - start_load:.2f}s ---")
print(f"{'='*50}\n")

executor = ThreadPoolExecutor(max_workers=1)

# --- 2. SECURITY LAYER ---

def restricted(func):
    """Decorator to only allow IDs in config.ALLOWED_IDS."""
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

async def send_large_message(context, chat_id, text, parse_mode="Markdown"):
    """Handles long text and protects against Telegram's fragile Markdown parser."""
    parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for part in parts:
        try:
            await context.bot.send_message(chat_id=chat_id, text=part, parse_mode=parse_mode)
        except BadRequest:
            logger.warning("Markdown failed, falling back to plain text.")
            await context.bot.send_message(chat_id=chat_id, text=part, parse_mode=None)

def call_gemini(prompt):
    try:
        response = gemini.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Gemini Error: {e}")
        return f"⚠️ Error processing with Gemini: {e}"

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
    
    # Identify the file source (Voice, Audio, or Shared WhatsApp File)
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
    
    if not file_id:
        return # Not a file we can process

    print(f"\n📩 {file_label.upper()} FROM {user_name.upper()}")
    status_msg = await context.bot.send_message(chat_id=chat_id, text=f"⏳ *{file_label} received.* Cranking the i5 engine...")
    temp_path = f"temp_{int(datetime.now().timestamp())}.oga"

    try:
        # A. DOWNLOAD
        voice_file = await context.bot.get_file(file_id)
        await voice_file.download_to_drive(temp_path)
        
        # B. TRANSCRIBE
        await status_msg.edit_text("⚙️ *Transcribing...* (Whisper Turbo is running)")
        loop = asyncio.get_event_loop()
        raw_transcript = await loop.run_in_executor(executor, transcribe_sync, temp_path)

        # C. MESSAGE 1: CLEAN TRANSCRIPT
        await status_msg.edit_text("✍️ *Cleaning up transcript...*")
        transcript_prompt = (
            f"Clean up this raw transcript from {user_name}. Fix grammar and punctuation. "
            f"Keep it verbatim but readable. Use paragraph breaks.\n\nTRANSCRIPT:\n{raw_transcript}"
        )
        clean_transcript = await loop.run_in_executor(None, call_gemini, transcript_prompt)
        await send_large_message(context, chat_id, f"📜 *Full Transcript*\n\n{clean_transcript}")

        # D. MESSAGE 2: ANALYSIS
        await status_msg.edit_text("🧠 *Analyzing for Second Brain...*")
        analysis_prompt = (
            f"Analyze this transcript for {user_name}'s Second Brain:\n"
            f"1. **Summary**: High-level overview.\n"
            f"2. **Action Items**: Bulleted list of tasks.\n"
            f"3. **Research/Further Thought**: Topics to explore deeper.\n"
            f"4. **Keywords**: 5 tags.\n\n"
            f"IMPORTANT: No underscores. Use ** for bold.\n\nTRANSCRIPT:\n{clean_transcript}"
        )
        analysis_output = await loop.run_in_executor(None, call_gemini, analysis_prompt)
        await send_large_message(context, chat_id, f"🧠 *Second Brain Analysis*\n\n{analysis_output}")
        
        await status_msg.delete()

    except Exception as e:
        logger.error(f"Error: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Failed: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@restricted
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id
    print(f"💬 TEXT NOTE FROM {update.message.from_user.first_name}")
    
    prompt = f"Extract key insights and action items from this note for a Second Brain: {text}"
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, call_gemini, prompt)
    await context.bot.send_message(chat_id=chat_id, text=f"📝 *Note Captured*\n\n{response}", parse_mode="Markdown")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"⚠️ System Error: {context.error}")
    if "httpx" in str(context.error).lower():
        await asyncio.sleep(5)

# --- 5. ENTRY POINT ---
if __name__ == '__main__':
    request_config = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)

    application = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .request(request_config)
        .build()
    )

    # Combined handler for all audio-like messages (Fixes WhatsApp sharing)
    application.add_handler(MessageHandler(
        (filters.VOICE | filters.AUDIO | filters.Document.ALL), 
        process_media
    ))
    
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    application.add_error_handler(error_handler)

    print(f"🚀 Second Brain Monolith Online (Security Active)")
    application.run_polling(drop_pending_updates=True)