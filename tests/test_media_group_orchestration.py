import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
# Note: Update this import if you haven't finished the refactor move yet
from telegram_transcriber.main import debounced_ingest_group, _media_groups_processing

@pytest.mark.asyncio
async def test_debounced_ingest_group_success(mocker):
    # 1. Mock asyncio.sleep to speed up the test
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

    # 2. Patch the processor instance inside the main module
    mock_get_cfg = mocker.patch("telegram_transcriber.main.get_user_config")
    mock_cfg = MagicMock()
    mock_get_cfg.return_value = mock_cfg

    # We patch the instance attribute specifically
    mock_ingest = mocker.patch("telegram_transcriber.main.processor.ingest_media_group", new_callable=AsyncMock)
    mock_ingest.return_value = {
        'total_files': 1,
        'succeeded': 1,
        'failed': 0,
        'failed_details': [],
        'saved_files': ['file1.jpg']
    }

    await debounced_ingest_group(media_group_id, user_id, mock_context)

    # 3. Assertions
    mock_ingest.assert_called_once()
    # Align this string with line 215 of your main.py
    mock_status_msg.edit_text.assert_any_call("✅ Data Secured! 1 items saved to your Inbox.")
    assert media_group_id not in _media_groups_processing

@pytest.mark.asyncio
async def test_debounced_ingest_group_partial_failure(mocker):
    mocker.patch("asyncio.sleep", return_value=None)
    
    media_group_id = "test_group_456"
    user_id = 12345
    mock_context = MagicMock()
    mock_status_msg = AsyncMock()

    update1 = MagicMock()
    update2 = MagicMock()

    _media_groups_processing[media_group_id] = {
        'updates': [update1, update2],
        'task': None,
        'status_msg': mock_status_msg
    }

    mocker.patch("telegram_transcriber.main.get_user_config")
    mock_ingest = mocker.patch("telegram_transcriber.main.processor.ingest_media_group", new_callable=AsyncMock)
    mock_ingest.return_value = {
        'total_files': 2,
        'succeeded': 1,
        'failed': 1,
        'failed_details': [{'filename': 'fail.jpg', 'reason': 'too large'}],
        'saved_files': ['success.jpg']
    }

    await debounced_ingest_group(media_group_id, user_id, mock_context)

    # 4. Corrected assertion string to match your code's logic
    # Your code uses: f"⚠️ Data Secured! {succeeded} files saved. {failed} files failed..."
    actual_call = mock_status_msg.edit_text.call_args[0][0]
    assert "⚠️ Data Secured! 1 files saved. 1 files failed" in actual_call
    assert "fail.jpg - too large" in actual_call