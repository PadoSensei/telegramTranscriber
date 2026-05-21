import pytest
from unittest.mock import AsyncMock, MagicMock
# Ensure this import matches your new layout
from telegram_transcriber.main import debounced_ingest_group, _media_groups_processing

@pytest.mark.asyncio
async def test_debounced_ingest_group_success(mocker):
    # 1. Mock sleep so the test is instant
    mocker.patch("asyncio.sleep", return_value=None)
    
    media_group_id = "test_group_123"
    user_id = 12345
    mock_status_msg = AsyncMock()
    _media_groups_processing[media_group_id] = {
        'updates': [MagicMock()],
        'task': None,
        'status_msg': mock_status_msg
    }

    # 2. Patch the specific instance inside the main module
    mocker.patch("telegram_transcriber.main.get_user_config", return_value=MagicMock())
    
    # CRITICAL: We patch the instance attribute 'processor' inside the 'main' module
    mock_ingest = mocker.patch("telegram_transcriber.main.processor.ingest_media_group", new_callable=AsyncMock)
    mock_ingest.return_value = {
        'total_files': 1, 'succeeded': 1, 'failed': 0, 'failed_details': [], 'saved_files': ['f1.jpg']
    }

    await debounced_ingest_group(media_group_id, user_id, MagicMock())

    # 3. Robust Assertion: Check that the string is IN the call, don't require exact match
    args, _ = mock_status_msg.edit_text.call_args
    assert "Data Secured!" in args[0]
    assert "1 items saved" in args[0]

@pytest.mark.asyncio
async def test_debounced_ingest_group_partial_failure(mocker):
    mocker.patch("asyncio.sleep", return_value=None)
    media_group_id = "test_group_456"
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

    await debounced_ingest_group(media_group_id, 12345, MagicMock())

    args, _ = mock_status_msg.edit_text.call_args
    assert "1 files saved" in args[0]
    assert "1 files failed" in args[0]