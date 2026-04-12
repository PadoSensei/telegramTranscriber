import pytest
import asyncio
from processor import TaskProcessor
from schema import UserConfig
from unittest.mock import MagicMock, patch

@pytest.fixture
def processor():
    return TaskProcessor()

@pytest.fixture
def user_cfg():
    return UserConfig(
        name="TestUser",
        repo_url="https://github.com/test/repo",
        token="test_token",
        username="test_user",
        category_map={"Inbox": "00_Inbox"},
        gdrive_doc_id="123456789012345678901234567890" # Valid length
    )

@pytest.mark.asyncio
async def test_run_sync_stack_soft_fail(processor, user_cfg, mocker):
    # Mock AI Engine
    mocker.patch.object(processor.ai, 'get_structured_output', return_value=("clean", "analysis"))

    # Mock VaultManager (Git Success)
    mock_vault = mocker.patch('processor.VaultManager')
    mock_vault_instance = mock_vault.return_value
    mock_vault_instance.push_to_obsidian.return_value = True

    # Mock GoogleManager (Google Fail)
    mock_google = mocker.patch('processor.GoogleManager')
    mock_google_instance = mock_google.return_value
    # Use a future that returns False to simulate failure
    mock_google_instance.sync_to_doc.return_value = asyncio.Future()
    mock_google_instance.sync_to_doc.return_value.set_result(False)

    # We need to mock loop.run_in_executor because it's used for git_task
    mocker.patch('asyncio.get_running_loop')
    mock_loop = asyncio.get_running_loop.return_value
    mock_loop.run_in_executor.return_value = asyncio.Future()
    mock_loop.run_in_executor.return_value.set_result(True)

    clean, analysis, git_success, google_success = await processor.run_sync_stack(
        user_cfg, "Inbox", "Inbox", "test text"
    )

    assert git_success is True
    assert google_success is False
    assert clean == "clean"
