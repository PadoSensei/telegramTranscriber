import pytest
from telegram_transcriber.bot_utils import parse_vault_request
from telegram_transcriber.config import VAULT_CONFIGS

# Define constants for easier reading
LUDMILA_ID = 7187182620
PADO_ID = 6426489405
KATIE_ID = 8630747869

@pytest.mark.parametrize("user_id, input_text", [
    (LUDMILA_ID, "Notes on #Zil project"),
    (LUDMILA_ID, "Update for #Feena"),
    (LUDMILA_ID, "No hashtag here"),
    (PADO_ID, "Training session #BJJDev"),
    (KATIE_ID, "My interview story about leadership #Star"),
    (KATIE_ID, "General #Bloom notes"),
    (KATIE_ID, "Random thought"),
])

def test_global_inbox_routing(user_id, input_text):
    """
    Validates that EVERYTHING routes to 00_Inbox regardless of hashtags.
    """
    user_cfg = VAULT_CONFIGS.get(user_id)
    assert user_cfg is not None

    # 1. Run the parser logic
    should_sync, target_cat, target_proj, _ = parse_vault_request(
        input_text, 
        user_cfg.get("category_map", {})
    )

    # 2. Assertions
    assert should_sync is True
    assert target_cat == "00_Inbox"
    assert target_proj == "Inbox"

def test_config_integrity():
    """
    Ensures users have the minimum required fields.
    """
    for user_id, cfg in VAULT_CONFIGS.items():
        assert "username" in cfg
        assert "name" in cfg
        assert "repo_url" in cfg
        assert "token" in cfg
