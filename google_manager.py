import os
import logging
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

class GoogleManager:
    def __init__(self):
        self.creds_path = os.getenv("KATIE_OD_GOOGLE_DRIVE")
        self.scopes = ['https://www.googleapis.com/auth/documents']

    def _get_service(self):
        """Internal helper to build the Google Docs service."""
        if not self.creds_path or not os.path.exists(self.creds_path):
            logger.error("❌ Google Credentials file missing.")
            return None
            
        creds = service_account.Credentials.from_service_account_file(
            self.creds_path, scopes=self.scopes
        )
        return build('docs', 'v1', credentials=creds)

    async def sync_to_doc(self, user_cfg, title, content, analysis):
        """Appends formatted STAR stories or research to a Google Doc."""
        doc_id = user_cfg.get("gdrive_doc_id")
        if not doc_id:
            return False

        try:
            service = self._get_service()
            if not service: return False

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            # Formatting the NotebookLM-friendly entry
            entry_header = f"\n\n--- 🌟 NEW {title.upper()} ENTRY: {timestamp} ---\n"
            full_text = (
                f"{entry_header}\n"
                f"{content}\n\n"
                f"💡 ANALYSIS & ACTION ITEMS:\n{analysis}\n"
                f"{'='*40}\n"
            )

            requests = [{
                'insertText': {
                    'location': {'index': 1}, 
                    'text': full_text
                }
            }]

            # Batch update is faster and more reliable
            service.documents().batchUpdate(
                documentId=doc_id, 
                body={'requests': requests}
            ).execute()
            
            logger.info(f"✅ Google Doc {doc_id} updated for {user_cfg.get('name')}")
            return True

        except Exception as e:
            logger.error(f"❌ Google Docs Sync Error: {e}")
            return False