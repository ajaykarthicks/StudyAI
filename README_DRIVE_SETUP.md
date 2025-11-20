# Google Drive Integration & Modes

This project supports two distinct modes for handling file storage and database operations.

## 1. Standard Mode (Database + Service Account)
*Default behavior.*
- **Database:** Requires a PostgreSQL database (configured via `DATABASE_URL`).
- **Storage:** Uses a Google Service Account to upload files to a specific Google Drive folder or Shared Drive.
- **Use Case:** Production deployments where a central service account manages all files.

## 2. Drive Only Mode (`DRIVE_ONLY_MODE=true`)
*Designed for lightweight or local usage without a database.*
- **Database:** **Disabled.** No SQL database is required. User sessions are stored in memory/filesystem, and user metadata is stored in a `user.json` file inside their Drive folder.
- **Storage:** Can operate in two sub-modes:

### A. Service Account Mode (Default)
- Uses the Service Account credentials (`GOOGLE_SERVICE_ACCOUNT_INFO`).
- **Limitation:** Service Accounts have a limited quota (15GB) unless they upload to a Shared Drive owned by a Workspace organization.
- **Config:**
  - `GOOGLE_SERVICE_ACCOUNT_INFO`: JSON string of credentials.
  - `GOOGLE_DRIVE_ROOT_FOLDER_ID`: The ID of the folder/Shared Drive to upload to.

### B. User OAuth Mode (`DRIVE_USER_MODE=true`)
- **Description:** The application acts on behalf of the *logged-in user*. Files are uploaded directly to the user's personal "My Drive".
- **Benefit:** Uses the user's own storage quota (e.g., your 2TB personal plan).
- **Config:**
  - `DRIVE_USER_MODE=true`
  - `GOOGLE_CLIENT_ID`: OAuth Client ID.
  - `GOOGLE_CLIENT_SECRET`: OAuth Client Secret.
  - `GOOGLE_DRIVE_ROOT_FOLDER_ID`: (Optional) If set, uploads to this specific folder. If invalid or unset, **automatically falls back to 'root' (My Drive)**.

## Configuration Variables (.env)

| Variable | Description | Required for User Mode? |
|----------|-------------|-------------------------|
| `DRIVE_ONLY_MODE` | Set to `true` to disable DB. | Yes |
| `DRIVE_USER_MODE` | Set to `true` to use personal Google Account storage. | Yes |
| `GOOGLE_CLIENT_ID` | From Google Cloud Console (OAuth 2.0 Client). | Yes |
| `GOOGLE_CLIENT_SECRET` | From Google Cloud Console. | Yes |
| `GOOGLE_DRIVE_ROOT_FOLDER_ID` | Target folder ID. Leave empty to use "My Drive" root. | No |
| `SECRET_KEY` | Flask session security key. | Yes |

## Troubleshooting

**Error: "File not found" (404)**
- **Cause:** You have a `GOOGLE_DRIVE_ROOT_FOLDER_ID` set in your `.env` that belongs to a different account (e.g., the Service Account) and your personal account cannot see it.
- **Fix:** The system now automatically detects this and falls back to your "My Drive" root. You can also remove `GOOGLE_DRIVE_ROOT_FOLDER_ID` from your `.env` file.

**Error: "Storage quota exceeded"**
- **Cause:** You are using Service Account mode (default) which has limited storage.
- **Fix:** Enable `DRIVE_USER_MODE=true` to use your personal storage.
