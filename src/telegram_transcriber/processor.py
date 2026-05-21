# processor.py
import os
import logging
import asyncio
from .vault_manager import VaultManager
from .ai_engine import AIEngine
from .templates import MediaTemplate, NoteTemplate
from .bot_utils import validate_media_file
from .exceptions import MediaIngestionError, TelegramDownloadError, GitPersistenceError

logger = logging.getLogger(__name__)

class TaskProcessor:
    def __init__(self):
        self.ai = AIEngine(api_key=os.getenv("GEMINI_API_KEY"))

    async def ingest_single_media(self, user_cfg, file_info: dict, file_id: str, context, status_msg=None) -> str:
        """
        Downloads a single media file from Telegram and secures it in the vault.
        """
        user_name = user_cfg.name
        logger.info(f"📥 [USER:{user_name}] Downloading media: {file_info['original_name']}")

        loop = asyncio.get_running_loop()

        # 1. Download from Telegram
        try:
            file = await context.bot.get_file(file_id)
            content = await file.download_as_bytearray()
        except Exception as e:
            logger.error(f"❌ [USER:{user_name}] Telegram download failed: {e}", exc_info=True)
            raise TelegramDownloadError(f"Failed to download your file from Telegram: {str(e)}")

        # Update status to "Securing"
        if status_msg:
            try:
                await status_msg.edit_text(f"📦 Securing '{file_info['original_name']}' to Vault...")
            except Exception as e:
                logger.warning(f"Failed to update status message to 'Securing': {e}")

        # 2. Generate Metadata
        metadata = MediaTemplate.get_metadata_content(
            filename=file_info['file_name'],
            original_name=file_info['original_name'],
            mime_type=file_info['mime_type'],
            file_size=file_info['file_size'],
            caption=file_info.get('caption'),
            timestamp=file_info['timestamp']
        )

        # 3. Persist to Vault
        vault = VaultManager(user_cfg.repo_url, user_cfg.token, user_cfg.username)

        # Offload heavy Git IO to executor
        try:
            saved_path = await loop.run_in_executor(
                None,
                vault.secure_media,
                file_info['file_name'],
                bytes(content),
                metadata
            )
        except GitPersistenceError:
            raise
        except Exception as e:
            logger.error(f"❌ [USER:{user_name}] Persistence failed: {e}", exc_info=True)
            raise GitPersistenceError(f"Failed to secure media in vault: {str(e)}")

        return saved_path

    async def ingest_media_group(self, user_cfg, updates: list, context) -> dict:
        """
        Orchestrates processing for a group of media files.
        """
        user_name = user_cfg.name
        logger.info(f"📦 [USER:{user_name}] Processing media group ({len(updates)} items)")

        results = {
            'total_files': len(updates),
            'succeeded': 0,
            'failed': 0,
            'failed_details': [],
            'saved_files': []
        }

        for update in updates:
            is_valid, file_info, error_message = validate_media_file(update.message)

            if not is_valid:
                logger.warning(f"❌ Validation failed for a file in group: {error_message}")
                results['failed'] += 1
                fname = "Unknown"
                if update.message.document: fname = update.message.document.file_name
                elif update.message.video: fname = update.message.video.file_name
                results['failed_details'].append({'filename': fname, 'reason': error_message})
                continue

            file_info['caption'] = update.message.caption

            try:
                saved_path = await self.ingest_single_media(user_cfg, file_info, file_info['file_id'], context)
                results['succeeded'] += 1
                results['saved_files'].append(file_info['original_name'])
            except Exception as e:
                logger.error(f"❌ Failed to ingest group item {file_info['original_name']}: {e}")
                results['failed'] += 1
                results['failed_details'].append({'filename': file_info['original_name'], 'reason': str(e)})

        return results

    async def run_sync_stack(self, user_cfg, text, input_type="voice"):
        """
        Coordinates AI transformation and persistence to Obsidian Inbox.
        """
        user_name = user_cfg.name
        logger.info(f"🔄 [USER:{user_name}] Starting sync stack (Type: {input_type})")

        # 1. AI Transformation
        clean_text, analysis = await self.ai.get_structured_output(text)
        
        # 2. Entry Formatting
        entry = NoteTemplate.format_entry(clean_text, analysis, input_type=input_type)

        # 3. Vault Persistence
        vault = VaultManager(user_cfg.repo_url, user_cfg.token, user_cfg.username)
        loop = asyncio.get_running_loop()
        
        git_success = await loop.run_in_executor(None, vault.push_to_obsidian, entry, input_type)

        return clean_text, analysis, git_success
