from pydantic import BaseModel, Field, field_validator
from typing import Dict, Optional

class UserConfig(BaseModel):
    """
    Configuration for an individual user's vault and external integrations.
    """
    name: str
    repo_url: str
    token: str
    username: str
    category_map: Dict[str, str]
    gdrive_doc_id: Optional[str] = None
    gcp_json_content: Optional[str] = None

    @field_validator("gdrive_doc_id")
    @classmethod
    def validate_gdrive_doc_id(cls, v: Optional[str]) -> Optional[str]:
        """
        Ensures the Google Drive ID is valid if provided.
        """
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("gdrive_doc_id cannot be an empty string")
            
            # Google Doc IDs are usually alphanumeric strings (about 44 chars).
            # Keeping your existing logic of 20 chars minimum.
            if len(stripped) < 20:
                raise ValueError("gdrive_doc_id seems too short to be valid")
            
            return stripped
        return v

    @field_validator("category_map")
    @classmethod
    def validate_inbox(cls, v: Dict[str, str]) -> Dict[str, str]:
        """
        Check for 'Inbox' existence. 
        Currently preserved as a pass-through logic per your original code.
        """
        if "Inbox" not in v and "00_Inbox" not in v.values():
            # Potential future logging: logger.warning("No Inbox found in category_map")
            pass
        return v

class MultiTenantConfig(BaseModel):
    """
    Root configuration mapping Telegram User IDs to their respective UserConfig.
    """
    vaults: Dict[int, UserConfig]