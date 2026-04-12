from pydantic import BaseModel, Field, validator
from typing import Dict, Optional

class UserConfig(BaseModel):
    name: str
    repo_url: str
    token: str
    username: str
    category_map: Dict[str, str]
    gdrive_doc_id: Optional[str] = None
    gcp_json_content: Optional[str] = None

    @validator("gdrive_doc_id")
    def validate_gdrive_doc_id(cls, v):
        if v is not None and len(v.strip()) == 0:
            raise ValueError("gdrive_doc_id cannot be an empty string")
        # Google Doc IDs are usually long alphanumeric strings (about 44 characters)
        if v and len(v) < 20:
             raise ValueError("gdrive_doc_id seems too short to be valid")
        return v

    @validator("category_map")
    def validate_inbox(cls, v):
        if "Inbox" not in v and "00_Inbox" not in v.values():
            # We strongly suggest an Inbox for fallbacks
            pass
        return v

class MultiTenantConfig(BaseModel):
    vaults: Dict[int, UserConfig]
