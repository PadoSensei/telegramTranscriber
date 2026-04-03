import pytest
from unittest.mock import MagicMock, AsyncMock
from processor import TaskProcessor

@pytest.fixture
def processor(mocker):
    mocker.patch("processor.AIEngine")
    mocker.patch("processor.GoogleManager")
    return TaskProcessor()

@pytest.mark.asyncio
async def test_run_sync_stack_success(processor, mocker):
    # 1. Setup Mocks
    processor.ai.get_structured_output.return_value = ("Clean Story", "Analysis")
    
    # Mock VaultManager instance and its method
    mock_vault_class = mocker.patch("processor.VaultManager")
    mock_vault_instance = mock_vault_class.return_value
    # CRITICAL: This must return True for the overall_success to be True
    mock_vault_instance.push_to_obsidian.return_value = True
    
    # Mock Google Sync
    processor.google.sync_to_doc = mocker.AsyncMock(return_value=True)

    # 2. Execute (Using a valid ID from your config)
    clean, analysis, overall_success = await processor.run_sync_stack(
        user_id=6426489405, 
        category="STAR_Story_Bank", 
        project="Tullamore_Launch", 
        text="I did things", 
        user_name="Katie"
    )

    # 3. Assertions
    assert overall_success is True
    assert clean == "Clean Story"
    mock_vault_instance.push_to_obsidian.assert_called_once()
    processor.google.sync_to_doc.assert_called_once()

@pytest.mark.asyncio
async def test_run_sync_stack_partial_failure(processor, mocker):
    processor.ai.get_structured_output.return_value = ("Clean", "Analysis")
    
    mock_vault_class = mocker.patch("processor.VaultManager")
    mock_vault_class.return_value.push_to_obsidian.return_value = False # GitHub fails
    processor.google.sync_to_doc = mocker.AsyncMock(return_value=True)

    _, _, overall_success = await processor.run_sync_stack(
        6426489405, "Inbox", "Project", "Text", "User"
    )

    assert overall_success is False