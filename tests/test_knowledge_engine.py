import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from telegram_transcriber.processor import TaskProcessor
from telegram_transcriber.schema import UserConfig

@pytest.mark.asyncio
async def test_run_sync_stack_success(mocker):
    # Mock AI Engine
    mock_ai = mocker.patch("telegram_transcriber.processor.AIEngine")
    mock_ai.return_value.get_structured_output = AsyncMock(return_value=("Clean Content", "Analysis Content"))

    # Mock VaultManager
    mock_vault = mocker.patch("telegram_transcriber.processor.VaultManager")

    processor = TaskProcessor()
    user_cfg = UserConfig(
        name="TestUser",
        repo_url="http://github.com/test/repo",
        token="token",
        username="user",
        category_map={},
        gdrive_doc_id=None
    )

    mock_loop = MagicMock()
    mock_loop.run_in_executor = AsyncMock(return_value=True)
    mocker.patch("asyncio.get_running_loop", return_value=mock_loop)

    clean, analysis, success = await processor.run_sync_stack(user_cfg, "Raw input text")

    assert clean == "Clean Content"
    assert analysis == "Analysis Content"
    assert success is True

@pytest.mark.asyncio
async def test_run_sync_stack_flow(mocker):
    # Integration-ish test for the flow
    mock_ai_instance = MagicMock()
    mock_ai_instance.get_structured_output = AsyncMock(return_value=("Polished", "Action Items"))
    mocker.patch("telegram_transcriber.processor.AIEngine", return_value=mock_ai_instance)

    mock_vault_instance = MagicMock()
    mock_vault_instance.push_to_obsidian = MagicMock(return_value=True)
    mocker.patch("telegram_transcriber.processor.VaultManager", return_value=mock_vault_instance)

    processor = TaskProcessor()
    user_cfg = UserConfig(
        name="Test",
        repo_url="http://github.com/test/repo",
        token="token",
        username="user",
        category_map={},
        gdrive_doc_id=None
    )

    # Mock loop.run_in_executor to call the function directly for testing
    async def mock_run(executor, func, *args):
        return func(*args)
    mocker.patch("asyncio.get_running_loop").return_value.run_in_executor = AsyncMock(side_effect=mock_run)

    clean, analysis, success = await processor.run_sync_stack(user_cfg, "Hello world", input_type="text")

    assert success is True
    assert clean == "Polished"
    # Verify VaultManager was called with correct entry format (contains delimiters)
    call_args = mock_vault_instance.push_to_obsidian.call_args[0]
    entry = call_args[0]
    assert "# CAPTURE_START" in entry
    assert "# CAPTURE_END" in entry
    assert "## Capture (" in entry
    assert "Polished" in entry
