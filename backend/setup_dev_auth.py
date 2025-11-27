import os
import json
# Allow HTTP for local testing (fixes "OAuth 2 MUST utilize https" error)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/drive.file'
]

def main():
    print("="*60)
    print("StudyAI - Developer Storage Setup")
    print("="*60)
    print("This script will generate a Refresh Token so the app can")
    print("upload files to YOUR Google Drive (as the developer).")
    print("-" * 60)

    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET is missing in .env")
        return

    # Create the flow
    config = {
        "installed": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:5000/auth/google/callback"]
        }
    }

    flow = InstalledAppFlow.from_client_config(config, SCOPES)
    flow.redirect_uri = "http://localhost:5000/auth/google/callback"
    
    print("\n1. A browser window will open.")
    print("2. Log in with the Google Account where you want to store files.")
    print("3. Allow access to Google Drive.")
    print("4. You will be redirected to a URL starting with http://localhost:5000/...")
    print("5. COPY THE ENTIRE URL from the address bar and paste it below.")
    print("\nLaunching browser...")
    
    auth_url, _ = flow.authorization_url(prompt='consent')
    
    import webbrowser
    webbrowser.open(auth_url)
    
    print(f"\nIf browser doesn't open, visit this URL:\n{auth_url}\n")
    
    code = input("Paste the full redirect URL here: ").strip()
    
    try:
        flow.fetch_token(authorization_response=code)
        creds = flow.credentials
    except Exception as e:
        print(f"\n[!] Failed to exchange code: {e}")
        return

    print("\n" + "="*60)
    print("SUCCESS! Here is your Refresh Token:")
    print("="*60)
    print(f"\n{creds.refresh_token}\n")
    print("="*60)
    print("INSTRUCTIONS:")
    print("1. Copy the token above.")
    print("2. Open your backend/.env file.")
    print("3. Add a new line:")
    print(f"GOOGLE_DEVELOPER_REFRESH_TOKEN={creds.refresh_token}")
    print("4. Save the file and restart the app.")
    print("="*60)

if __name__ == '__main__':
    main()
