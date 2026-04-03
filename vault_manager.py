import os
import logging
from datetime import datetime
from git import Repo
from templates import NoteTemplate

logger = logging.getLogger(__name__)

class VaultManager:
    def __init__(self, repo_url, token, username):
        self.repo_url = repo_url
        self.token = token
        self.username = username
        self.temp_dir = f"temp_vault_{username}"
        
        # Format URL with token for authentication
        self.auth_url = self.repo_url.replace("https://", f"https://{username}:{token}@")

    def push_to_obsidian(self, target_category, target_project, clean_transcript, analysis_output):
        """
        Clones, updates, and pushes a Markdown entry to the specific GitHub vault.
        """
        try:
            logger.info(f"Cloning vault for user {self.username}...")
            if os.path.exists(self.temp_dir):
                import shutil
                shutil.rmtree(self.temp_dir)

            repo = Repo.clone_from(self.auth_url, self.temp_dir)
            
            # Ensure the target directory exists in the vault
            full_folder_path = os.path.join(self.temp_dir, target_category)
            os.makedirs(full_folder_path, exist_ok=True)

            # Create file name based on date (Obsidian Daily Note style)
            date_str = datetime.now().strftime('%Y-%m-%d')
            file_name = f"{date_str}.md"
            file_path = os.path.join(full_folder_path, file_name)

            # --- SENIOR LOGIC: Formatting ---
            # Check if this is a STAR story to set the correct icon in Obsidian
            is_star = "STAR_Story_Bank" in target_category

            # Ensure the note exists and has frontmatter
            if not os.path.exists(file_path):
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(NoteTemplate.get_frontmatter(target_project, self.username))

            # Append the formatted entry (using callouts for high-readability)
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(NoteTemplate.format_entry(clean_transcript, analysis_output, is_star=is_star))

            # Git Push sequence
            repo.git.add(A=True)
            repo.index.commit(f"New capture via 2ndBrain Bot: {target_project}")
            origin = repo.remote(name='origin')
            origin.push()
            
            logger.info(f"✅ Successfully pushed to GitHub for {self.username}")
            return True

        except Exception as e:
            logger.error(f"Vault Sync Error: {e}")
            return False
        finally:
            # Cleanup temp folder to prevent Railway disk saturation
            if os.path.exists(self.temp_dir):
                import shutil
                shutil.rmtree(self.temp_dir)
                logger.info("Temporary workspace cleaned.")