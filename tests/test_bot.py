import pytest
from unittest.mock import AsyncMock, MagicMock
from config import ALLOWED_IDS
import os

# --- Test 1: Config Logic ---
def test_allowed_ids_parsing():
    # Simulate the env variable
    raw_input = "12345, 67890 ,11223"
    parsed = [int(i.strip()) for i in raw_input.split(",") if i.strip()]
    
    assert parsed == [12345, 67890, 11223]
    assert isinstance(parsed[0], int)

# --- Test 2: Security Decorator ---
# We mock the Telegram 'Update' and 'Context' objects
@pytest.mark.asyncio
async def test_restricted_decorator_blocks_unauthorized():
    from main import restricted
    
    # Create a dummy function to protect
    @restricted
    async def dummy_func(update, context):
        return "Access Granted"

    # Mock an unauthorized user
    mock_update = MagicMock()
    mock_update.effective_user.id = 99999  # Not in ALLOWED_IDS
    mock_update.effective_chat.id = 123
    
    mock_context = MagicMock()
    mock_context.bot.send_message = AsyncMock()

    # Call the decorated function
    result = await dummy_func(mock_update, mock_context)

    # Assertions
    assert result is None  # Function should return early
    mock_context.bot.send_message.assert_called_once()
    assert "Access Denied" in mock_context.bot.send_message.call_args[1]['text']

@pytest.mark.asyncio
async def test_restricted_decorator_allows_authorized():
    from main import restricted
    
    # Create a dummy function to protect
    @restricted
    async def dummy_func(update, context):
        return "Access Granted"

    # Mock an authorized user (Use an ID that IS in your ALLOWED_IDS)
    mock_update = MagicMock()
    mock_update.effective_user.id = ALLOWED_IDS[0] 
    
    mock_context = MagicMock()

    # Call the decorated function
    result = await dummy_func(mock_update, mock_context)

    # Assertions
    assert result == "Access Granted"