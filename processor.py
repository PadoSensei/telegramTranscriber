import os
import logging
import asyncio
from vault_manager import VaultManager
from google_manager import GoogleManager
from ai_engine import AIEngine
from templates import MediaTemplate
from bot_utils import validate_media_file
from exceptions import MediaIngestionError, TelegramDownloadError, GitPersistenceError

logger = logging.getLogger(__name__)

class TaskProcessor:
    def __init__(self):
        # AI Engine can be shared as it's typically a thread-safe client or stateless
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

        # Optional: Update status to "Securing" for visibility
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
            # 1. Validate each file in the group
            is_valid, file_info, error_message = validate_media_file(update.message)

            if not is_valid:
                logger.warning(f"❌ Validation failed for a file in group: {error_message}")
                results['failed'] += 1
                # Try to get a filename for the failure report
                fname = "Unknown"
                if update.message.document: fname = update.message.document.file_name
                elif update.message.video: fname = update.message.video.file_name
                results['failed_details'].append({'filename': fname, 'reason': error_message})
                continue

            # Add caption if present
            file_info['caption'] = update.message.caption

            # 2. Ingest
            try:
                # We don't pass status_msg to group ingestion items to avoid message editing spam/conflicts
                # unless we want to update the group message with "Securing item X of Y"
                saved_path = await self.ingest_single_media(user_cfg, file_info, file_info['file_id'], context)
                results['succeeded'] += 1
                results['saved_files'].append(file_info['original_name'])
            except Exception as e:
                logger.error(f"❌ Failed to ingest group item {file_info['original_name']}: {e}")
                results['failed'] += 1
                results['failed_details'].append({'filename': file_info['original_name'], 'reason': str(e)})

        return results

    async def run_sync_stack(self, user_cfg, category, project, text):
        """
        Coordinates AI transformation and parallel persistence.
        Ensures absolute tenant isolation by instantiating Managers locally.
        """
        user_name = user_cfg.name
        logger.info(f"🔄 [USER:{user_name}] Starting sync stack for project: {project}")

        # Determine if we should use STAR story prompt
        is_star = "Star" in category or "STAR_Story_Bank" in category
        
        # 1. AI Transformation (Gemini 2.0 Flash)
        clean_text, analysis = await self.ai.get_structured_output(text, user_name, is_star)
        
        # 2. Local Service Instantiation (Isolated per request - Factory Pattern)
        # These are local variables, ensuring they are not shared between concurrent requests.
        vault = VaultManager(user_cfg.repo_url, user_cfg.token, user_cfg.username)
        google = GoogleManager(gcp_json_content=user_cfg.gcp_json_content)

        # 3. Setup Persistence Tasks
        has_google = user_cfg.gdrive_doc_id is not None
        loop = asyncio.get_running_loop()
        
        # Start GitHub sync (Always required)
        git_task = loop.run_in_executor(None, vault.push_to_obsidian, category, project, clean_text, analysis)

        # Start Google sync (Optional)
        google_task = None
        if has_google:
            logger.info(f"🔗 Google Sync enabled for {user_name}")
            google_task = google.sync_to_doc(user_cfg.gdrive_doc_id, project, clean_text, analysis, user_name)
        else:
            logger.info(f"⏭️ Skipping Google Sync for {user_name} (No Doc ID)")

        # 4. Parallel Sync Execution
        tasks = [git_task]
        if google_task:
            tasks.append(google_task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 5. Independent Success Evaluation
        git_success = False
        google_success = True # Default to True if not configured

        # Evaluate Git Result (always index 0)
        if isinstance(results[0], Exception):
            logger.error(f"❌ GitHub Sync error for {user_name}: {results[0]}")
        else:
            git_success = results[0]

        # Evaluate Google Result (index 1 if exists)
        if google_task:
            if isinstance(results[1], Exception):
                logger.error(f"❌ Google Sync error for {user_name}: {results[1]}")
                google_success = False
            else:
                google_success = results[1]

        return clean_text, analysis, git_success, google_success
