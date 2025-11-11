from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import relationship

from db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    google_sub = Column(String(128), unique=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255))
    picture = Column(String(512))
    locale = Column(String(32))
    drive_folder_id = Column(String(128))
    drive_folder_link = Column(String(512))
    login_csv_file_id = Column(String(128))
    login_csv_file_name = Column(String(255), default="login_history.csv")
    login_csv_web_view_link = Column(String(512))
    location_cache = Column(JSON)
    last_login_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    photo_capture_enabled = Column(Boolean, default=False, nullable=False)

    uploads = relationship("PdfUpload", back_populates="user", cascade="all, delete-orphan")
    logins = relationship("LoginEvent", back_populates="user", cascade="all, delete-orphan")


class PdfUpload(Base):
    __tablename__ = "pdf_uploads"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    drive_file_id = Column(String(128))
    drive_web_view_link = Column(String(512))
    drive_web_content_link = Column(String(512))
    file_size = Column(Integer)
    sha256_hash = Column(String(128))

    user = relationship("User", back_populates="uploads")
    __table_args__ = (
        UniqueConstraint("user_id", "drive_file_id", name="uq_user_drive_file"),
    )


class LoginEvent(Base):
    __tablename__ = "login_events"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    ip_address = Column(String(64))
    user_agent = Column(Text)
    location = Column(JSON)

    user = relationship("User", back_populates="logins")


class DailyUploadStat(Base):
    __tablename__ = "daily_upload_stats"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    upload_count = Column(Integer, default=0, nullable=False)

    user = relationship("User")
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_user_date"),
    )


class PhotoCaptureEvent(Base):
    __tablename__ = "photo_capture_events"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    context = Column(String(32))  # e.g., login or upload
    drive_file_id = Column(String(128))
    drive_web_view_link = Column(String(512))

    user = relationship("User")
