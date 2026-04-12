import json
import os
import logging
import fasteners
import datetime
import time

logger = logging.getLogger(__name__)

class StateManager:
    def __init__(self, filepath="bot_state.json"):
        self.filepath = filepath
        self.lock_path = f"{filepath}.lock"
        self.lock = fasteners.InterProcessLock(self.lock_path)

    def _load_state(self):
        with self.lock:
            if os.path.exists(self.filepath):
                try:
                    with open(self.filepath, 'r') as f:
                        return json.load(f)
                except Exception as e:
                    logger.error(f"Error loading state: {e}")
            return {}

    def _save_state(self, state):
        with self.lock:
            try:
                # Write to temp file first then rename for atomicity
                temp_file = f"{self.filepath}.tmp"
                with open(temp_file, 'w') as f:
                    json.dump(state, f)
                os.replace(temp_file, self.filepath)
            except Exception as e:
                logger.error(f"Error saving state: {e}")

    def get_transcript(self, user_id):
        state = self._load_state()
        user_data = state.get(str(user_id), {})
        if isinstance(user_data, str): # Migration for old state format
            return user_data
        return user_data.get("last_transcript")

    def set_transcript(self, user_id, transcript):
        state = self._load_state()
        user_id_str = str(user_id)
        if user_id_str not in state or isinstance(state[user_id_str], str):
            state[user_id_str] = {}
        state[user_id_str]["last_transcript"] = transcript
        state[user_id_str]["transcript_ts"] = int(datetime.datetime.now().timestamp())
        self._save_state(state)

    def clear_transcript(self, user_id):
        state = self._load_state()
        user_id_str = str(user_id)
        if user_id_str in state:
            if isinstance(state[user_id_str], dict):
                state[user_id_str]["last_transcript"] = None
            else:
                del state[user_id_str]
            self._save_state(state)

    def set_pending_tag(self, user_id, tag):
        state = self._load_state()
        user_id_str = str(user_id)
        if user_id_str not in state or isinstance(state[user_id_str], str):
            state[user_id_str] = {}
        state[user_id_str]["pending_tag"] = tag
        state[user_id_str]["tag_ts"] = int(datetime.datetime.now().timestamp())
        self._save_state(state)

    def get_pending_tag(self, user_id):
        state = self._load_state()
        user_data = state.get(str(user_id), {})
        if not isinstance(user_data, dict):
            return None

        tag = user_data.get("pending_tag")
        ts = user_data.get("tag_ts", 0)

        # 10 minute expiry (600 seconds)
        if tag and (time.time() - ts > 600):
            logger.info(f"⏳ Pending tag {tag} expired for user {user_id}")
            return None

        return tag

    def clear_pending_tag(self, user_id):
        state = self._load_state()
        user_id_str = str(user_id)
        if user_id_str in state and isinstance(state[user_id_str], dict):
            state[user_id_str]["pending_tag"] = None
            self._save_state(state)

    def set_discovered_folders(self, username, folders):
        state = self._load_state()
        if "discovery" not in state:
            state["discovery"] = {}
        state["discovery"][username] = folders
        self._save_state(state)

    def get_discovered_folders(self, username):
        state = self._load_state()
        return state.get("discovery", {}).get(username, [])
