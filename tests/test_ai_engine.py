import pytest
from unittest.mock import MagicMock, AsyncMock
from ai_engine import AIEngine

@pytest.fixture
def ai_engine(mocker):
    mocker.patch("google.generativeai.configure")
    mocker.patch("google.generativeai.GenerativeModel")
    return AIEngine()

@pytest.mark.asyncio
async def test_structured_output_split(ai_engine, mocker):
    # Mock Gemini's response
    mock_response = MagicMock()
    mock_response.text = "This is the story.---ANALYSIS_SPLIT---This is the analysis."
    ai_engine.model.generate_content_async = AsyncMock(return_value=mock_response)

    story, analysis = await ai_engine.get_structured_output("raw input", "Katie", is_star=True)
    
    assert story == "This is the story."
    assert analysis == "This is the analysis."

@pytest.mark.asyncio
async def test_structured_output_no_split(ai_engine, mocker):
    mock_response = MagicMock()
    mock_response.text = "Just a regular response."
    ai_engine.model.generate_content_async = AsyncMock(return_value=mock_response)

    story, analysis = await ai_engine.get_structured_output("raw input", "Katie", is_star=False)
    
    assert story == "Just a regular response."
    assert "No separate analysis" in analysis
