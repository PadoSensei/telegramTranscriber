import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()
SERVICE_ACCOUNT_FILE = os.getenv("KATIE_OD_GOOGLE_DRIVE")
# PASTE THE ID OF THE DOC YOU JUST CREATED BELOW
DOCUMENT_ID = "1qXYNymYag8a4AyTdEygQNKfOkLoDd1Ep7ZUMslV7D8Q" 

SCOPES = ['https://www.googleapis.com/auth/documents']

def test_append_to_doc():
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        
        # We use 'docs' instead of 'drive' here
        service = build('docs', 'v1', credentials=creds)

        # Prepare the text to append
        text_to_append = "\n\n🚀 2nd Brain Test: Successfully appended at " + os.popen('date').read()
        
        requests = [
            {
                'insertText': {
                    'location': {'index': 1}, # Inserts at the start of the doc
                    'text': text_to_append
                }
            }
        ]

        print(f"📝 Attempting to append to Doc: {DOCUMENT_ID}...")
        
        service.documents().batchUpdate(
            documentId=DOCUMENT_ID, 
            body={'requests': requests}
        ).execute()

        print(f"✅ Success! Open the Google Doc '{DOCUMENT_ID}' to see the update.")

    except Exception as e:
        print(f"❌ Append Failed: {e}")

if __name__ == '__main__':
    test_append_to_doc()