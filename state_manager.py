import json
import os
import logging
import fasteners

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
        return state.get(str(user_id))

    def set_transcript(self, user_id, transcript):
        state = self._load_state()
        state[str(user_id)] = transcript
        self._save_state(state)

    def clear_transcript(self, user_id):
        state = self._load_state()
        if str(user_id) in state:
            del state[str(user_id)]
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
