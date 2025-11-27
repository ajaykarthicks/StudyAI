import os
from services.google_drive import get_drive_service

# Load env vars (since we are running this script directly, we need to load them if not already loaded by app)
# But app.py loads them. Let's just assume they are in env or we load them manually.
from dotenv import load_dotenv
load_dotenv()

def check_access():
    print("Checking Drive access...")
    service = get_drive_service()
    if not service:
        print("[!] Could not create Drive service. Check credentials.")
        return

    root_folder_id = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID")
    print(f"Root Folder ID: {root_folder_id}")
    
    if not root_folder_id:
        print("[!] GOOGLE_DRIVE_ROOT_FOLDER_ID is not set.")
        return

    try:
        # Try to get the folder metadata
        folder = service.files().get(fileId=root_folder_id, fields="id, name").execute()
        print(f"[OK] Successfully accessed folder: {folder.get('name')} ({folder.get('id')})")
    except Exception as e:
        print(f"[!] Failed to access root folder: {e}")
        print("Make sure the account you authenticated with has access to this folder ID.")

if __name__ == "__main__":
    check_access()
