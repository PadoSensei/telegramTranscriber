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
        """Coordinates AI transformation and parallel persistence."""
        user_cfg = VAULT_CONFIGS.get(user_id)
        if not user_cfg:
            logger.error(f"❌ User {user_id} not found in VAULT_CONFIGS")
            return None, None, False

        is_star = (category == "STAR_Story_Bank")
        
        # 1. AI Transformation
        clean_text, analysis = self.ai.get_structured_output(text, user_name, is_star)
        
        # 2. Parallel Persistence
        vault = VaultManager(user_cfg["repo_url"], user_cfg["token"], user_cfg["username"])
        
        # Senior Move: Run GitHub (Threaded) and Google (Async) in parallel
        # We use a wrapper to ensure threaded calls return booleans
        loop = asyncio.get_running_loop()
        
        try:
            results = await asyncio.gather(
                loop.run_in_executor(None, vault.push_to_obsidian, category, project, clean_text, analysis),
                self.google.sync_to_doc(user_cfg, project, clean_text, analysis),
                return_exceptions=True
            )
            
            # Check for success (True) and filter out exceptions or None
            success = all(res is True for res in results)
            return clean_text, analysis, success
            
        except Exception as e:
            logger.error(f"❌ Critical error in sync stack: {e}")
            return clean_text, analysis, False