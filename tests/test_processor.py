import pytest
from unittest.mock import MagicMock, AsyncMock
from processor import TaskProcessor

@pytest.fixture
def processor(mocker):
    # Mock components to isolate TaskProcessor logic
    mocker.patch("processor.AIEngine")
    mocker.patch("processor.GoogleManager")
    return TaskProcessor()

@pytest.mark.asyncio
async def test_run_sync_stack_success(processor, mocker):
    """Verifies that for a user with Google enabled, both syncs are called."""
    # Mock Config
    mocker.patch("processor.VAULT_CONFIGS", {
        999999999: {
            "name": "Katie",
            "repo_url": "https://github.com/mock/repo",
            "token": "mock_token",
            "username": "katieOD",
            "gdrive_doc_id": "mock_doc_id",
            "category_map": {"Star": "01_Projects/Bloom_Prep/STAR_Story_Bank"}
        }
    })

    # 1. Setup Mocks
    processor.ai.get_structured_output.return_value = ("Clean Story", "Analysis")
    
    mock_vault_class = mocker.patch("processor.VaultManager")
    mock_vault_instance = mock_vault_class.return_value
    mock_vault_instance.push_to_obsidian.return_value = True
    
    processor.google.sync_to_doc = mocker.AsyncMock(return_value=True)

    # 2. Execute
    clean, analysis, overall_success = await processor.run_sync_stack(
        user_id=999999999, 
        category="STAR_Story_Bank", 
        project="Tullamore_Launch", 
        text="I did things", 
        user_name="Katie"
    )

    # 3. Assertions
    assert overall_success is True
    mock_vault_instance.push_to_obsidian.assert_called_once()
    processor.google.sync_to_doc.assert_called_once()

@pytest.mark.asyncio
async def test_run_sync_stack_paddy_no_google(processor, mocker):
    """Verifies that for a user without Google, only GitHub is called."""
    # Mock Config
    mocker.patch("processor.VAULT_CONFIGS", {
        6426489405: {
            "name": "Paddy",
            "repo_url": "https://github.com/mock/repo",
            "token": "mock_token",
            "username": "PadoSensei",
            "gdrive_doc_id": None,
            "category_map": {"Inbox": "00_Inbox"}
        }
    })

    processor.ai.get_structured_output.return_value = ("Paddy Clean", "Analysis")
    
    mock_vault_class = mocker.patch("processor.VaultManager")
    mock_vault_instance = mock_vault_class.return_value
    mock_vault_instance.push_to_obsidian.return_value = True
    
    processor.google.sync_to_doc = mocker.AsyncMock(return_value=True)

    # 2. Execute
    _, _, overall_success = await processor.run_sync_stack(
        user_id=6426489405, 
        category="00_Inbox", 
        project="Testing", 
        text="Hello", 
        user_name="Paddy"
    )

    # 3. Assertions
    assert overall_success is True
    mock_vault_instance.push_to_obsidian.assert_called_once()
    processor.google.sync_to_doc.assert_not_called()