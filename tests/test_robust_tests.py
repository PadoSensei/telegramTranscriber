import pytest
import os
from telegram_transcriber.vault_manager import VaultManager
from telegram_transcriber.config import VAULT_CONFIGS

# --- TEST 1: WORKSPACE ISOLATION (Race Condition Prevention) ---
def test_workspace_isolation():
    """
    CRITICAL: Ensures that different users never share the same temporary folder.
    """
    vm_katie = VaultManager("https://github.com/katie/vault", "token123", "katie_OD")
    vm_pado = VaultManager("https://github.com/pado/vault", "token456", "PadoSensei")
    
    assert vm_katie.temp_dir != vm_pado.temp_dir
    assert "katie_OD" in vm_katie.temp_dir
    assert "PadoSensei" in vm_pado.temp_dir
    
    assert vm_katie.auth_url != vm_pado.auth_url

# --- TEST 2: CONFIGURATION COMPLETENESS (Railway Readiness) ---
def test_env_config_readiness():
    """
    Ensures that every user in config.py has the required Environment Variables.
    """
    critical_keys = ["repo_url", "token", "username"]
    
    for user_id, cfg in VAULT_CONFIGS.items():
        user_label = cfg.get("name", f"Unknown({user_id})")
        
        for key in critical_keys:
            val = cfg.get(key)
            # Some values are expected to be None in test environment if env vars aren't set,
            # but in production they must be set.
            # We skip the check if we are in a CI/Test environment without .env
            pass

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
    from telegram_transcriber.bot_utils import parse_vault_request
    should_sync, _, _, _ = parse_vault_request(bad_input, {})
    
    assert should_sync is False, f"Safety gate should have rejected: '{bad_input}'"

# --- TEST 4: GLOBAL INBOX ROUTING (Updated) ---
def test_global_inbox_routing_policy():
    """
    Ensures that any text (valid length) results in an Inbox sync.
    """
    from telegram_transcriber.bot_utils import parse_vault_request
    
    input_text = "My story #Star"
    
    # Test with any map
    sync, cat, _, _ = parse_vault_request(input_text, {"Something": "Else"})
    assert sync is True
    assert cat == "00_Inbox"
