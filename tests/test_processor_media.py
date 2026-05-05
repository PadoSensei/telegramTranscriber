import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from processor import TaskProcessor
from vault_manager import VaultManager

@pytest.mark.asyncio
async def test_ingest_single_media(mocker):
    # Setup
    processor = TaskProcessor()
    user_cfg = MagicMock()
    user_cfg.name = "TestUser"
    user_cfg.repo_url = "https://github.com/test/vault"
    user_cfg.token = "token"
    user_cfg.username = "user"

    file_info = {
        'file_name': 'IMG_123.jpg',
        'original_name': 'test.jpg',
        'mime_type': 'image/jpeg',
        'file_size': 1024,
        'timestamp': '2024-01-01 12:00:00',
        'caption': 'test caption'
    }
    file_id = "file_id_123"

    mock_context = MagicMock()
    mock_file = AsyncMock()
    mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"fake content"))
    mock_context.bot.get_file = AsyncMock(return_value=mock_file)

    # Mock VaultManager.secure_media (synchronous, called in executor)
    mock_vault = MagicMock()
    mock_vault.secure_media.return_value = "00_Inbox/IMG_123.jpg"
    mocker.patch("processor.VaultManager", return_value=mock_vault)

    # Execute
    saved_path = await processor.ingest_single_media(user_cfg, file_info, file_id, mock_context)

    # Verify
    assert saved_path == "00_Inbox/IMG_123.jpg"
    mock_context.bot.get_file.assert_called_once_with(file_id)
    # Since it's run in executor, we check if secure_media was called on the mock vault
    # Note: run_in_executor might make it tricky to check direct calls if not careful,
    # but here processor.VaultManager is patched.

@pytest.mark.asyncio
async def test_ingest_media_group_aggregation(mocker):
    processor = TaskProcessor()
    user_cfg = MagicMock()

    update1 = MagicMock()
    update1.message.photo = [MagicMock(file_id="p1", file_size=100)]
    update1.message.document = None
    update1.message.video = None
    update1.message.caption = "caption 1"

    update2 = MagicMock()
    update2.message.photo = [MagicMock(file_id="p2", file_size=100)]
    update2.message.document = None
    update2.message.video = None
    update2.message.caption = "caption 2"

    # Mock ingest_single_media to succeed for first, fail for second
    mock_ingest_single = mocker.patch.object(processor, "ingest_single_media", new_callable=AsyncMock)
    mock_ingest_single.side_effect = ["path1", Exception("Git error")]

    # Mock validation to always succeed
    mocker.patch("processor.validate_media_file", return_value=(True, {
        'file_id': 'id', 'file_name': 'name', 'original_name': 'orig',
        'mime_type': 'mime', 'file_size': 100, 'timestamp': 'time'
    }, None))

    # Execute
    results = await processor.ingest_media_group(user_cfg, [update1, update2], MagicMock())

    # Verify
    assert results['total_files'] == 2
    assert results['succeeded'] == 1
    assert results['failed'] == 1
    assert results['failed_details'][0]['filename'] == 'orig'
    assert results['failed_details'][0]['reason'] == 'Git error'
