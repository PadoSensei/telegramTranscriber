import os
from dotenv import load_dotenv
from vault_manager import VaultManager

# 1. Load your real credentials
load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO_URL = os.getenv("GITHUB_REPO_URL")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")

def run_integration_test():
    print("🔍 Starting Live Vault Integration Test...")
    
    # Check if env vars are present
    if not all([GITHUB_TOKEN, GITHUB_REPO_URL, GITHUB_USERNAME]):
        print("❌ Error: Missing GitHub credentials in .env")
        return

    # 2. Initialize the real VaultManager
    vault = VaultManager(GITHUB_REPO_URL, GITHUB_TOKEN, GITHUB_USERNAME)
    
    # 3. Define dummy data
    test_project = "Feena" # Ensure this folder exists in your repo
    test_transcript = "This is a manual integration test transcript."
    test_analysis = "### Summary\n- Integration: Successful\n- Status: Verified"

    print(f"🚀 Attempting to push to project: {test_project}...")
    
    # 4. Execute the push
    success = vault.push_to_obsidian(test_project, test_transcript, test_analysis)
    
    if success:
        print("\n" + "="*40)
        print("✅ SUCCESS: Data pushed to GitHub!")
        print(f"📂 Check folder: 01_Projects/{test_project}/📥 TelegramCaptures/")
        print("="*40)
        print("\nNext Steps:")
        print("1. Open your GitHub repo in the browser to confirm the file exists.")
        print("2. Open Obsidian and wait for the 'Git' plugin to pull the changes.")
    else:
        print("\n" + "!"*40)
        print("❌ FAILED: The push did not go through.")
        print("Check your GITHUB_TOKEN permissions and GITHUB_REPO_URL.")
        print("!"*40)

if __name__ == "__main__":
    run_integration_test()