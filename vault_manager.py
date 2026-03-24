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
        """
        Initializes the manager with user-specific credentials.
        Constructs an authenticated URL for Git operations.
        """
        # Inject the token into the URL for HTTPS authentication
        self.auth_url = repo_url.replace("https://", f"https://{username}:{token}@")
        self.username = username

    def push_to_obsidian(self, category, project, clean_transcript, analysis_output):
        """
        Clones the user's vault, appends the note to the correct project folder,
        and pushes the changes back to GitHub.
        """
        tmp_dir = tempfile.mkdtemp()
        try:
            # 1. Shallow clone for speed (only the latest commit)
            logger.info(f"Cloning vault for user {self.username}...")
            repo = Repo.clone_from(self.auth_url, tmp_dir, depth=1)
            
            # 2. Determine target folder path based on Category and Project
            # Logic: If category is '00_Inbox', project name is omitted from path.
            if category == "00_Inbox":
                target_folder = os.path.join(tmp_dir, "00_Inbox", "📥 TelegramCaptures")
            else:
                target_folder = os.path.join(tmp_dir, category, project, "📥 TelegramCaptures")
            
            # Ensure the folder structure exists
            os.makedirs(target_folder, exist_ok=True)
            
            # 3. Prepare the daily note file
            filename = f"{datetime.now().strftime('%Y-%m-%d')}.md"
            file_path = os.path.join(target_folder, filename)
            
            # Check if this is a brand new file for the day
            is_new_file = not os.path.exists(file_path)
            
            # Get formatted content from templates
            entry_content = NoteTemplate.format_entry(clean_transcript, analysis_output)
            
            # 4. Write/Append to file
            with open(file_path, "a", encoding="utf-8") as f:
                if is_new_file:
                    # Write the YAML frontmatter and daily header if it's a new file
                    f.write(NoteTemplate.get_daily_header(project))
                f.write(entry_content)

            # 5. Git Commit & Push
            repo.index.add([file_path])
            commit_msg = f"Capture: {project} at {datetime.now().strftime('%H:%M')}"
            repo.index.commit(commit_msg)
            
            logger.info(f"Pushing update to GitHub: {commit_msg}")
            repo.remote(name='origin').push()
            
            return True

        except Exception as e:
            logger.error(f"Vault Sync Error: {e}")
            return False
            
        finally:
            # Always clean up the temporary directory to save server space
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir)
                logger.info("Temporary workspace cleaned.")