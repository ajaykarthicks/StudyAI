from __future__ import annotations

from datetime import datetime
from typing import Optional, Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column

from db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    google_sub: Mapped[Optional[str]] = mapped_column(String(128), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    picture: Mapped[Optional[str]] = mapped_column(String(512))
    locale: Mapped[Optional[str]] = mapped_column(String(32))
    drive_folder_id: Mapped[Optional[str]] = mapped_column(String(128))
    drive_folder_link: Mapped[Optional[str]] = mapped_column(String(512))
    login_csv_file_id: Mapped[Optional[str]] = mapped_column(String(128))
    login_csv_file_name: Mapped[Optional[str]] = mapped_column(String(255), default="login_history.csv")
    login_csv_web_view_link: Mapped[Optional[str]] = mapped_column(String(512))
    location_cache: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime)
    streaming_command: Mapped[Optional[str]] = mapped_column(String(32))  # start, stop, capture_photo
    streaming_facing_mode: Mapped[Optional[str]] = mapped_column(String(32), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    photo_capture_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    uploads: Mapped[list[PdfUpload]] = relationship("PdfUpload", back_populates="user", cascade="all, delete-orphan")
    logins: Mapped[list[LoginEvent]] = relationship("LoginEvent", back_populates="user", cascade="all, delete-orphan")
    feature_usages: Mapped[list[FeatureUsage]] = relationship("FeatureUsage", back_populates="user", cascade="all, delete-orphan")
    notes: Mapped[list[Note]] = relationship("Note", back_populates="user", cascade="all, delete-orphan")


class PdfUpload(Base):
    __tablename__ = "pdf_uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    drive_file_id: Mapped[Optional[str]] = mapped_column(String(128))
    drive_web_view_link: Mapped[Optional[str]] = mapped_column(String(512))
    drive_web_content_link: Mapped[Optional[str]] = mapped_column(String(512))
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    sha256_hash: Mapped[Optional[str]] = mapped_column(String(128))

    user: Mapped[User] = relationship("User", back_populates="uploads")
    __table_args__ = (
        UniqueConstraint("user_id", "drive_file_id", name="uq_user_drive_file"),
    )


class LoginEvent(Base):
    __tablename__ = "login_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    location: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)

    user: Mapped[User] = relationship("User", back_populates="logins")


class DailyUploadStat(Base):
    __tablename__ = "daily_upload_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    date: Mapped[datetime] = mapped_column(Date, nullable=False)
    upload_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped[User] = relationship("User")
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_user_date"),
    )


class PhotoCaptureEvent(Base):
    __tablename__ = "photo_capture_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    context: Mapped[Optional[str]] = mapped_column(String(32))  # e.g., login or upload
    drive_file_id: Mapped[Optional[str]] = mapped_column(String(128))
    drive_web_view_link: Mapped[Optional[str]] = mapped_column(String(512))

    user: Mapped[User] = relationship("User")


class FeatureUsage(Base):
    __tablename__ = "feature_usages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    feature_type: Mapped[Optional[str]] = mapped_column(String(50))  # chat, summarize, quiz, flashcards
    details: Mapped[Optional[str]] = mapped_column(Text)  # JSON string or text description
    pdf_filename: Mapped[Optional[str]] = mapped_column(String(255))

    user: Mapped[User] = relationship("User", back_populates="feature_usages")


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    pdf_filename: Mapped[Optional[str]] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped[User] = relationship("User", back_populates="notes")


class StreamState(Base):
    __tablename__ = "stream_states"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), primary_key=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    command: Mapped[Optional[str]] = mapped_column(String(32))  # start, stop, capture_photo
    facing_mode: Mapped[str] = mapped_column(String(32), default="user")
    last_frame: Mapped[Optional[bytes]] = mapped_column(Text) # Storing as Base64 string (Text) is safer for some DBs, but LargeBinary is better. Let's use Text for base64 to be safe with drivers.
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped[User] = relationship("User")
