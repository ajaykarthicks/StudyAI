from __future__ import annotations

import base64
import json
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from flask import request

from db import db_session
from models import DailyUploadStat, LoginEvent, PdfUpload, PhotoCaptureEvent, User, FeatureUsage


def decode_user_cookie() -> Optional[Dict[str, Any]]:
    user_cookie = request.cookies.get("user_data")
    if not user_cookie:
        return None
    try:
        user_json = base64.b64decode(user_cookie).decode("utf-8")
        return json.loads(user_json)
    except Exception:
        return None


def get_or_create_user(user_info: Dict[str, Any], drive_folder: Optional[Dict[str, str]] = None, drive_service: Any = None) -> User:
    with db_session() as session:
        user = session.query(User).filter_by(email=user_info["email"]).first()
        now = datetime.now(timezone.utc)
        
        # Check if picture changed or new user
        new_picture = user_info.get("picture")
        picture_changed = False
        
        if not user:
            user = User(
                google_sub=user_info.get("sub"),
                email=user_info.get("email"),
                name=user_info.get("name"),
                picture=new_picture,
                locale=user_info.get("locale"),
                last_login_at=now,
            )
            session.add(user)
            session.flush()
            picture_changed = True
        else:
            if user.picture != new_picture and new_picture:
                user.picture = new_picture
                picture_changed = True
            
            user.google_sub = user_info.get("sub") or user.google_sub
            user.name = user_info.get("name") or user.name
            user.locale = user_info.get("locale") or user.locale
            setattr(user, "last_login_at", now)

        if drive_folder:
            if drive_folder.get("id"):
                setattr(user, "drive_folder_id", drive_folder.get("id"))
            if drive_folder.get("link"):
                setattr(user, "drive_folder_link", drive_folder.get("link"))
        
        # Handle Profile Picture Upload to Drive
        if picture_changed and drive_service and user.drive_folder_id and new_picture:
            try:
                # Import here to avoid circular imports
                from services.google_drive import ensure_subfolder, upload_pdf
                import requests
                
                # Create/Get "Profile Pictures" folder
                pics_folder = ensure_subfolder(drive_service, user.drive_folder_id, "Profile Pictures")
                
                # Download image
                img_resp = requests.get(new_picture)
                if img_resp.status_code == 200:
                    # Upload to Drive
                    filename = f"profile_pic_{int(now.timestamp())}.jpg"
                    drive_file = upload_pdf(
                        drive_service, 
                        pics_folder['id'], 
                        filename, 
                        img_resp.content, 
                        mimetype="image/jpeg"
                    )
                    
                    # Update user with Drive Link
                    if drive_file.get('id'):
                        # Use local proxy to serve the image
                        # We use a relative URL which the frontend will resolve against the API base
                        user.picture = f"/api/file/proxy/{drive_file.get('id')}"
                        # Store file ID if we want to delete old ones later (optional)
            except Exception as e:
                print(f"[Profile Pic] Failed to upload profile picture to Drive: {e}")

        session.add(user)
        session.flush()
        session.refresh(user)
        return user


def update_user_drive_folder(user_id: int, folder_info: Dict[str, str]) -> None:
    with db_session() as session:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return
        if folder_info.get("id"):
            setattr(user, "drive_folder_id", folder_info.get("id"))
        if folder_info.get("link"):
            setattr(user, "drive_folder_link", folder_info.get("link"))
        session.add(user)


def update_login_csv_metadata(user_id: int, file_id: str, web_view_link: Optional[str]) -> None:
    with db_session() as session:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return
        setattr(user, "login_csv_file_id", file_id)
        if web_view_link:
            setattr(user, "login_csv_web_view_link", web_view_link)
        session.add(user)


def record_login_event(user: User, ip_address: Optional[str], user_agent: Optional[str], location: Optional[Dict[str, Any]], csv_row: Optional[str] = None) -> None:
    with db_session() as session:
        user = session.query(User).filter_by(id=user.id).first()
        if not user:
            return

        event = LoginEvent(
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            location=location,
        )
        if location:
            setattr(user, "location_cache", location)
        setattr(user, "last_login_at", datetime.now(timezone.utc))
        session.add(event)
        session.add(user)


def update_precise_location(user_id: int, precise_location: Dict[str, Any]) -> None:
    with db_session() as session:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return

        existing_cache: Dict[str, Any] = {}
        if isinstance(user.location_cache, dict):
            existing_cache = dict(user.location_cache)

        existing_cache["device"] = precise_location
        setattr(user, "location_cache", existing_cache)

        event = (
            session.query(LoginEvent)
            .filter(LoginEvent.user_id == user_id)
            .order_by(LoginEvent.timestamp.desc())
            .first()
        )
        if event:
            event_location: Dict[str, Any] = {}
            if isinstance(event.location, dict):
                event_location = dict(event.location)
            event_location["device"] = precise_location
            setattr(event, "location", event_location)
            session.add(event)

        session.add(user)


def record_pdf_upload(user: User, filename: str, drive_meta: Dict[str, Any], sha_hash: Optional[str], size_bytes: int) -> PdfUpload:
    with db_session() as session:
        user_id = getattr(user, "id", None)
        if not isinstance(user_id, int):
            raise ValueError("User does not have a valid id")

        db_user = session.query(User).filter_by(id=user_id).first()
        if not db_user:
            raise ValueError("User not found when recording PDF upload")

        upload = PdfUpload(
            user_id=db_user.id,
            filename=filename,
            drive_file_id=drive_meta.get("id"),
            drive_web_view_link=drive_meta.get("webViewLink"),
            drive_web_content_link=drive_meta.get("webContentLink"),
            file_size=size_bytes,
            sha256_hash=sha_hash,
        )
        session.add(upload)
        session.flush()

        event_date = upload.uploaded_at.date()
        stat = (
            session.query(DailyUploadStat)
            .filter_by(user_id=db_user.id, date=event_date)
            .with_for_update(of=DailyUploadStat)
            .first()
        )
        if not stat:
            stat = DailyUploadStat(user_id=db_user.id, date=event_date, upload_count=1)
            session.add(stat)
        else:
            setattr(stat, "upload_count", stat.upload_count + 1)  # type: ignore[attr-defined]
        session.flush()
        session.refresh(upload)
        return upload


def record_photo_capture(user_id: int, context: str, drive_meta: Dict[str, Any]) -> None:
    with db_session() as session:
        event = PhotoCaptureEvent(
            user_id=user_id,
            context=context,
            drive_file_id=drive_meta.get("id"),
            drive_web_view_link=drive_meta.get("webViewLink"),
        )
        session.add(event)


def get_authenticated_user() -> Optional[User]:
    user_info = decode_user_cookie()
    if not user_info:
        return None
    with db_session() as session:
        user = session.query(User).filter_by(email=user_info.get("email")).first()
        if user:
            session.expunge(user)
        return user


def serialize_user_for_admin(user: User, daily_stats: Dict[str, int], total_uploads: int, last_photo_link: Optional[str] = None) -> Dict[str, Any]:
    last_login = getattr(user, "last_login_at", None)
    last_heartbeat = getattr(user, "last_heartbeat", None)

    # Ensure timezone awareness for correct ISO formatting
    if last_login and last_login.tzinfo is None:
        last_login = last_login.replace(tzinfo=timezone.utc)
    if last_heartbeat and last_heartbeat.tzinfo is None:
        last_heartbeat = last_heartbeat.replace(tzinfo=timezone.utc)

    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "picture": user.picture,
        "lastLogin": last_login.isoformat() if last_login else None,
        "lastHeartbeat": last_heartbeat.isoformat() if last_heartbeat else None,
        "driveFolderLink": user.drive_folder_link,
        "photoCaptureEnabled": user.photo_capture_enabled,
        "location": user.location_cache,
        "totalUploads": total_uploads,
        "dailyUploads": daily_stats,
        "loginCsvLink": user.login_csv_web_view_link,
        "lastPhotoLink": last_photo_link,
    }


def set_photo_capture(user_id: int, enabled: bool) -> None:
    with db_session() as session:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return
        setattr(user, "photo_capture_enabled", enabled)
        session.add(user)


def update_heartbeat(user_id: int) -> None:
    with db_session() as session:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return
        setattr(user, "last_heartbeat", datetime.now(timezone.utc))
        session.add(user)


def record_feature_usage(user_id: int, feature_type: str, details: str, pdf_filename: Optional[str] = None) -> None:
    with db_session() as session:
        usage = FeatureUsage(
            user_id=user_id,
            feature_type=feature_type,
            details=details,
            pdf_filename=pdf_filename
        )
        session.add(usage)


def check_duplicate_pdf(sha256_hash: str) -> Optional[PdfUpload]:
    with db_session() as session:
        return session.query(PdfUpload).filter_by(sha256_hash=sha256_hash).first()


def get_active_users(seconds: int = 30) -> list[User]:
    with db_session() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=seconds)
        users = session.query(User).filter(User.last_heartbeat >= cutoff).all()
        # Expunge to use outside session
        for user in users:
            session.expunge(user)
        return users


# In-memory storage for live streaming states
# Format: { user_id: { "active": bool, "facingMode": str, "lastFrame": bytes, "updatedAt": datetime } }
STREAMING_STATES: Dict[int, Dict[str, Any]] = {}


def get_streaming_state(user_id: int) -> Optional[Dict[str, Any]]:
    return STREAMING_STATES.get(user_id)


def update_streaming_state(user_id: int, active: bool, facing_mode: str = "user") -> None:
    if user_id not in STREAMING_STATES:
        STREAMING_STATES[user_id] = {}
    STREAMING_STATES[user_id].update({
        "active": active,
        "facingMode": facing_mode,
        "updatedAt": datetime.now(timezone.utc)
    })


def update_streaming_frame(user_id: int, frame_data: bytes) -> None:
    if user_id in STREAMING_STATES:
        STREAMING_STATES[user_id]["lastFrame"] = frame_data
        STREAMING_STATES[user_id]["updatedAt"] = datetime.now(timezone.utc)
