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

    @validator("category_map")
    def validate_inbox(cls, v):
        if "Inbox" not in v and "00_Inbox" not in v.values():
            # We strongly suggest an Inbox for fallbacks
            pass
        return v

class MultiTenantConfig(BaseModel):
    vaults: Dict[int, UserConfig]
