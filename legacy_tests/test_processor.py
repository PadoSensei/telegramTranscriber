import pytest
from unittest.mock import MagicMock, AsyncMock
from telegram_transcriber.processor import TaskProcessor
from telegram_transcriber.schema import UserConfig

@pytest.fixture
def mock_user_config():
    return UserConfig(
        name="Katie",
        repo_url="https://github.com/mock/repo",
        token="mock_token",
        username="katieOD",
        gdrive_doc_id="1-mock-doc-id-longer-than-20-chars",
        category_map={"Star": "01_Projects/Bloom_Prep/STAR_Story_Bank"}
    )

@pytest.fixture
def processor(mocker):
    # Mock components to isolate TaskProcessor logic
    mocker.patch("telegram_transcriber.processor.AIEngine")
    mocker.patch("telegram_transcriber.processor.GoogleManager")
    mocker.patch("telegram_transcriber.processor.VaultManager")
    return TaskProcessor()

@pytest.mark.asyncio
async def test_run_sync_stack_success(processor, mock_user_config, mocker):
    """Verifies that for a user with Google enabled, both syncs are called."""
    # 1. Setup Mocks
    processor.ai.get_structured_output = AsyncMock(return_value=("Clean Story", "Analysis"))
    
    # We need to mock the classes that are instantiated locally in run_sync_stack
    mock_vault_cls = mocker.patch("telegram_transcriber.processor.VaultManager")
    mock_vault = mock_vault_cls.return_value
    mock_vault.push_to_obsidian.return_value = True

    mock_google_cls = mocker.patch("telegram_transcriber.processor.GoogleManager")
    mock_google = mock_google_cls.return_value
    mock_google.sync_to_doc = AsyncMock(return_value=True)

    # 2. Execute
    clean, analysis, git_success, google_success = await processor.run_sync_stack(
        user_cfg=mock_user_config,
        category="STAR_Story_Bank", 
        project="Tullamore_Launch", 
        text="I did things"
    )

    # 3. Assertions
    assert git_success is True
    assert google_success is True
    mock_vault.push_to_obsidian.assert_called_once()
    mock_google.sync_to_doc.assert_called_once()

@pytest.mark.asyncio
async def test_run_sync_stack_paddy_no_google(processor, mocker):
    """Verifies that for a user without Google, only GitHub is called."""
    paddy_config = UserConfig(
        name="Paddy",
        repo_url="https://github.com/mock/repo",
        token="mock_token",
        username="PadoSensei",
        gdrive_doc_id=None,
        category_map={"Inbox": "00_Inbox"}
    )
    
    processor.ai.get_structured_output = AsyncMock(return_value=("Paddy Clean", "Analysis"))
    
    mock_vault_cls = mocker.patch("telegram_transcriber.processor.VaultManager")
    mock_vault = mock_vault_cls.return_value
    mock_vault.push_to_obsidian.return_value = True

    mock_google_cls = mocker.patch("telegram_transcriber.processor.GoogleManager")
    mock_google = mock_google_cls.return_value
    mock_google.sync_to_doc = AsyncMock(return_value=True)

    # 2. Execute
    _, _, git_success, google_success = await processor.run_sync_stack(
        user_cfg=paddy_config,
        category="00_Inbox", 
        project="Testing", 
        text="Hello"
    )

    # 3. Assertions
    assert git_success is True
    assert google_success is True # Defaults to True when no google sync is configured
    mock_vault.push_to_obsidian.assert_called_once()
    mock_google.sync_to_doc.assert_not_called()
