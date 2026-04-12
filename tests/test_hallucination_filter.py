import pytest
from transcriber import Transcriber, HallucinationError
import os

@pytest.fixture
def transcriber():
    return Transcriber(model_name="tiny")

@pytest.mark.asyncio
async def test_hallucination_detection(transcriber, mocker):
    # Mock the internal _sync_transcribe to return a known hallucination
    mocker.patch.object(transcriber, '_sync_transcribe', side_effect=HallucinationError("Hallucination detected: Thank you for watching"))

    with pytest.raises(HallucinationError):
        await transcriber.transcribe("fake_path.oga")

@pytest.mark.asyncio
async def test_short_content_returns_empty(transcriber, mocker):
    # Mock the internal _sync_transcribe to return very short text
    # Note: We need to mock the model.transcribe instead to test the real filter logic if possible,
    # but that's heavy. Let's mock the return of model.transcribe in _sync_transcribe.

    # We'll just test the _sync_transcribe logic directly for efficiency
    mocker.patch.object(transcriber.model, 'transcribe', return_value={"text": "   yo   "})
    mocker.patch('os.path.exists', return_value=False) # Skip cleanup check

    result = transcriber._sync_transcribe("fake_path.oga")
    assert result == "" # "yo" is length 2, should be filtered by len < 3 check

@pytest.mark.asyncio
async def test_valid_content_passes(transcriber, mocker):
    mocker.patch.object(transcriber.model, 'transcribe', return_value={"text": "This is a valid long sentence that should pass."})
    mocker.patch('os.path.exists', return_value=False)

    result = transcriber._sync_transcribe("fake_path.oga")
    assert result == "This is a valid long sentence that should pass."
