import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from telegram_transcriber import main

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

    main._media_groups_processing[media_group_id] = {
        'updates': [update1],
        'task': None,
        'status_msg': mock_status_msg
    }

    # Mock dependencies
    mock_get_cfg = mocker.patch("telegram_transcriber.main.get_user_config")
    mock_cfg = MagicMock()
    mock_get_cfg.return_value = mock_cfg

    mock_ingest = mocker.patch("telegram_transcriber.main.processor.ingest_media_group", new_callable=AsyncMock)
    mock_ingest.return_value = {
        'total_files': 1,
        'succeeded': 1,
        'failed': 0,
        'failed_details': [],
        'saved_files': ['file1.jpg']
    }

    # Execute
    await main.debounced_ingest_group(media_group_id, user_id, mock_context)

    # Verify
    mock_ingest.assert_called_once()
    mock_status_msg.edit_text.assert_any_call("✅ Data Secured! 1 items saved to your Inbox.")
    assert media_group_id not in main._media_groups_processing

@pytest.mark.asyncio
async def test_debounced_ingest_group_partial_failure(mocker):
    mocker.patch("asyncio.sleep", return_value=None)
    
    media_group_id = "test_group_456"
    user_id = 12345
    mock_context = MagicMock()
    mock_status_msg = AsyncMock()

    update1 = MagicMock()
    update2 = MagicMock()

    main._media_groups_processing[media_group_id] = {
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

    # Execute
    await main.debounced_ingest_group(media_group_id, user_id, mock_context)

    # Verify
    call_args = mock_status_msg.edit_text.call_args[0][0]
    assert "⚠️ Data Secured! 1 files saved. 1 files failed" in call_args
    assert "fail.jpg' - too large" in call_args
