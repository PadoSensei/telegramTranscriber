import pytest
from unittest.mock import MagicMock, AsyncMock
from processor import TaskProcessor
from schema import UserConfig

@pytest.fixture
def mock_user_config():
    return UserConfig(
        name="Katie",
        repo_url="https://github.com/mock/repo",
        token="mock_token",
        username="katieOD",
        gdrive_doc_id="mock_doc_id",
        category_map={"Star": "01_Projects/Bloom_Prep/STAR_Story_Bank"}
    )

@pytest.fixture
def processor(mocker, mock_user_config):
    # Mock components to isolate TaskProcessor logic
    mocker.patch("processor.AIEngine")
    mocker.patch("processor.GoogleManager")
    mocker.patch("processor.VaultManager")
    return TaskProcessor(mock_user_config)

@pytest.mark.asyncio
async def test_run_sync_stack_success(processor, mocker):
    """Verifies that for a user with Google enabled, both syncs are called."""
    # 1. Setup Mocks
    processor.ai.get_structured_output.return_value = ("Clean Story", "Analysis")
    
    processor.vault.push_to_obsidian.return_value = True
    processor.google.sync_to_doc = mocker.AsyncMock(return_value=True)

    # 2. Execute
    clean, analysis, git_success, google_success = await processor.run_sync_stack(
        category="STAR_Story_Bank", 
        project="Tullamore_Launch", 
        text="I did things"
    )

    # 3. Assertions
    assert git_success is True
    assert google_success is True
    processor.vault.push_to_obsidian.assert_called_once()
    processor.google.sync_to_doc.assert_called_once()

@pytest.mark.asyncio
async def test_run_sync_stack_paddy_no_google(mocker):
    """Verifies that for a user without Google, only GitHub is called."""
    paddy_config = UserConfig(
        name="Paddy",
        repo_url="https://github.com/mock/repo",
        token="mock_token",
        username="PadoSensei",
        gdrive_doc_id=None,
        category_map={"Inbox": "00_Inbox"}
    )
    
    mocker.patch("processor.AIEngine")
    mocker.patch("processor.GoogleManager")
    mocker.patch("processor.VaultManager")
    
    processor = TaskProcessor(paddy_config)
    processor.ai.get_structured_output.return_value = ("Paddy Clean", "Analysis")
    processor.vault.push_to_obsidian.return_value = True
    processor.google.sync_to_doc = mocker.AsyncMock(return_value=True)

    # 2. Execute
    _, _, git_success, google_success = await processor.run_sync_stack(
        category="00_Inbox", 
        project="Testing", 
        text="Hello"
    )

    # 3. Assertions
    assert git_success is True
    assert google_success is True # Defaults to True when no google sync is configured
    processor.vault.push_to_obsidian.assert_called_once()
    processor.google.sync_to_doc.assert_not_called()
