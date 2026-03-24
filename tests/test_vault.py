import pytest
from unittest.mock import MagicMock, AsyncMock
from main import parse_vault_request, process_media
from config import ALLOWED_IDS

# --- 1. Test Hashtag Parsing ---
@pytest.mark.parametrize("text, expected_sync, expected_project", [
    ("#2ndBrain #Feena", True, "Feena"),
    ("#2ndBrain #AISolutions", True, "AISolutions"),
    ("#2ndBrain", True, "00_Inbox"),
    ("#Feena", False, None),
    ("#2ndBrain #TypoProj", True, "00_Inbox"),
])
def test_hashtag_parsing(text, expected_sync, expected_project):
    # This expects 3 values now
    should_sync, project, warning = parse_vault_request(text)
    assert should_sync == expected_sync
    assert project == expected_project


# --- 2. Test the Bot Integration ---
@pytest.mark.asyncio
async def test_process_media_triggers_sync(mocker):
    # A. Create the Mock VaultManager Object
    mock_vault_obj = MagicMock()
    mock_vault_obj.push_to_obsidian = MagicMock(return_value=True)
    
    # B. Patch the FACTORY FUNCTION in main
    # This is where the AttributeError usually happens if the name is wrong
    mocker.patch('main.get_vault_for_user', return_value=mock_vault_obj)

    # C. Mock external dependencies
    mocker.patch('main.transcribe_sync', return_value="Raw Whisper Text")
    mocker.patch('main.call_gemini', side_effect=["Clean Transcript", "AI Analysis"])

    # D. Mock Telegram Infrastructure
    mock_status_msg = AsyncMock()
    mock_status_msg.edit_text = AsyncMock()
    mock_status_msg.delete = AsyncMock()
    
    mock_context = MagicMock()
    mock_context.bot.send_message = AsyncMock(return_value=mock_status_msg)
    
    # Mock the file download path
    mock_file = AsyncMock()
    mock_file.download_to_drive = AsyncMock()
    mock_context.bot.get_file = AsyncMock(return_value=mock_file)

    # E. Mock the Update
    mock_update = MagicMock()
    mock_update.effective_user.id = ALLOWED_IDS[0] 
    mock_update.effective_chat.id = 12345
    mock_update.message.caption = "#2ndBrain #Feena"
    mock_update.message.from_user.first_name = "TestUser"
    mock_update.message.voice = MagicMock(file_id="v123", duration=10)
    mock_update.message.audio = None
    mock_update.message.document = None

    # F. RUN
    await process_media(mock_update, mock_context)

    # G. ASSERTIONS
    # Verify the factory was called and the resulting object pushed data
    mock_vault_obj.push_to_obsidian.assert_called_once()
    args, _ = mock_vault_obj.push_to_obsidian.call_args
    assert args[0] == "Feena"
    assert args[1] == "Clean Transcript"