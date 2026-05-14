import pytest
import os
from unittest.mock import MagicMock, patch
from telegram_transcriber.google_manager import GoogleManager

# --- FIXTURES ---

@pytest.fixture
def google_manager():
    """Fixture to initialize the manager."""
    return GoogleManager()

@pytest.fixture
def mock_user_cfg():
    """Simulated user config for Katie."""
    # This ID must match your REAL Google Doc for the live test to pass
    return {
        "name": "Katie",
        "gdrive_doc_id": "1qXYNymYag8a4AyTdEygQNKfOkLoDd1Ep7ZUMslV7D8Q" 
    }

# --- 1. UNIT TEST (MOCKED) ---
# This is fast and runs without internet or real keys.

@pytest.mark.asyncio
async def test_sync_to_doc_mocked(google_manager, mock_user_cfg, mocker):
    """Verifies internal logic without hitting Google."""
    
    # Mock the API client chain
    mocker.patch("telegram_transcriber.google_manager.GoogleManager._get_service")
    google_manager._get_service = MagicMock()
    mock_service = MagicMock()
    mock_docs = MagicMock()
    mock_batch = MagicMock()
    
    google_manager._get_service.return_value = mock_service
    mock_service.documents.return_value = mock_docs
    mock_docs.batchUpdate.return_value = mock_batch
    mock_batch.execute.return_value = {"status": "success"}

    result = await google_manager.sync_to_doc(
        mock_user_cfg["gdrive_doc_id"], "Star", "Fake Content", "Fake Analysis", mock_user_cfg["name"]
    )

    assert result is True
    mock_docs.batchUpdate.assert_called_once()

# --- 2. INTEGRATION TEST (LIVE) ---
# This uses your REAL .env keys. 
# We add a decorator to skip it unless we explicitly want to run a live test.

@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("KATIE_OD_GOOGLE_DRIVE"), reason="No real Google credentials found in .env")
async def test_sync_to_doc_live(google_manager, mock_user_cfg):
    """REAL connection test using your .env and the actual Google Doc."""
    
    # This calls the actual GoogleManager logic
    result = await google_manager.sync_to_doc(
        mock_user_cfg["gdrive_doc_id"],
        "Live Integration Test", 
        "This is a test message from Pytest.", 
        "System is operational.",
        mock_user_cfg["name"]
    )

    assert result is True