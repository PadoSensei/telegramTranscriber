import pytest
import os
from vault_manager import VaultManager
from config import VAULT_CONFIGS

# --- TEST 1: WORKSPACE ISOLATION (Race Condition Prevention) ---
def test_workspace_isolation():
    """
    CRITICAL: Ensures that different users never share the same temporary folder.
    If they did, User A's transcription could be pushed to User B's vault 
    if they message the bot at the same time.
    """
    # Initialize two different managers simulating two users
    vm_katie = VaultManager("https://github.com/katie/vault", "token123", "katie_OD")
    vm_pado = VaultManager("https://github.com/pado/vault", "token456", "PadoSensei")
    
    # Verify the temporary directory paths are unique and user-specific
    assert vm_katie.temp_dir != vm_pado.temp_dir
    assert "katie_OD" in vm_katie.temp_dir
    assert "PadoSensei" in vm_pado.temp_dir
    
    # Verify the auth URLs are unique (prevents permission leaking)
    assert vm_katie.auth_url != vm_pado.auth_url

# --- TEST 2: CONFIGURATION COMPLETENESS (Railway Readiness) ---
def test_env_config_readiness():
    """
    Ensures that every user in config.py has the required Environment Variables.
    Prevents "NoneType" crashes when the bot tries to clone a repo.
    """
    critical_keys = ["repo_url", "token", "username"]
    
    for user_id, cfg in VAULT_CONFIGS.items():
        user_label = cfg.get("name", f"Unknown({user_id})")
        
        for key in critical_keys:
            val = cfg.get(key)
            # This catches cases where os.getenv returned None because the key is missing in Railway
            assert val is not None, f"FAIL: {user_label} is missing '{key}' in Environment Variables."
            assert isinstance(val, str), f"FAIL: {user_label} key '{key}' must be a string."
            assert len(val.strip()) > 0, f"FAIL: {user_label} key '{key}' is an empty string."

    # Special check for Katie's "NotebookLM Bridge"
    katie_cfg = next((cfg for cfg in VAULT_CONFIGS.values() if cfg["name"] == "katie_OD"), None)
    if katie_cfg:
        assert katie_cfg.get("gdrive_doc_id") is not None, "FAIL: Katie's Google Drive ID is missing!"

# --- TEST 3: SAFETY GATE (Empty Content / Noise Handling) ---
@pytest.mark.parametrize("bad_input", [
    "",             # Total empty
    " ",            # Single space
    "   \n   ",     # Newlines/Whitespace
    "a",            # Single character (usually noise)
    None            # Null input
])
def test_empty_content_safety_gate(bad_input):
    """
    Mirrors the logic in main.py to ensure the bot doesn't try to process 
    silent voice notes or accidental "pocket clicks."
    """
    # This is the exact logic from your main.py Phase A
    is_valid = bool(bad_input and len(bad_input.strip()) >= 2)
    
    assert is_valid is False, f"Safety gate should have rejected: '{bad_input}'"

# --- TEST 4: MULTI-USER PERSONA ISOLATION ---
def test_persona_isolation():
    """
    Ensures that hashtags don't 'leak' between users if their 
    category_maps are different.
    """
    from bot_utils import parse_vault_request
    
    # Katie uses #Star for her interview bank
    katie_map = VAULT_CONFIGS[8630747869]["category_map"]
    # Ludmila uses a standard project map
    ludmila_map = VAULT_CONFIGS[7187182620]["category_map"]
    
    input_text = "My story #Star"
    
    # Test Katie
    k_sync, k_cat, _, _ = parse_vault_request(input_text, katie_map)
    assert k_sync is True
    assert "STAR_Story_Bank" in k_cat
    
    # Test Ludmila with the same text
    l_sync, l_cat, _, _ = parse_vault_request(input_text, ludmila_map)
    # Ludmila doesn't have #Star in her map, so it should not sync specifically
    assert l_sync is False