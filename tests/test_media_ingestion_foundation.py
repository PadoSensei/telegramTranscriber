import pytest
from unittest.mock import MagicMock
from datetime import datetime
from bot_utils import validate_media_file
from templates import MediaTemplate
from config import MAX_FILE_SIZE_MB

def test_validate_media_file_photo():
    message = MagicMock()
    message.document = None
    message.video = None
    photo = MagicMock()
    photo.file_id = "photo_id"
    photo.file_size = 1024 * 1024 # 1MB
    message.photo = [photo] # Simplification, list of PhotoSize

    is_valid, file_info, error_message = validate_media_file(message)

    assert is_valid is True
    assert file_info['file_id'] == "photo_id"
    assert file_info['mime_type'] == "image/jpeg"
    assert file_info['file_name'].startswith("IMG_")
    assert file_info['file_name'].endswith(".jpg")
    assert error_message is None

def test_validate_media_file_too_large():
    message = MagicMock()
    message.photo = None
    message.video = None
    doc = MagicMock()
    doc.file_id = "doc_id"
    doc.file_name = "large_file.pdf"
    doc.mime_type = "application/pdf"
    doc.file_size = (MAX_FILE_SIZE_MB + 1) * 1024 * 1024
    message.document = doc

    is_valid, file_info, error_message = validate_media_file(message)

    assert is_valid is False
    assert "too large" in error_message

def test_validate_media_file_blacklisted_extension():
    message = MagicMock()
    message.photo = None
    message.video = None
    doc = MagicMock()
    doc.file_id = "doc_id"
    doc.file_name = "malicious.exe"
    doc.mime_type = "application/x-msdownload"
    doc.file_size = 1024
    message.document = doc

    is_valid, file_info, error_message = validate_media_file(message)

    assert is_valid is False
    assert "not supported" in error_message
    assert ".exe" in error_message

def test_media_template():
    filename = "IMG_20240507_143510.jpg"
    original_name = "my_photo.jpg"
    mime_type = "image/jpeg"
    file_size = 1024 * 1024
    caption = "A beautiful sunset"
    timestamp = "2024-05-07 14:35:10"

    content = MediaTemplate.get_metadata_content(
        filename, original_name, mime_type, file_size, caption, timestamp
    )

    assert 'original_name: "my_photo.jpg"' in content
    assert 'mime_type: image/jpeg' in content
    assert f'![[{filename}]]' in content
    assert "## 📝 Caption" in content
    assert caption in content
