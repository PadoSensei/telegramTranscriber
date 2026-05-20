import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from telegram_transcriber.main import debounced_ingest_group, _media_groups_processing

@pytest.mark.asyncio
async def test_debounced_ingest_group_success(mocker):
    mocker.patch("asyncio.sleep", return_value=None)
    media_group_id = "test_group_123"
    user_id = 12345
    mock_context = MagicMock()
    mock_status_msg = AsyncMock()

    update1 = MagicMock()
    update1.message.media_group_id = media_group_id

    _media_groups_processing[media_group_id] = {
        'updates': [update1],
        'task': None,
        'status_msg': mock_status_msg
    }

    mocker.patch("telegram_transcriber.main.get_user_config", return_value=MagicMock())
    mock_ingest = mocker.patch("telegram_transcriber.main.processor.ingest_media_group", new_callable=AsyncMock)
    mock_ingest.return_value = {
        'total_files': 1, 'succeeded': 1, 'failed': 0, 'failed_details': [], 'saved_files': ['f1.jpg']
    }

    await debounced_ingest_group(media_group_id, user_id, mock_context)
    mock_status_msg.edit_text.assert_any_call("✅ Data Secured! 1 items saved to your Inbox.")

@pytest.mark.asyncio
async def test_debounced_ingest_group_partial_failure(mocker):
    mocker.patch("asyncio.sleep", return_value=None)
    media_group_id = "test_group_456"
    user_id = 12345
    mock_status_msg = AsyncMock()

    _media_groups_processing[media_group_id] = {
        'updates': [MagicMock(), MagicMock()],
        'task': None,
        'status_msg': mock_status_msg
    }

    mocker.patch("telegram_transcriber.main.get_user_config")
    mock_ingest = mocker.patch("telegram_transcriber.main.processor.ingest_media_group", new_callable=AsyncMock)
    mock_ingest.return_value = {
        'total_files': 2, 'succeeded': 1, 'failed': 1, 
        'failed_details': [{'filename': 'fail.jpg', 'reason': 'too large'}],
        'saved_files': ['success.jpg']
    }

    await debounced_ingest_group(media_group_id, user_id, MagicMock())
    actual_call = mock_status_msg.edit_text.call_args[0][0]
    assert "⚠️ Data Secured! 1 files saved. 1 files failed" in actual_call