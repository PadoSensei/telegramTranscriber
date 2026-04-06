import os
from dotenv import load_dotenv

load_dotenv()

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

