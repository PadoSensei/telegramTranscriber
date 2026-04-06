import pytest
from bot_utils import parse_vault_request
from config import VAULT_CONFIGS

# Define constants for easier reading
LUDMILA_ID = 7187182620
PADO_ID = 6426489405
KATIE_ID = 8630747869

@pytest.mark.parametrize("user_id, input_text, expected_path", [
    # --- LUDMILA TESTS (Updated to match 03_Projects nested structure) ---
    (LUDMILA_ID, "Notes on #Zil project", "03_Projects/Zil/📥 TelegramCaptures"),
    (LUDMILA_ID, "Update for #Feena", "03_Projects/Feena/📥 TelegramCaptures"),
    (LUDMILA_ID, "No hashtag here", "00_Inbox"), 

    # --- PADOSENSEI TESTS ---
    (PADO_ID, "Training session #BJJDev", "03_Projects"),
    (PADO_ID, "Learning FastAPI #ScrimbaBackendCourse", "01_Study"),
    (PADO_ID, "Stock market thoughts #Investing", "02_Money"),
    (PADO_ID, "New drone logic #DroneDev", "03_Projects"),

    # --- KATIE TESTS ---
    (KATIE_ID, "My interview story about leadership #Star", "01_Projects/Bloom_Prep/STAR_Story_Bank"),
    (KATIE_ID, "General #Bloom notes", "01_Projects/Bloom_Prep"),
    (KATIE_ID, "PDF source for #Source", "01_Projects/Bloom_Prep/NotebookLM_Sources"),
    (KATIE_ID, "Daily check-in #Progress", "Progress_Summaries"),
    (KATIE_ID, "Random thought", "00_Inbox"), 
])

def test_multi_user_routing(user_id, input_text, expected_path):
    """
    Validates that each user's hashtags map to their unique folder structures.
    """
    user_cfg = VAULT_CONFIGS.get(user_id)
    assert user_cfg is not None, f"User ID {user_id} not found in config.py"

    # 1. Run the parser logic
    should_sync, target_cat, target_proj, _ = parse_vault_request(
        input_text, 
        user_cfg["category_map"]
    )

    # 2. Mimic the 'Senior Move' logic from main.py 
    # (If no hashtag matches, force to 00_Inbox)
    actual_path = target_cat if should_sync else "00_Inbox"

    # 3. Assertions
    assert actual_path == expected_path, (
        f"FAILED: User {user_cfg['name']} | Input: '{input_text}' | "
        f"Expected: {expected_path} | Got: {actual_path}"
    )

@pytest.mark.parametrize("user_id, input_text, expected_google_trigger", [
    # Ludmila and Pado should NEVER trigger Google Doc sync (no GDrive ID in config)
    (LUDMILA_ID, "Note #Zil", False),
    (PADO_ID, "Note #BJJDev", False),
    
    # Katie should trigger for Bloom-related prep tags
    (KATIE_ID, "Interview prep #Star", True),
    (KATIE_ID, "Context for #Bloom", True),
    (KATIE_ID, "New material #Source", True),
    (KATIE_ID, "Weekly #Progress", True),
    
    # Katie should NOT trigger Google Sync for random Inbox items to save quota
    (KATIE_ID, "Just a grocery list #Inbox", False),
    (KATIE_ID, "Random untagged thought", False),
])
def test_google_doc_trigger_flow(user_id, input_text, expected_google_trigger):
    """
    Ensures the 'NotebookLM Bridge' (Google Doc Sync) only triggers for 
    authorized users with specific high-value tags.
    """
    user_cfg = VAULT_CONFIGS.get(user_id)
    
    # Check 1: Does the user even have a Google Drive destination?
    has_gdrive = "gdrive_doc_id" in user_cfg
    
    # Check 2: Does the content contain a "Bloom Bridge" hashtag?
    # These are the tags Katie uses to feed NotebookLM
    bloom_bridge_tags = ["#star", "#bloom", "#source", "#progress"]
    has_bridge_tag = any(tag in input_text.lower() for tag in bloom_bridge_tags)
    
    # The condition used in processor.py
    should_trigger_google = has_gdrive and has_bridge_tag
    
    assert should_trigger_google == expected_google_trigger

def test_config_integrity():
    """
    Ensures no two users share the same GitHub Repository (if isolation is required)
    and that all users have the minimum required fields.
    """
    repo_urls = []
    for user_id, cfg in VAULT_CONFIGS.items():
        # Check for essential keys
        assert "category_map" in cfg
        assert "username" in cfg
        assert "name" in cfg
        
        # Check if Katie specifically has her GDrive ID
        if cfg["name"] == "katie_OD":
            assert "gdrive_doc_id" in cfg
            
        repo_urls.append(cfg["repo_url"])

    # Optional: Alert if everyone is using the same repo (unless intended)
    if len(repo_urls) != len(set(repo_urls)):
        print("\nNote: Some users share the same GitHub Repository URL.")

def test_hashtag_case_insensitivity():
    """
    Ensure that #STAR works exactly like #star.
    """
    katie_cfg = VAULT_CONFIGS[KATIE_ID]
    should_sync, target_cat, _, _ = parse_vault_request("#STAR", katie_cfg["category_map"])
    
    assert should_sync is True
    assert target_cat == "01_Projects/Bloom_Prep/STAR_Story_Bank"

def test_follow_up_hashtag_logic():
    """
    Simulates: 
    1. User sends voice (transcribed as 'Hello World')
    2. User sends '#star' immediately after
    """
    # Simulate Step 1: Voice Note arrives
    mock_transcription = "This is my leadership story about a difficult project."
    user_id = 8630747869 # Katie
    
    # We manually simulate the cache update that happens in main.py
    TRANSCRIPTION_CACHE = {user_id: mock_transcription}
    
    # Simulate Step 2: The follow-up text message
    incoming_text = "#Star"
    
    # Logic check: If message is just a hashtag, combine it with cache
    if incoming_text.startswith("#") and len(incoming_text.split()) == 1:
        final_content = f"{TRANSCRIPTION_CACHE[user_id]} {incoming_text}"
    else:
        final_content = incoming_text
        
    # Verify the combined content now triggers the correct routing
    katie_cfg = VAULT_CONFIGS[user_id]
    should_sync, target_cat, target_proj, _ = parse_vault_request(
        final_content, 
        katie_cfg["category_map"]
    )
    
    assert "#Star" in final_content
    assert target_cat == "01_Projects/Bloom_Prep/STAR_Story_Bank"
    assert should_sync is True