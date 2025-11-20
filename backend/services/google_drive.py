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
    drive_user_mode = (os.getenv("DRIVE_USER_MODE", "false").lower() == "true")
    shared_drive_id = (os.getenv("GOOGLE_DRIVE_SHARED_DRIVE_ID") or "").strip()
    if not root_folder_id:
        # In user OAuth mode, default to the user's My Drive root
        if drive_user_mode:
            root_folder_id = 'root'
        else:
            return None

    # Preferred naming: "<Name> (<email>)"; legacy: "<email>"
    preferred_name_raw = f"{user_name} ({user_email})" if user_name else user_email
    preferred_name = preferred_name_raw.replace("'", "\\'")
    legacy_name = user_email.replace("'", "\\'")

    query = (
        "mimeType='application/vnd.google-apps.folder' and trashed=false "
        f"and (name='{preferred_name}' or name='{legacy_name}') and '{root_folder_id}' in parents"
    )
    list_kwargs: Dict[str, Any] = dict(
        q=query,
        spaces="drive",
        fields="files(id, name, webViewLink)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
    )
    # When using a shared drive, specify corpora/driveId for more consistent results
    if shared_drive_id:
        list_kwargs["driveId"] = shared_drive_id
        list_kwargs["corpora"] = "drive"
        list_kwargs["includeItemsFromAllDrives"] = True
        list_kwargs["supportsAllDrives"] = True
    
    try:
        response = service.files().list(**list_kwargs).execute()
    except HttpError as e:
        # If the root folder is not found (404) and we are in user mode, fallback to 'root'
        if e.resp.status == 404 and drive_user_mode and root_folder_id != 'root':
            print(f"[Drive] Root folder {root_folder_id} not found/accessible. Falling back to 'root' (My Drive).")
            root_folder_id = 'root'
            # Re-build query with 'root'
            query = (
                "mimeType='application/vnd.google-apps.folder' and trashed=false "
                f"and (name='{preferred_name}' or name='{legacy_name}') and 'root' in parents"
            )
            list_kwargs['q'] = query
            response = service.files().list(**list_kwargs).execute()
        else:
            raise e

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


def find_named_file(service, folder_id: str, filename: str) -> Optional[Dict[str, Any]]:
    shared_drive_id = (os.getenv("GOOGLE_DRIVE_SHARED_DRIVE_ID") or "").strip()
    safe_name = filename.replace("'", "\\'")
    query = "name='{}' and '{}' in parents and trashed=false".format(safe_name, folder_id)
    list_kwargs: Dict[str, Any] = dict(
        q=query,
        spaces="drive",
        fields="files(id, name, mimeType, webViewLink)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        pageSize=1,
    )
    if shared_drive_id:
        list_kwargs["driveId"] = shared_drive_id
        list_kwargs["corpora"] = "drive"
    resp = service.files().list(**list_kwargs).execute()
    files = resp.get("files", [])
    return files[0] if files else None


def read_text_file(service, file_id: str) -> str:
    data = download_file(service, file_id)
    return data.decode("utf-8")


def load_user_json(service, folder_id: str) -> Dict[str, Any]:
    try:
        meta = find_named_file(service, folder_id, "user.json")
        if not meta:
            return {}
        content = read_text_file(service, meta["id"])  # type: ignore[index]
        import json as _json
        return _json.loads(content)
    except Exception:
        return {}


def save_user_json(service, folder_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    import json as _json
    existing = find_named_file(service, folder_id, "user.json")
    return upload_text_file(
        service,
        folder_id,
        "user.json",
        _json.dumps(data, ensure_ascii=False, indent=2),
        existing_file_id=(existing or {}).get("id"),
        mimetype="application/json",
    )


def list_folder_files(service, folder_id: str, page_size: int = 100) -> Dict[str, Any]:
    shared_drive_id = (os.getenv("GOOGLE_DRIVE_SHARED_DRIVE_ID") or "").strip()
    list_kwargs: Dict[str, Any] = dict(
        q=f"'{folder_id}' in parents and trashed=false",
        spaces="drive",
        fields="files(id,name,mimeType,webViewLink,createdTime,modifiedTime,size)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        pageSize=page_size,
        orderBy="modifiedTime desc",
    )
    if shared_drive_id:
        list_kwargs["driveId"] = shared_drive_id
        list_kwargs["corpora"] = "drive"
    resp = service.files().list(**list_kwargs).execute()
    return {"files": resp.get("files", [])}


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
