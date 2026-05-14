class MediaIngestionError(Exception):
    """Base exception for all media ingestion related errors."""
    pass

class GitPersistenceError(MediaIngestionError):
    """Raised when there is an error during Git operations or file writes to the vault."""
    pass

class TelegramDownloadError(MediaIngestionError):
    """Raised when there is an error downloading a file from Telegram."""
    pass
