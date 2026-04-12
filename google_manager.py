import os
import logging
import json
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

class GoogleManager:
    def __init__(self, gcp_json_content=None):
        self.gcp_json_content = gcp_json_content
        self.scopes = ['https://www.googleapis.com/auth/documents']

    def _get_service(self):
        """
        Internal helper to build the Google Docs service.
        Prioritizes provided gcp_json_content (Per-User) over global Env Var.
        """
        try:
            # 1. Try to load from provided JSON content (Per-User Isolation)
            raw_json = self.gcp_json_content or os.getenv("GCP_JSON_CONTENT")
            if raw_json:
                logger.info("🔐 Authenticating via Google Service Account JSON")
                info = json.loads(raw_json)
                creds = service_account.Credentials.from_service_account_info(
                    info, scopes=self.scopes
                )
                return build('docs', 'v1', credentials=creds)

            # 2. Fallback to local JSON file (Local Dev Mode)
            creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if creds_path and os.path.exists(creds_path):
                logger.info(f"📂 Authenticating via local file: {creds_path}")
                creds = service_account.Credentials.from_service_account_file(
                    creds_path, scopes=self.scopes
                )
                return build('docs', 'v1', credentials=creds)

            logger.error("❌ No Google Credentials found.")
            return None

        except Exception as e:
            logger.error(f"❌ Failed to initialize Google Docs Service: {e}")
            return None

    async def sync_to_doc(self, doc_id, title, content, analysis, user_name="Unknown"):
        """Appends formatted STAR stories or research to a Google Doc."""
        if not doc_id:
            return False

        try:
            service = self._get_service()
            if not service: 
                return False

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

            # Batch update for reliable appending
            service.documents().batchUpdate(
                documentId=doc_id, 
                body={'requests': requests}
            ).execute()
            
            logger.info(f"✅ Google Doc {doc_id} updated for {user_name}")
            return True

        except Exception as e:
            logger.error(f"❌ Google Docs Sync Error: {e}")
            return False