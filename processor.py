import os
import logging
import asyncio
from vault_manager import VaultManager
from google_manager import GoogleManager
from ai_engine import AIEngine
from templates import MediaTemplate

logger = logging.getLogger(__name__)

class TaskProcessor:
    def __init__(self):
        # AI Engine can be shared as it's typically a thread-safe client or stateless
        self.ai = AIEngine(api_key=os.getenv("GEMINI_API_KEY"))

    async def ingest_media(self, user_cfg, file_info: dict, file_id: str, context) -> str:
        """
        Downloads media from Telegram and secures it in the user's vault.
        """
        user_name = user_cfg.name
        loop = asyncio.get_running_loop()

        # 1. DOWNLOAD FROM TELEGRAM
        logger.info(f"[USER:{user_name}] Downloading media file: {file_info['original_name']}")
        file_obj = await context.bot.get_file(file_id)

        # Assume download_as_bytearray is synchronous or handle it properly
        # In python-telegram-bot v20+, it's an async method
        media_content_bytes = await file_obj.download_as_bytearray()

        # 2. GENERATE METADATA
        # Extract caption if present in file_info or elsewhere
        # (Assuming it's passed in file_info or we need to get it from context/update)
        caption = file_info.get("caption", "")

        metadata_content = MediaTemplate.get_metadata_content(
            filename=file_info['file_name'],
            original_name=file_info['original_name'],
            mime_type=file_info['mime_type'],
            file_size=file_info['file_size'],
            caption=caption,
            timestamp=file_info['timestamp']
        )

        # 3. SECURE IN VAULT (Offload to executor)
        vault = VaultManager(user_cfg.repo_url, user_cfg.token, user_cfg.username)

        await loop.run_in_executor(
            None,
            vault.secure_media,
            file_info['file_name'],
            media_content_bytes,
            metadata_content
        )

        return file_info['file_name']

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
