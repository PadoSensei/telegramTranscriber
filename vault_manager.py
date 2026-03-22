import os
import shutil
import tempfile
import logging
from git import Repo
from datetime import datetime
from templates import NoteTemplate

logger = logging.getLogger(__name__)

class VaultManager:
    def __init__(self, repo_url, token, username):
        self.auth_url = repo_url.replace("https://", f"https://{username}:{token}@")
        self.username = username

    def push_to_obsidian(self, project, clean_transcript, analysis_output):
        tmp_dir = tempfile.mkdtemp()
        try:
            # 1. Clone
            repo = Repo.clone_from(self.auth_url, tmp_dir, depth=1)
            
            # 2. Setup Path
            target_folder = os.path.join(tmp_dir, "01_Projects", project, "📥 TelegramCaptures")
            os.makedirs(target_folder, exist_ok=True)
            
            filename = f"{datetime.now().strftime('%Y-%m-%d')}.md"
            file_path = os.path.join(target_folder, filename)

            # 3. Format & Write
            is_new_file = not os.path.exists(file_path)
            entry_content = NoteTemplate.format_entry(clean_transcript, analysis_output)
            
            with open(file_path, "a", encoding="utf-8") as f:
                if is_new_file:
                    f.write(NoteTemplate.get_daily_header(project))
                f.write(entry_content)

            # 4. Git Push
            repo.index.add([file_path])
            repo.index.commit(f"New capture for {project}")
            repo.remote(name='origin').push()
            return True

        except Exception as e:
            logger.error(f"Vault Sync Error: {e}")
            return False
        finally:
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir)