import os
import logging
import shutil
import git.exc
from datetime import datetime
from git import Repo
from .templates import NoteTemplate
from .exceptions import GitPersistenceError

# Standardize logger to match the main orchestrator
logger = logging.getLogger("2ndBrain.VaultManager")

class VaultManager:
    def __init__(self, repo_url, token, username):
        """
        Manages individual GitHub repositories for Multi-Tenant users.
        """
        self.repo_url = repo_url
        self.token = token
        self.username = username
        # Unique temp directory per user to avoid collision during parallel processing
        self.temp_dir = f"temp_vault_{username}_{datetime.now().strftime('%H%M%S%f')}"
        
        # Format URL with token for silent HTTPS authentication
        self.auth_url = self.repo_url.replace("https://", f"https://{username}:{token}@")

    def secure_media(self, filename: str, media_content_bytes: bytes, metadata_content: str) -> str:
        """
        Atomically clones the vault, writes a binary media file and its companion .md metadata,
        and pushes the changes to GitHub.
        Returns the relative path of the saved media file.
        """
        try:
            logger.info(f"[USER:{self.username}] Starting secure_media for: {filename}")

            # 1. CLEANUP/PREP
            if os.path.exists(self.temp_dir):
                try:
                    shutil.rmtree(self.temp_dir)
                except Exception as e:
                    logger.warning(f"[USER:{self.username}] Initial cleanup failed: {e}")

            # 2. CLONE
            logger.info(f"[USER:{self.username}] Cloning vault for media ingestion...")
            try:
                repo = Repo.clone_from(self.auth_url, self.temp_dir)
            except git.exc.GitCommandError as e:
                raise GitPersistenceError(f"Failed to clone repository: {str(e)}")

            # 3. DIRECTORY PREP (99_System/Attachments for media)
            target_category = "00_Inbox"
            attachment_dir = os.path.join(self.temp_dir, "99_System", "Attachments")
            inbox_dir = os.path.join(self.temp_dir, target_category)

            try:
                os.makedirs(attachment_dir, exist_ok=True)
                os.makedirs(inbox_dir, exist_ok=True)
            except OSError as e:
                raise GitPersistenceError(f"Failed to create directories: {str(e)}")

            # 4. WRITE BINARY FILE
            media_path = os.path.join(attachment_dir, filename)
            try:
                with open(media_path, 'wb') as f:
                    f.write(media_content_bytes)
            except IOError as e:
                raise GitPersistenceError(f"Failed to write media file: {str(e)}")

            # 5. WRITE METADATA FILE (in 00_Inbox)
            metadata_filename = f"{filename}.md"
            metadata_path = os.path.join(inbox_dir, metadata_filename)
            try:
                with open(metadata_path, 'w', encoding='utf-8') as f:
                    f.write(metadata_content)
            except IOError as e:
                raise GitPersistenceError(f"Failed to write metadata file: {str(e)}")

            # 6. COMMIT & PUSH
            try:
                repo.git.add(A=True)
                commit_msg = f"Media Ingest: {filename} via Knowledge Ingestion Engine"
                repo.index.commit(commit_msg)

                origin = repo.remote(name='origin')
                origin.push()
            except git.exc.GitCommandError as e:
                raise GitPersistenceError(f"Git operation failed: {str(e)}")

            relative_path = os.path.join("99_System", "Attachments", filename)
            logger.info(f"[USER:{self.username}] ✅ Media secured successfully: {relative_path}")
            return relative_path

        except GitPersistenceError:
            raise
        except Exception as e:
            logger.error(f"[USER:{self.username}] ❌ secure_media Unexpected Error: {str(e)}")
            raise GitPersistenceError(f"An unexpected error occurred during persistence: {str(e)}")
        finally:
            self._cleanup()

    def push_to_obsidian(self, entry, input_type="voice"):
        """
        Clones, updates, and pushes a Markdown entry to the 00_Inbox/YYYY-MM-DD.md file.
        """
        try:
            logger.info(f"[USER:{self.username}] Starting vault sync to Inbox")
            
            # 1. CLEANUP PREVIOUS RUNS
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)

            # 2. CLONE
            logger.info(f"[USER:{self.username}] Cloning repository...")
            repo = Repo.clone_from(self.auth_url, self.temp_dir)
            
            # 3. PATH PREP
            target_category = "00_Inbox"
            full_folder_path = os.path.join(self.temp_dir, target_category)
            os.makedirs(full_folder_path, exist_ok=True)

            # 4. FILE PREPARATION
            date_str = datetime.now().strftime('%Y-%m-%d')
            file_name = f"{date_str}.md"
            file_path = os.path.join(full_folder_path, file_name)

            # 5. WRITE/APPEND LOGIC
            if not os.path.exists(file_path):
                logger.info(f"[USER:{self.username}] Creating new daily note: {file_name}")
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(NoteTemplate.get_frontmatter("Unsorted", self.username))

            # Append the new entry with double newline before to prevent formatting bleed
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write("\n\n" + entry)

            # 6. GIT PUSH
            repo.git.add(A=True)
            commit_msg = f"Capture: {input_type} via Knowledge Ingestion Engine"
            repo.index.commit(commit_msg)
            
            origin = repo.remote(name='origin')
            origin.push()
            
            logger.info(f"[USER:{self.username}] ✅ Successfully pushed to GitHub Inbox")
            return True

        except Exception as e:
            logger.error(f"[USER:{self.username}] ❌ Vault Sync Error: {str(e)}")
            return False
        finally:
            self._cleanup()

    def _cleanup(self):
        if os.path.exists(self.temp_dir):
                try:
                    shutil.rmtree(self.temp_dir)
                    logger.info(f"[USER:{self.username}] Temporary workspace cleaned.")
                except Exception as cleanup_error:
                    logger.error(f"Cleanup failed for {self.temp_dir}: {cleanup_error}")
