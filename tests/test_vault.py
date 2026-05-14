import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram_transcriber.bot_utils import parse_vault_request
from telegram_transcriber.main import process_entry

# --- FIXTURES ---

@pytest.fixture
def mock_user_map():
    """Simulated category map from telegram_transcriber.config.py."""
    return {
        "Star": "01_Projects/Bloom_Prep/STAR_Story_Bank",
        "Inbox": "00_Inbox"
    }

# --- 1. UNIT TESTS ---

@pytest.mark.asyncio
async def test_process_entry_triggers_sync_with_hashtag(mocker):
    """Verifies that audio with a hashtag routes to the correct project folder."""
    # 1. Mock Transcriber (Async)
    mocker.patch("telegram_transcriber.main.transcriber.get_voice_file", new_callable=AsyncMock, return_value="fake.oga")
    mocker.patch("telegram_transcriber.main.transcriber.transcribe", new_callable=AsyncMock, return_value="My project story #star")
    
    # 2. Mock the Processor (Async)
    # We must return a 3-item tuple to satisfy: clean, analysis, success = await processor...
    mock_processor = mocker.patch("telegram_transcriber.main.processor.run_sync_stack", new_callable=AsyncMock)
    mock_processor.return_value = ("Clean Story", "Analysis", True)
    
    # 3. Mock Telegram Update/Context
    mock_update = MagicMock()
    mock_context = MagicMock()
    mock_update.effective_user.id = 6426489405 # Authorized ID
    mock_update.effective_user.first_name = "Katie"
    mock_update.message.voice.file_id = "v123"
    
    # 4. Mock Status Message so .delete() doesn't fail
    mock_status_msg = AsyncMock()
    mock_context.bot.send_mess