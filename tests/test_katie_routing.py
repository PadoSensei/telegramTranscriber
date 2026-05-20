import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram_transcriber.main import process_entry
from telegram_transcriber.schema import UserConfig

# Using the placeholder ID for testing
KATIE_ID = 999999999 

@pytest.mark.asyncio
@pytest.mark.parametrize("input_text, expected_folder", [
    # Everything should go to Inbox now
    ("Just thinking about the flight to Spain", "00_Inbox"),
    ("I led the US launch of Tullamore D.E.W. Honey #star", "00_Inbox"),
    ("The layout of the Bloom festival is interesting #bloom", "00_Inbox"),
    ("This is a random thought for my 2nd brain", "00_Inbox"),
])
async def test_global_inbox_routing_logic(input_text, expected_folder, mocker):
    """
    Verifies that global routing now sends everything to the Inbox,
    ignoring any hashtags.
    """
    
    mocker.patch("telegram_transcriber.bot_utils.ALLOWED_IDS", [KATIE_ID])
    
    mock_cfg = UserConfig(
        name="Katie",
        repo_url="https://github.com/mock/repo",
        token="mock_token",
        username="katieOD",
        gdrive_doc_id=None,
        category_map={}
    )

    mocker.patch("telegram_transcriber.main.get_user_config", return_value=mock_cfg)

    # Mock Transcriber
    mocker.patch("telegram_transcriber.main.transcriber.get_voice_file", new_callable=AsyncMock, return_value="fake_voice.oga")
    mocker.patch("telegram_transcriber.main.transcriber.transcribe", new_callable=AsyncMock, return_value=input_text)
    
    # Mock the Processor
    mock_processor = mocker.patch("telegram_transcriber.main.processor.run_sync_stack", new_callable=AsyncMock)
    mock_processor.return_value = ("Clean Text", "Analysis Output", True, True)
    
    # Mock Telegram Update & Context
    mock_update = MagicMock()
    mock_context = MagicMock()
    mock_update.effective_user.id = KATIE_ID
    mock_update.effective_user.first_name = "Katie"
    mock_update.message.voice.file_id = "voice_123"
    mock_update.message.text = None
    mock_update.message.caption = None
    
    mock_status_msg = AsyncMock()
    mock_context.bot.send_message = mocker.AsyncMock(return_value=mock_status_msg)

    # --- 2. EXECUTE ---
    await process_entry(mock_update, mock_context)

    # --- 3. ASSERTIONS ---
    mock_processor.assert_called_once()

    args, _ = mock_processor.call_args
    assert args[0].name == "Katie"
    assert args[1] == expected_folder
    assert args[2] == "Inbox"
