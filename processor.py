import os
import logging
import asyncio
from vault_manager import VaultManager
from google_manager import GoogleManager
from ai_engine import AIEngine
from config import VAULT_CONFIGS

logger = logging.getLogger(__name__)

class TaskProcessor:
    def __init__(self):
        self.ai = AIEngine()
        self.google = GoogleManager()

    async def run_sync_stack(self, user_id, category, project, text, user_name):
        """
        Coordinates AI transformation and parallel persistence.
        GitHub is mandatory. Google is optional based on user config.
        """
        user_cfg = VAULT_CONFIGS.get(user_id)
        if not user_cfg:
            logger.error(f"❌ User {user_id} not found in VAULT_CONFIGS")
            return None, None, False

        # Determine if we should use STAR story prompt
        is_star = "Star" in category or "STAR_Story_Bank" in category
        
        # 1. AI Transformation (Gemini 2.0 Flash)
        clean_text, analysis = self.ai.get_structured_output(text, user_name, is_star)
        
        # 2. Setup Persistence Tasks
        vault = VaultManager(user_cfg["repo_url"], user_cfg["token"], user_cfg["username"])
        
        # Check if this specific user has a Google Doc assigned (e.g., Katie=Yes, Paddy=No)
        has_google = user_cfg.get("gdrive_doc_id") is not None
        
        loop = asyncio.get_running_loop()
        
        # Start with GitHub (Always required)
        tasks = [
            loop.run_in_executor(None, vault.push_to_obsidian, category, project, clean_text, analysis)
        ]

        # Add Google Sync ONLY if the user has a configured Doc ID
        if has_google:
            logger.info(f"🔗 Google Sync enabled for {user_name}")
            tasks.append(self.google.sync_to_doc(user_cfg, project, clean_text, analysis))
        else:
            logger.info(f"⏭️ Skipping Google Sync for {user_name} (No Doc ID)")

        try:
            # Run tasks in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # evaluate GitHub Success
            git_success = results[0] is True
            
            # evaluate Google Success (if not configued, default to True so it doesn't block)
            google_success = True
            if has_google:
                google_success = results[1] is True
            
            return clean_text, analysis, (git_success and google_success)
            
        except Exception as e:
            logger.error(f"❌ Critical error in sync stack for {user_name}: {e}")
            return clean_text, analysis, False