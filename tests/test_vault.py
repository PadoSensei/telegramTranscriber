import pytest
from unittest.mock import AsyncMock, MagicMock
from bot_utils import parse_vault_request
from main import process_media

@pytest.fixture
def mock_user_map():
    return {
        "Star": "01_Projects/Bloom_Prep/STAR_Story_Bank",
        "Inbox": "00_Inbox"
    }

@pytest.mark.asyncio
async def test_process_media_triggers_sync(mocker):
    # Mock Transcriber methods as ASYNC
    mocker.patch("main.transcriber.get_voice_file", new_callable=AsyncMock, return_value="fake.oga")
    mocker.patch("main.transcriber.transcribe", new_callable=AsyncMock, return_value="My story #star")
    
    # Mock the Processor
    mock_processor = mocker.patch("main.processor.run_sync_stack", new_callable=AsyncMock)
    mock_processor.return_value = ("Clean", "Analysis", True)
    
    # Mock Telegram Update
    mock_update = MagicMock()
    mock_context = MagicMock()
    mock_update.effective_user.id = 6426489405
    mock_update.message.voice.file_id = "v123"
    
    # Mock status message so 'await status_msg.delete()' works
    mock_status_msg = AsyncMock()
    mock_context.bot.send_message = mocker.AsyncMock(return_value=mock_status_msg)

    await process_media(mock_update, mock_context)

    mock_processor.assert_called_once()
    # Check positional arguments: args[1] is category
    args, _ = mock_processor.call_args
    assert args[1] == "01_Projects/Bloom_Prep/STAR_Story_Bank"

@pytest.mark.asyncio
async def test_process_media_no_sync_triggers_inbox(mocker):
    # Mock Transcriber methods as ASYNC to avoid TypeError
    mocker.patch("main.transcriber.get_voice_file", new_callable=AsyncMock, return_value="fake.oga")
    mocker.patch("main.transcriber.transcribe", new_callable=AsyncMock, return_value="Just talking")
    
    mock_processor = mocker.patch("main.processor.run_sync_stack", new_callable=AsyncMock)
    
    mock_update = MagicMock()
    mock_context = MagicMock()
    mock_update.effective_user.id = 6426489405
    
    # Mock status message
    mock_status_msg = AsyncMock()
    mock_context.bot.send_message = mocker.AsyncMock(return_value=mock_status_msg)

    await process_media(mock_update, mock_context)

    # Should not sync because no hashtag/keyword was present
    mock_processor.assert_not_called()