import os
import json
import time
from state_manager import StateManager

def test_bidirectional_cache():
    sm = StateManager("test_state.json")
    user_id = 12345

    # Test Priming (Tag before audio)
    sm.set_pending_tag(user_id, "#star")
    tag = sm.get_pending_tag(user_id)
    print(f"Primed tag: {tag}")
    assert tag == "#star"

    # Test Expiry
    # Manually modify state for testing expiry
    with sm.lock:
        with open("test_state.json", 'r') as f:
            state = json.load(f)
        state[str(user_id)]["tag_ts"] = time.time() - 700 # 700 seconds ago
        with open("test_state.json", 'w') as f:
            json.dump(state, f)

    expired_tag = sm.get_pending_tag(user_id)
    print(f"Expired tag (should be None): {expired_tag}")
    assert expired_tag is None

    # Test Transcription Save/Load
    sm.set_transcript(user_id, "Hello world")
    transcript = sm.get_transcript(user_id)
    print(f"Transcript: {transcript}")
    assert transcript == "Hello world"

    # Cleanup
    if os.path.exists("test_state.json"):
        os.remove("test_state.json")
    if os.path.exists("test_state.json.lock"):
        os.remove("test_state.json.lock")
    print("✅ Bidirectional Cache Tests Passed!")

if __name__ == "__main__":
    test_bidirectional_cache()
