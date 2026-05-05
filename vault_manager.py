import os
import logging
import shutil
import git.exc
from datetime import datetime
from git import Repo
from templates import NoteTemplate
from exceptions import GitPersistenceError

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
        # Add a short unique suffix to avoid collision in high-concurrency scenarios
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

            # 3. DIRECTORY PREP (Always 00_Inbox for now)
            target_category = "00_Inbox"
            full_folder_path = os.path.join(self.temp_dir, target_category)
            try:
                os.makedirs(full_folder_path, exist_ok=True)
            except OSError as e:
                raise GitPersistenceError(f"Failed to create directory: {str(e)}")

            # 4. WRITE BINARY FILE
            media_path = os.path.join(full_folder_path, filename)
            try:
                with open(media_path, 'wb') as f:
                    f.write(media_content_bytes)
            except IOError as e:
                raise GitPersistenceError(f"Failed to write media file: {str(e)}")

            # 5. WRITE METADATA FILE
            metadata_filename = f"{filename}.md"
            metadata_path = os.path.join(full_folder_path, metadata_filename)
            try:
                with open(metadata_path, 'w', encoding='utf-8') as f:
                    f.write(metadata_content)
            except IOError as e:
                raise GitPersistenceError(f"Failed to write metadata file: {str(e)}")

            # 6. DISCOVERY (Optional but kept for consistency)
            self._discover_new_folders(repo)

            # 7. COMMIT & PUSH
            try:
                repo.git.add(A=True)
                commit_msg = f"Media Ingest: {filename} via 2ndBrain Bot"
                repo.index.commit(commit_msg)

                origin = repo.remote(name='origin')
                origin.push()
            except git.exc.GitCommandError as e:
                raise GitPersistenceError(f"Git operation failed: {str(e)}")

            relative_path = os.path.join(target_category, filename)
            logger.info(f"[USER:{self.username}] ✅ Media secured successfully: {relative_path}")
            return relative_path

        except GitPersistenceError:
            raise # Re-raise our custom exception
        except Exception as e:
            logger.error(f"[USER:{self.username}] ❌ secure_media Unexpected Error: {str(e)}")
            raise GitPersistenceError(f"An unexpected error occurred during persistence: {str(e)}")
        finally:
            self._cleanup()

    def push_to_obsidian(self, target_category, target_project, clean_transcript, analysis_output):
        """
        Clones, verifies paths, updates, and pushes a Markdown entry to the specific GitHub vault.
        """
        try:
            logger.info(f"[USER:{self.username}] Starting vault sync for project: {target_project}")
            
            # 1. CLEANUP PREVIOUS RUNS: Ensure workspace is clear
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)

            # 2. CLONE: Pull the latest state from GitHub
            logger.info(f"[USER:{self.username}] Cloning repository...")
            repo = Repo.clone_from(self.auth_url, self.temp_dir)
            
            # 3. PATH RESILIENCY: Verify if the category folder exists in the actual vault
            # If Katie renamed '01_Interviews' to 'Work/Interviews' in Obsidian, 
            # os.path.exists will fail, and we fallback to '00_Inbox' to prevent breaking the structure.
            full_folder_path = os.path.join(self.temp_dir, target_category)
            
            if not os.path.isdir(full_folder_path):
                logger.warning(
                    f"[USER:{self.username}] PATH MISMATCH: Folder '{target_category}' not found in repo. "
                    f"Redirecting entry to '00_Inbox' to prevent lost data."
                )
                target_category = "00_Inbox"
                full_folder_path = os.path.join(self.temp_dir, target_category)

            # Ensure the directory exists (creates 00_Inbox if it was missing too)
            os.makedirs(full_folder_path, exist_ok=True)

            # 4. FILE PREPARATION: Obsidian Daily Note Style (YYYY-MM-DD.md)
            date_str = datetime.now().strftime('%Y-%m-%d')
            file_name = f"{date_str}.md"
            file_path = os.path.join(full_folder_path, file_name)

            # Determine if this is a STAR story for specialized formatting
            is_star = "STAR_Story_Bank" in target_category or "#star" in clean_transcript.lower()

            # 5. WRITE/APPEND LOGIC
            # If file doesn't exist, initialize it with Frontmatter
            if not os.path.exists(file_path):
                logger.info(f"[USER:{self.username}] Creating new daily note: {file_name}")
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(NoteTemplate.get_frontmatter(target_project, self.username))

            # Append the new entry
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(NoteTemplate.format_entry(clean_transcript, analysis_output, is_star=is_star))

            # 5.5 DISCOVERY MODE: Scan for new folders to suggest hashtags
            self._discover_new_folders(repo)

            # 6. GIT PUSH: Commit and sync back to GitHub
            repo.git.add(A=True)
            commit_msg = f"Capture: {target_project} via 2ndBrain Bot"
            repo.index.commit(commit_msg)
            
            origin = repo.remote(name='origin')
            origin.push()
            
            logger.info(f"[USER:{self.username}] ✅ Successfully pushed to GitHub (Path: {target_category})")
            return True

        except Exception as e:
            logger.error(f"[USER:{self.username}] ❌ Vault Sync Error: {str(e)}")
            return False
        finally:
            self._cleanup()

    def _discover_new_folders(self, repo):
        """
        Scans the repository for folders and suggests new hashtags if they aren't in mapping.
        """
        try:
            ignore_dirs = {'.git', '.obsidian', '.trash', 'attachments'}
            found_folders = []
            for root, dirs, files in os.walk(self.temp_dir):
                # Filter out hidden/ignored directories
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ignore_dirs]
                for d in dirs:
                    # We want the relative path from the repo root
                    rel_path = os.path.relpath(os.path.join(root, d), self.temp_dir)
                    found_folders.append(rel_path)

            # Internal mapping update: Update bot_state.json with discovered folders
            from state_manager import StateManager
            state = StateManager()
            state.set_discovered_folders(self.username, found_folders)

            logger.info(f"[USER:{self.username}] Discovery Mode found {len(found_folders)} folders. Mapping updated.")

        except Exception as e:
            logger.error(f"Discovery Mode failed: {e}")

    def _cleanup(self):
        # 7. FINAL CLEANUP: Critical for Railway to prevent "Disk Full" errors
        if os.path.exists(self.temp_dir):
                try:
                    shutil.rmtree(self.temp_dir)
                    logger.info(f"[USER:{self.username}] Temporary workspace cleaned.")
                except Exception as cleanup_error:
                    logger.error(f"Cleanup failed for {self.temp_dir}: {cleanup_error}")