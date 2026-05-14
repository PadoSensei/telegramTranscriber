import pytest
import os
from unittest.mock import MagicMock, patch
from telegram_transcriber.transcriber import Transcriber

@pytest.fixture
def mock_transcriber(mocker):
    # Mock the whisper.load_model so it doesn't actually load during tests
    mocker.patch("whisper.load_model")
    return Transcriber(model_name="tiny")

@pytest.mark.asyncio
async def test_get_voice_file(mock_transcriber, mocker):
    # Mock Telegram Update and Context
    mock_update = MagicMock()
    mock_context = MagicMock()
    mock_file = MagicMock()
    
    # Simulate a voice message
    mock_update.message.voice.file_id = "12345"
    mock_context.bot.get_file = mocker.AsyncMock(return_value=mock_file)
    mock_file.download_to_drive = mocker.AsyncMock()

    path = await mock_transcriber.get_voice_file(mock_update, mock_context)
    
    assert "temp_" in path
    assert path.endswith(".oga")
    mock_file.download_to_drive.assert_called_once()

@pytest.mark.asyncio
async def test_transcribe_and_cleanup(mock_transcriber, mocker):
    # Mock the internal transcription logic
    mock_transcriber.model.transcribe.return_value = {"text": "Hello world"}
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("os.remove")

    text = await mock_transcriber.transcribe("fake_path.oga")
    
    assert text == "Hello world"
    # Verify cleanup was called
    os.remove.assert_called_once_with("fake_path.oga")