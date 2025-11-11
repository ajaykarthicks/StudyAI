from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from flask import request

from .db import db_session
from .models import DailyUploadStat, LoginEvent, PdfUpload, PhotoCaptureEvent, User


def decode_user_cookie() -> Optional[Dict[str, Any]]:
    user_cookie = request.cookies.get("user_data")
    if not user_cookie:
        return None
    try:
        user_json = base64.b64decode(user_cookie).decode("utf-8")
        return json.loads(user_json)
    except Exception:
        return None


def get_or_create_user(user_info: Dict[str, Any], drive_folder: Optional[Dict[str, str]] = None) -> User:
    with db_session() as session:
        user = session.query(User).filter_by(email=user_info["email"]).first()
        now = datetime.now(timezone.utc)
        if not user:
            user = User(
                google_sub=user_info.get("sub"),
                email=user_info.get("email"),
                name=user_info.get("name"),
                picture=user_info.get("picture"),
                locale=user_info.get("locale"),
                last_login_at=now,
            )
            session.add(user)
            session.flush()
        else:
            user.google_sub = user_info.get("sub") or user.google_sub
            user.name = user_info.get("name") or user.name
            user.picture = user_info.get("picture") or user.picture
            user.locale = user_info.get("locale") or user.locale
            setattr(user, "last_login_at", now)

        if drive_folder:
            if drive_folder.get("id"):
                setattr(user, "drive_folder_id", drive_folder.get("id"))
            if drive_folder.get("link"):
                setattr(user, "drive_folder_link", drive_folder.get("link"))

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


def record_login_event(user: User, ip_address: Optional[str], user_agent: Optional[str], location: Optional[Dict[str, str]], csv_row: Optional[str] = None) -> None:
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


def record_pdf_upload(user: User, filename: str, drive_meta: Dict[str, Any], sha_hash: Optional[str], size_bytes: int) -> PdfUpload:
    with db_session() as session:
        user = session.query(User).filter_by(id=user.id).first()
        if not user:
            raise ValueError("User not found when recording PDF upload")

        upload = PdfUpload(
            user_id=user.id,
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
            .filter_by(user_id=user.id, date=event_date)
            .with_for_update(of=DailyUploadStat)
            .first()
        )
        if not stat:
            stat = DailyUploadStat(user_id=user.id, date=event_date, upload_count=1)
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


def serialize_user_for_admin(user: User, daily_stats: Dict[str, int], total_uploads: int) -> Dict[str, Any]:
    last_login = getattr(user, "last_login_at", None)
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "lastLogin": last_login.isoformat() if last_login else None,
        "driveFolderLink": user.drive_folder_link,
        "photoCaptureEnabled": user.photo_capture_enabled,
        "location": user.location_cache,
        "totalUploads": total_uploads,
        "dailyUploads": daily_stats,
        "loginCsvLink": user.login_csv_web_view_link,
    }


def set_photo_capture(user_id: int, enabled: bool) -> None:
    with db_session() as session:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return
        setattr(user, "photo_capture_enabled", enabled)
        session.add(user)
