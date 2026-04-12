import os
import asyncio
import whisper
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

class HallucinationError(Exception):
    """Raised when Whisper returns a common hallucination or gibberish."""
    pass

class Transcriber:
    def __init__(self, model_name="tiny", device="cpu"):
        """
        Initializes the Whisper model once on startup.
        'tiny' is best for speed on CPU; 'base' is better for accuracy.
        """
        logger.info(f"⏳ Loading Whisper model ({model_name})...")
        self.model = whisper.load_model(model_name, device=device)
        self.executor = ThreadPoolExecutor(max_workers=1) 
        logger.info("✅ Whisper Transcriber Ready")

    async def get_voice_file(self, update, context):
        """
        Downloads the voice note from Telegram to a unique local temp file.
        """
        message = update.message
        voice = message.voice or message.audio
        
        if not voice:
            return None

        # Create a unique filename using timestamp and user ID
        user_id = update.effective_user.id
        timestamp = int(datetime.now().timestamp())
        temp_path = f"temp_{user_id}_{timestamp}.oga"

        # Download from Telegram
        new_file = await context.bot.get_file(voice.file_id)
        await new_file.download_to_drive(temp_path)
        
        return temp_path

    def _sync_transcribe(self, file_path: str):
        """
        Synchronous wrapper for the heavy Whisper CPU work.
        Includes hallucination filtering for common 'tiny' model artifacts.
        """
        try:
            logger.info(f"🎙️ [Whisper] Transcribing: {file_path}")

            # Senior Logic: Get actual duration using os.path.getsize as a proxy if ffmpeg is missing
            # or use a more reliable method if possible.
            try:
                file_size = os.path.getsize(file_path)
            except OSError:
                file_size = 0

            # Rough proxy: 1 second of .oga (Opus) is roughly 2-4 KB.
            # If > 10KB, it's likely > 3 seconds.
            is_long_audio = file_size > 10000

            result = self.model.transcribe(file_path, fp16=False)
            text = result.get("text", "").strip()

            # HEURISTIC_BLACKLIST: Whisper 'tiny' often outputs these on silence or static
            hallucinations = [
                "Thank you for watching",
                "Visit us",
                "Please subscribe",
                "Thanks for watching",
                "Subtitles by",
                "Amara.org",
                "you",
                ".",
                "Bye.",
                "Enjoy.",
                "God bless.",
                "Like and subscribe.",
                "Visit us, please",
                "Thank you for the support.",
                "The end.",
                "Subtitles by",
                "Thanks for watching"
            ]

            # 1. Exact or fuzzy matches for common hallucinations
            for h in hallucinations:
                if h.lower() in text.lower() and len(text) < len(h) + 15:
                    logger.warning(f"⚠️ Hallucination detected and filtered: '{text}'")
                    raise HallucinationError(f"Hallucination detected: {text}")

            # 2. Senior Logic: Common single-word verbs in longer audio are likely hallucinations
            common_verbs = ["you", "go", "is", "the", "and", "do", "get", "can"]
            words = text.split()
            if len(words) == 1 and words[0].lower().strip(".,!?") in common_verbs:
                if is_long_audio:
                    logger.warning(f"⚠️ Single-verb hallucination detected (Size: {file_size}): '{text}'")
                    raise HallucinationError(f"Single-verb hallucination detected: {text}")

            # 3. Check for extremely high repetition (e.g., "you you you you")
            words = text.split()
            if len(words) > 5 and len(set(words)) / len(words) < 0.3:
                logger.warning(f"⚠️ High repetition hallucination detected: '{text}'")
                raise HallucinationError(f"Repetitive hallucination detected: {text}")

            # 3. Short capture check
            if len(text.strip()) < 3:
                logger.info(f"🔈 Captured noise or too short: '{text}'")
                return ""

            return text
        except Exception as e:
            logger.error(f"❌ Whisper Error: {e}")
            return ""

    async def transcribe(self, file_path: str):
        """
        Async entry point for transcription. 
        Runs the CPU-heavy work in a thread to keep the bot responsive.
        """
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(self.executor, self._sync_transcribe, file_path)
        
        # Cleanup: Delete the temp file immediately after transcription
        self.cleanup(file_path)
        
        return text

    def cleanup(self, file_path: str):
        """Removes the temporary audio file."""
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"🧹 Cleaned up: {file_path}")