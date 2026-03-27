import pytest
from unittest.mock import MagicMock, AsyncMock
from main import parse_vault_request, process_media
from config import ALLOWED_IDS

# Dummy map to simulate a user's project structure for testing
TEST_USER_MAP = {
    "Feena": "01_Projects",
    "AISolutions": "01_Projects"
}

# --- 1. Test Hashtag Parsing ---
@pytest.mark.parametrize("text, expected_sync, expected_category, expected_project", [
    ("#2ndBrain #Feena", True, "01_Projects", "Feena"),
    ("#2ndBrain #AISolutions", True, "01_Projects", "AISolutions"),
    ("#2ndBrain", True, "00_Inbox", "00_Inbox"),
    ("#Feena", False, None, None),
    ("#2ndBrain #TypoProj", True, "00_Inbox", "00_Inbox"),
])
def test_hashtag_parsing(text, expected_sync, expected_category, expected_project):
    # Updated to pass TEST_USER_MAP and unpack 4 values
    should_sync, category, project, warning = parse_vault_request(text, TEST_USER_MAP)
    
    assert should_sync == expected_sync
    assert category == expected_category
    assert project == expected_project


# --- 2. Test the Bot Integration ---
@pytest.mark.asyncio
async def test_process_media_triggers_sync(mocker):
    # A. Create the Mock VaultManager Object
    mock_vault_obj = MagicMock()
    mock_vault_obj.push_to_obsidian = MagicMock(return_value=True)
    
    # B. Patch dependencies
    mocker.patch('main.get_vault_for_user', return_value=mock_vault_obj)
    mocker.patch('main.transcribe_sync', return_value="Raw Whisper Text")
    
    # We now expect ONE call to Gemini with a split-key in the response
    mock_ai_response = "Clean Transcript\n---ANALYSIS_SPLIT---\nAI Analysis"
    mocker.patch('main.call_gemini', return_value=mock_ai_response)

    # C. Mock Telegram Infrastructure
    mock_status_msg = AsyncMock()
    mock_status_msg.edit_text = AsyncMock()
    mock_status_msg.delete = AsyncMock()
    
    mock_context = MagicMock()
    mock_context.bot.send_message = AsyncMock(return_value=mock_status_msg)
    
    mock_file = AsyncMock()
    mock_file.download_to_drive = AsyncMock()
    mock_context.bot.get_file = AsyncMock(return_value=mock_file)

    # D. Mock the Update
    mock_update = MagicMock()
    mock_update.effective_user.id = ALLOWED_IDS[0] 
    mock_update.effective_chat.id = 12345
    mock_update.message.caption = "#2ndBrain #Feena"
    mock_update.message.from_user.first_name = "TestUser"
    mock_update.message.voice = MagicMock(file_id="v123", duration=10)
    mock_update.message.audio = None

    # E. RUN
    await process_media(mock_update, mock_context)

    # F. ASSERTIONS
    mock_vault_obj.push_to_obsidian.assert_called_once()
    args, _ = mock_vault_obj.push_to_obsidian.call_args
    
    # New Argument Order: (category, project, transcript, analysis)
    assert args[0] == "01_Projects"       # Category
    assert args[1] == "Feena"             # Project
    assert args[2] == "Clean Transcript"  # Transcript
    assert args[3] == "AI Analysis"       # Analysis