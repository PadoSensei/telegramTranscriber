import os
from dotenv import load_dotenv
from schema import UserConfig

load_dotenv()

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
# Maps Telegram User IDs to their specific GitHub Repositories 
# and their unique folder structures (Category Maps).

VAULT_CONFIGS = {
    
 # --------------------------------------
    # LUDMILA'S VAULT (2ndBrain Repo)
    # --------------------------------------
    7187182620: {  
        "name": "Ludmila",
        "repo_url": os.getenv("LUDMILA_REPO_URL"),
        "token":    os.getenv("LUDMILA_TOKEN"),
        "username": os.getenv("LUDMILA_NAME"),
        
        # SYNCED MAPPING: Matches her "📥 TelegramCaptures" structure
        "category_map": {
            "Zil": "03_Projects/Zil/📥 TelegramCaptures",
            "Feena": "03_Projects/Feena/📥 TelegramCaptures",
            "AISolutions": "03_Projects/AISolutions/📥 TelegramCaptures",
            
            # Additional routes based on her root folders
            "Study": "01_Study",
            "Report": "02_Reports",
            "Inbox": "00_Inbox"
        }
    },
    
    # --------------------------------------
    # PADOSENSEI'S VAULT (DevBrain Repo)
    # --------------------------------------
    6426489405: {  
        "name": "PadoSensei",
        "repo_url": os.getenv("PADO_REPO_URL"),
        "token": os.getenv("PADO_TOKEN"),
        "username": os.getenv("PADO_NAME"),
        
        # Pado's specific project routing (Projects live in '03_Projects')
        "category_map": {
            "Zil": "03_Projects",
            "BJJDev": "03_Projects",
            "Feena": "03_Projects",
            "Project2ndBrain": "03_Projects",
            "EduCanoe": "03_Projects",
            "DroneDev": "03_Projects",
            "Guild": "03_Projects",
            
            # Future-proofing for your other folders:
            "ScrimbaBackendCourse": "01_Study",
            "Investing": "02_Money"
        }
    },


    # --------------------------------------
    # KATIE O'DONOGHUE'S VAULT (Bloom Interview Prep)
    # --------------------------------------
    
    # If she messages the bot, the logs will show "Unauthorized access attempt by ID: XXXXXXX"
    8630747869: {  
        "name": "katie_OD",
        "repo_url": os.getenv("KATIE_OD_REPO_URL"),
        "token": os.getenv("KATIE_OD_TOKEN"),
        "username": os.getenv("KATIE_OD_NAME"),
        "gdrive_doc_id": os.getenv("KATIE_OD_GOOGLE_DRIVE"),
        
        # Folder structure designed for Bloom & NotebookLM
        "category_map": {
            "Star": "01_Projects/Bloom_Prep/STAR_Story_Bank",
            "Bloom": "01_Projects/Bloom_Prep",
            "Source": "01_Projects/Bloom_Prep/NotebookLM_Sources",
            "Inbox": "00_Inbox",
            "Progress": "Progress_Summaries"
        }
    }
}

# Keep this list dynamic for the @restricted security decorator in main.py
ALLOWED_IDS = list(VAULT_CONFIGS.keys())

def get_user_config(user_id: int) -> UserConfig:
    """
    Retrieves and validates user configuration using Pydantic.
    """
    cfg_dict = VAULT_CONFIGS.get(user_id)
    if not cfg_dict:
        raise ValueError(f"User {user_id} not authorized.")

    # Create a copy to avoid mutating the global VAULT_CONFIGS directly before validation
    cfg_to_validate = cfg_dict.copy()

    # We can also inject per-user GCP content from env if it's missing in the dict
    user_name = cfg_to_validate.get("name")
    if user_name and not cfg_to_validate.get("gcp_json_content"):
        # Fallback to a naming convention or a specific env var if needed
        env_key = f"{user_name.upper()}_GCP_JSON"
        cfg_to_validate["gcp_json_content"] = os.getenv(env_key)

    return UserConfig(**cfg_to_validate)
