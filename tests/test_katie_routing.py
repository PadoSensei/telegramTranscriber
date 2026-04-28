import pytest
from unittest.mock import AsyncMock, MagicMock
from main import process_entry
from schema import UserConfig

# Using the placeholder ID for testing
KATIE_ID = 999999999 

@pytest.mark.asyncio
@pytest.mark.parametrize("input_text, expected_folder, expected_sync", [
    # 1. No Hashtag -> Should go to Inbox
    ("Just thinking about the flight to Spain", "00_Inbox", True),
    
    # 2. #star Hashtag -> Should go to Katie's STAR_Story_Bank
    ("I led the US launch of Tullamore D.E.W. Honey #star", "01_Projects/Bloom_Prep/STAR_Story_Bank", True),
    
    # 3. #bloom Hashtag -> Should go to Katie's Bloom_Prep folder
    ("The layout of the Bloom festival is interesting #bloom", "01_Projects/Bloom_Prep", True),
    
    # 4. Keyword '2nd brain' with no tag -> Should default to Katie's Inbox folder
    ("This is a random thought for my 2nd brain", "00_Inbox", True),
])
async def test_katie_routing_logic(input_text, expected_folder, expected_sync, mocker):
    """
    Verifies that Katie's ID correctly routes messages to her specific folders
    based on the hashtags she uses, bypassing security for the test.
    """
    
    # --- SENIOR MOVE: MOCK SECURITY & CONFIG ---
    # We patch the whitelist so the test ID is authorized
    mocker.patch("bot_utils.ALLOWED_IDS", [KATIE_ID])
    
    mock_cfg = UserConfig(
        name="Katie",
        repo_url="https://github.com/mock/repo",
        token="mock_token",
        username="katieOD",
        gdrive_doc_id="1-mock-doc-id-longer-than-20-chars",
        category_map={
            "Star": "01_Projects/Bloom_Prep/STAR_Story_Bank",
            "Bloom": "01_Projects/Bloom_Prep",
            "Inbox": "00_Inbox"
        }
    )

    # We patch get_user_config to return our mock config
    mocker.patch("main.get_user_config", return_value=mock_cfg)

    # --- 1. MOCK SERVICES ---
    # Mock Transcriber (Async)
    mocker.patch("main.transcriber.get_voice_file", new_callable=AsyncMock, return_value="fake_voice.oga")
    mocker.patch("main.transcriber.transcribe", new_callable=AsyncMock, return_value=input_text)
    
    # Mock the Processor (Async)
    mock_processor = mocker.patch("main.processor.run_sync_stack", new_callable=AsyncMock)
    mock_processor.return_value = ("Clean Text", "Analysis Output", True, True)
    
    # Mock Telegram Update & Context
    mock_update = MagicMock()
    mock_context = MagicMock()
    mock_update.effective_user.id = KATIE_ID
    mock_update.effective_user.first_name = "Katie"
    mock_update.message.voice.file_id = "voice_123"
    mock_update.message.text = None
    mock_update.message.caption = None
    
    # Mock Status Message to allow 'await status_msg.delete()'
    mock_status_msg = AsyncMock()
    mock_context.bot.send_message = mocker.AsyncMock(return_value=mock_status_msg)

    # --- 2. EXECUTE ---
    await process_entry(mock_update, mock_context)

    # --- 3. ASSERTIONS ---
    if expected_sync:
        # In the new Orchestrator, everything syncs!
        mock_processor.assert_called_once()
        
        # Verify it used the CORRECT mock config and folder path
        args, _ = mock_processor.call_args
        assert args[0] == mock_cfg
        assert args[1] == expected_folder
        
        print(f"✅ Successfully routed '{input_text}' to '{expected_folder}'")
    else:
        # Verify no sync was attempted for plain messages
        mock_processor.assert_not_called()
        print(f"✅ Correcty ignored non-sync message: '{input_text}'")
