import os
from pathlib import Path
from dotenv import load_dotenv
from .schema import UserConfig

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_FILE_PATH = PROJECT_ROOT / "config" / "data" / "bot_state.json"

MEDIA_GROUP_DEBOUNCE_TIME = 1.5

# Global HTTP Timeouts for Heavy IO (Transcription downloads/Syncs)
HTTP_CONNECT_TIMEOUT = 20.0
HTTP_READ_TIMEOUT    = 60.0
HTTP_WRITE_TIMEOUT   = 20.0

# Security Guardrails
MAX_FILE_SIZE_MB = 20
FILE_TYPE_BLACKLIST = [
    '.exe', '.bat', '.cmd', '.sh', '.bin', '.dll', '.run', '.msi', '.apk', '.jar', # Executables
    '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', # Hazardous archives
    '.dmg', '.iso', '.vhd', '.vmdk', # Disk images
    '.js', '.vbs', '.wsf', '.ps1', '.php', '.py', '.rb', '.pl', # Scripts
    '.docm', '.xlsm', '.pptm', '.rtf' # Macro-enabled files
]
MIME_TYPE_BLACKLIST = [
    'application/x-executable', 'application/x-sh', 'text/x-shellscript',
    'application/zip', 'application/x-rar-compressed', 'application/x-7z-compressed',
    'application/x-msdownload'
]

# ==========================================
# MULTI-TENANT VAULT CONFIGURATIONS
# ==========================================
# Maps Telegram User IDs to their specific GitHub Repositories.

VAULT_CONFIGS = {
    # LUDMILA'S VAULT
    7187182620: {  
        "name": "Ludmila",
        "repo_url": os.getenv("LUDMILA_REPO_URL", ""),
        "token":    os.getenv("LUDMILA_TOKEN", ""),
        "username": os.getenv("LUDMILA_NAME", ""),
        "category_map": {}, 
        "gdrive_doc_id": None
    },
    
    # PADOSENSEI'S VAULT
    6426489405: {  
        "name": "PadoSensei",
        "repo_url": os.getenv("PADO_REPO_URL"),
        "token": os.getenv("PADO_TOKEN"),
        "username": os.getenv("PADO_NAME"),
        "category_map": {}, 
        "gdrive_doc_id": None
    },

    # KATIE O'DONOGHUE'S VAULT
    8630747869: {  
        "name": "katie_OD",
        "repo_url": os.getenv("KATIE_OD_REPO_URL"),
        "token": os.getenv("KATIE_OD_TOKEN"),
        "username": os.getenv("KATIE_OD_NAME"),
        "gdrive_doc_id": None,
        "category_map": {}
    }
}

ALLOWED_IDS = list(VAULT_CONFIGS.keys())

def get_user_config(user_id: int) -> UserConfig:
    """
    Retrieves and validates user configuration using Pydantic.
    """
    cfg_dict = VAULT_CONFIGS.get(user_id)
    if not cfg_dict:
        raise ValueError(f"User {user_id} not authorized.")

    return UserConfig(**cfg_dict)
