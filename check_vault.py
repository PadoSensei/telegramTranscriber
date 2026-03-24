import os
import sys
import tempfile
import shutil
from git import Repo
from config import VAULT_CONFIGS

def find_config_by_name(target_name):
    """Searches VAULT_CONFIGS for a entry matching the provided name."""
    for user_id, cfg in VAULT_CONFIGS.items():
        if cfg['name'].lower() == target_name.lower():
            return cfg
    return None

def print_vault_tree(cfg):
    """Clones the repo to a temp folder and prints the folder structure."""
    # Build authenticated URL
    auth_url = cfg["repo_url"].replace("https://", f"https://{cfg['username']}:{cfg['token']}@")
    tmp_dir = tempfile.mkdtemp()
    
    print(f"\n{'='*50}")
    print(f"📡  CONNECTING TO VAULT: {cfg['name']}")
    print(f"🔗  REPO: {cfg['repo_url']}")
    print(f"{'='*50}\n")

    try:
        # Shallow clone to save bandwidth
        Repo.clone_from(auth_url, tmp_dir, depth=1)
        
        print("📂 VAULT STRUCTURE:")
        for root, dirs, files in os.walk(tmp_dir):
            # Ignore git internals
            if '.git' in dirs:
                dirs.remove('.git')
            
            level = root.replace(tmp_dir, '').count(os.sep)
            indent = ' ' * 4 * (level)
            folder_name = os.path.basename(root)
            
            # Print the directory name
            if folder_name:
                print(f"{indent}├── {folder_name}/")
            else:
                print("root/")

            # Print the files inside the directory
            subindent = ' ' * 4 * (level + 1)
            for f in files:
                if not f.startswith('.'): # Hide .gitkeep and hidden files
                    print(f"{subindent}📄 {f}")
        print(f"\n{'='*50}")
        print("✅ Check Complete.")
        
    except Exception as e:
        print(f"❌ Error accessing vault: {e}")
    finally:
        shutil.rmtree(tmp_dir)

if __name__ == "__main__":
    # Check if a name was provided via command line
    if len(sys.argv) > 1:
        name = sys.argv[1]
    else:
        # Fallback to interactive input if no argument provided
        name = input("Enter the name of the vault to check (e.g., PadoSensei or Ludmila): ")

    config = find_config_by_name(name)
    
    if config:
        print_vault_tree(config)
    else:
        print(f"❌ No vault configuration found for name: '{name}'")
        print(f"Available names: {', '.join([c['name'] for c in VAULT_CONFIGS.values()])}")