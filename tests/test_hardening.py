import pytest
import asyncio
import git.exc
import os
import shutil
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from exceptions import MediaIngestionError, GitPersistenceError, TelegramDownloadError
from vault_manager import VaultManager
from processor import TaskProcessor
from bot_utils import validate_media_file
from templates import MediaTemplate
import main

@pytest.fixture
def user_cfg():
    cfg = MagicMock()
    cfg.name = "TestUser"
    cfg.repo_url = "https://github.com/test/vault"
    cfg.token = "token"
    cfg.username = "user"
    return cfg

# --- 1. VaultManager Tests ---

def test_vault_manager_secure_media_git_clone_failure(user_cfg, mocker):
    mocker.patch("git.Repo.clone_from", side_effect=git.exc.GitCommandError("clone", 128))
    vault = VaultManager(user_cfg.repo_url, user_cfg.token, user_cfg.username)

    with pytest.raises(GitPersistenceError) as excinfo:
        vault.secure_media("test.jpg", b"content", "metadata")
    assert "Failed to clone repository" in str(excinfo.value)

def test_vault_manager_secure_media_io_failure(user_cfg, mocker):
    mocker.patch("git.Repo.clone_from")
    mocker.patch("os.makedirs")
    # Mocking open for both binary and metadata files.
    # We'll make it fail on the first write.
    mocker.patch("builtins.open", side_effect=IOError("Disk full"))
    vault = VaultManager(user_cfg.repo_url, user_cfg.token, user_cfg.username)

    with pytest.raises(GitPersistenceError) as excinfo:
        vault.secure_media("test.jpg", b"content", "metadata")
    assert "Failed to write media file" in str(excinfo.value)

def test_vault_manager_secure_media_push_failure(user_cfg, mocker):
    mock_repo = MagicMock()
    mocker.patch("git.Repo.clone_from", return_value=mock_repo)
    mocker.patch("os.makedirs")
    mocker.patch("builtins.open", mock_open())
    mocker.patch.object(VaultManager, "_discover_new_folders")

    mock_origin = MagicMock()
    mock_origin.push.side_effect = git.exc.GitCommandError("push", 1)
    mock_repo.remote.return_value = mock_origin

    vault = VaultManager(user_cfg.repo_url, user_cfg.token, user_cfg.username)

    with pytest.raises(GitPersistenceError) as excinfo:
        vault.secure_media("test.jpg", b"content", "metadata")
    assert "Git operation failed" in str(excinfo.value)

# --- 2. TaskProcessor Tests ---

@pytest.mark.asyncio
async def test_processor_ingest_single_media_download_failure(user_cfg, mocker):
    processor = TaskProcessor()
    mock_context = MagicMock()
    mock_context.bot.get_file = AsyncMock(side_effect=Exception("Telegram down"))

    file_info = {'original_name': 'test.jpg', 'file_name': 'test.jpg', 'mime_type': 'image/jpeg', 'file_size': 100, 'timestamp': '2024'}

    with pytest.raises(TelegramDownloadError) as excinfo:
        await processor.ingest_single_media(user_cfg, file_info, "id", mock_context)
    assert "Failed to download your file from Telegram" in str(excinfo.value)

@pytest.mark.asyncio
async def test_processor_ingest_single_media_persistence_failure(user_cfg, mocker):
    processor = TaskProcessor()
    mock_context = MagicMock()
    mock_file = AsyncMock()
    mock_file.download_as_bytearray = AsyncMock(return_value=b"content")
    mock_context.bot.get_file = AsyncMock(return_value=mock_file)

    # Mock VaultManager.secure_media to raise GitPersistenceError
    mock_vault = MagicMock()
    mock_vault.secure_media.side_effect = GitPersistenceError("Push failed")
    mocker.patch("processor.VaultManager", return_value=mock_vault)

    file_info = {'original_name': 'test.jpg', 'file_name': 'test.jpg', 'mime_type': 'image/jpeg', 'file_size': 100, 'timestamp': '2024'}

    with pytest.raises(GitPersistenceError):
        await processor.ingest_single_media(user_cfg, file_info, "id", mock_context)

# --- 3. Bot Utils Tests ---

def test_validate_media_file_size_error():
    message = MagicMock()
    message.document = MagicMock(file_size=25 * 1024 * 1024, file_name="large.zip", mime_type="application/zip")

    with patch("bot_utils.MAX_FILE_SIZE_MB", 20):
        is_valid, info, error = validate_media_file(message)

    assert is_valid is False
    assert "too large (25.0MB)" in error

# --- 4. Main Error Handling Tests ---

@pytest.mark.asyncio
async def test_process_media_error_handling(mocker):
    # Authorized user
    mocker.patch("bot_utils.ALLOWED_IDS", [123])
    mock_update = MagicMock()
    mock_update.effective_user.id = 123
    mock_update.message.media_group_id = None
    mock_update.message.reply_text = AsyncMock()

    # Mock validation to succeed
    mocker.patch("main.validate_media_file", return_value=(True, {'original_name': 'test.jpg', 'file_id': 'id', 'file_name': 'test.jpg'}, None))
    mocker.patch("main.get_user_config")

    # Mock processor to raise TelegramDownloadError
    mocker.patch("main.processor.ingest_single_media", side_effect=TelegramDownloadError("Down"))

    mock_status_msg = AsyncMock()
    mock_update.message.reply_text.return_value = mock_status_msg

    await main.process_media(mock_update, MagicMock())

    mock_status_msg.edit_text.assert_any_call("⚠️ Failed to download your file from Telegram. This might be a temporary network issue. Please try again.")

@pytest.mark.asyncio
async def test_process_media_group_partial_failure_feedback(mocker):
    # Mock debounced_ingest_group call or just test it directly
    media_group_id = "group1"
    user_id = 123
    mock_context = MagicMock()

    mock_status_msg = AsyncMock()
    main._media_groups_processing[media_group_id] = {
        'updates': [MagicMock()],
        'task': None,
        'status_msg': mock_status_msg
    }

    mocker.patch("main.get_user_config")
    results = {
        'total_files': 2,
        'succeeded': 1,
        'failed': 1,
        'failed_details': [{'filename': 'fail.jpg', 'reason': 'Too large'}]
    }
    mocker.patch("main.processor.ingest_media_group", AsyncMock(return_value=results))

    await main.debounced_ingest_group(media_group_id, user_id, mock_context)

    mock_status_msg.edit_text.assert_any_call(
        "⚠️ Data Secured! 1 files saved. 1 files failed (e.g., 'fail.jpg' - Too large). Please check your vault."
    )

# --- 5. Graceful Shutdown Tests ---

@pytest.mark.asyncio
async def test_shutdown_media_group_timers():
    mock_task = MagicMock()
    mock_task.done.return_value = False
    main._media_groups_processing = {
        "group1": {"task": mock_task}
    }

    await main._shutdown_media_group_timers()

    mock_task.cancel.assert_called_once()
    assert main._media_groups_processing == {}

# --- 6. Template Tests ---

def test_media_template_generation():
    filename = "IMG_20240101_120000.jpg"
    original_name = "vacation.jpg"
    mime_type = "image/jpeg"
    file_size = 1024 * 1024 # 1MB
    caption = "Fun at the beach!"
    timestamp = "2024-01-01 12:00:00"

    content = MediaTemplate.get_metadata_content(
        filename=filename,
        original_name=original_name,
        mime_type=mime_type,
        file_size=file_size,
        caption=caption,
        timestamp=timestamp
    )

    assert f"original_name: \"{original_name}\"" in content
    assert f"mime_type: {mime_type}" in content
    assert "size_mb: 1.00" in content
    assert f"![[{filename}]]" in content
    assert f"## 📝 Caption\n{caption}" in content

def test_media_template_no_caption():
    content = MediaTemplate.get_metadata_content(
        filename="test.jpg",
        original_name="test.jpg",
        mime_type="image/jpeg",
        file_size=100,
        caption=None,
        timestamp="now"
    )
    assert "## 📝 Caption" not in content
