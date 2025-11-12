from __future__ import annotations

import io
import json
from typing import Any, Dict, Optional

import os
from google.oauth2 import service_account
from googleapiclient.discovery import build  # type: ignore[import-not-found]
from googleapiclient.errors import HttpError  # type: ignore[import-not-found]
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload  # type: ignore[import-not-found]

DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.file",
]

_drive_service_cache = None


def _load_credentials():
    sa_info = None
    env_json = (os.getenv("GOOGLE_SERVICE_ACCOUNT_INFO") or "").strip()
    if env_json:
        try:
            sa_info = json.loads(env_json)
        except json.JSONDecodeError:
            pass
    sa_file = (os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE") or "").strip()
    if not sa_info and sa_file:
        with open(sa_file, "r", encoding="utf-8") as fh:
            sa_info = json.load(fh)
    if not sa_info:
        return None
    return service_account.Credentials.from_service_account_info(sa_info, scopes=DRIVE_SCOPES)


def get_drive_service():
    global _drive_service_cache
    if _drive_service_cache is not None:
        return _drive_service_cache

    creds = _load_credentials()
    if not creds:
        return None
    _drive_service_cache = build("drive", "v3", credentials=creds, cache_discovery=False)
    return _drive_service_cache


def ensure_user_folder(service, user_email: str, user_name: Optional[str] = None) -> Optional[Dict[str, str]]:
    root_folder_id = (os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID") or "").strip()
    if not root_folder_id:
        return None

    # Preferred naming: "<Name> (<email>)"; legacy: "<email>"
    preferred_name_raw = f"{user_name} ({user_email})" if user_name else user_email
    preferred_name = preferred_name_raw.replace("'", "\\'")
    legacy_name = user_email.replace("'", "\\'")

    query = (
        "mimeType='application/vnd.google-apps.folder' and trashed=false "
        f"and (name='{preferred_name}' or name='{legacy_name}') and '{root_folder_id}' in parents"
    )
    response = service.files().list(
        q=query,
        spaces="drive",
        fields="files(id, name, webViewLink)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
    ).execute()
    files = response.get("files", [])
    if files:
        # Prefer the correctly named folder if both exist
        preferred = next((f for f in files if f.get("name") == preferred_name_raw), None)
        folder = preferred or files[0]
        return {
            "id": folder["id"],
            "link": folder.get("webViewLink"),
        }

    metadata = {
        "name": preferred_name_raw,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [root_folder_id],
    }
    if user_name:
        metadata["description"] = f"StudyAI uploads for {user_name}"

    folder = service.files().create(body=metadata, fields="id, webViewLink", supportsAllDrives=True).execute()
    return {
        "id": folder["id"],
        "link": folder.get("webViewLink"),
    }


def upload_pdf(service, folder_id: str, filename: str, file_bytes: bytes, mimetype: str = "application/pdf") -> Dict[str, Any]:
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mimetype, resumable=False)
    metadata = {
        "name": filename,
        "parents": [folder_id],
        "mimeType": mimetype,
    }
    file = (
        service.files()
        .create(body=metadata, media_body=media, fields="id, name, webViewLink, webContentLink", supportsAllDrives=True)
        .execute()
    )
    return file


def download_file(service, file_id: str) -> bytes:
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    return fh.getvalue()


def upload_text_file(
    service,
    folder_id: str,
    filename: str,
    content: str,
    existing_file_id: Optional[str] = None,
    mimetype: str = "text/csv",
) -> Dict[str, Any]:
    media = MediaIoBaseUpload(io.BytesIO(content.encode("utf-8")), mimetype=mimetype, resumable=False)
    metadata = {
        "name": filename,
        "parents": [folder_id],
        "mimeType": mimetype,
    }
    if existing_file_id:
        file = (
            service.files()
            .update(
                fileId=existing_file_id,
                media_body=media,
                body={"name": filename},
                fields="id, name, webViewLink, webContentLink",
                supportsAllDrives=True,
            )
            .execute()
        )
    else:
        file = (
            service.files()
            .create(body=metadata, media_body=media, fields="id, name, webViewLink, webContentLink", supportsAllDrives=True)
            .execute()
        )
    return file
