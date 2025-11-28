import os
import socket
from urllib.parse import urlparse
from contextlib import contextmanager
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import scoped_session, sessionmaker, declarative_base

# --- MONKEYPATCH: Force IPv4 globally ---
# This is required for Hugging Face Spaces + Supabase to avoid "Network is unreachable" (IPv6) errors.
# It filters out all IPv6 addresses from DNS lookups.
_original_getaddrinfo = socket.getaddrinfo

def _patched_getaddrinfo(*args, **kwargs):
    res = _original_getaddrinfo(*args, **kwargs)
    # Filter results to only include AF_INET (IPv4)
    return [r for r in res if r[0] == socket.AF_INET]

socket.getaddrinfo = _patched_getaddrinfo
print("[Init] Applied global IPv4-only monkeypatch for socket.getaddrinfo")
# ----------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///instance/studyai.db")

# Clean up DATABASE_URL (remove quotes if present)
if DATABASE_URL:
    DATABASE_URL = DATABASE_URL.strip().strip('"').strip("'")

# Fix for some Postgres providers (like Supabase/Heroku) using 'postgres://' instead of 'postgresql://'
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+pg8000://", 1)
    elif DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+pg8000://", 1)

print(f"[DB] Using DATABASE_URL: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else 'sqlite'}")

connect_args = {}

if DATABASE_URL.startswith("sqlite"):
    db_path = DATABASE_URL.replace("sqlite:///", "")
    directory = os.path.dirname(db_path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
    # SQLite needs this option when used with threads
    connect_args = {"check_same_thread": False}
elif "supabase.co" in DATABASE_URL:
    # pg8000 is pure Python and respects the socket monkeypatch, so we don't need the hostaddr hack anymore.
    # In fact, passing hostaddr to pg8000 might not be supported or might conflict.
    # We rely 100% on the socket monkeypatch above.
    pass

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = scoped_session(
    sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
)

Base = declarative_base()


def init_db() -> None:
    import models  # noqa: F401  Ensures models are registered

    if DATABASE_URL.startswith("sqlite"):
        _run_sqlite_migrations()

    try:
        Base.metadata.create_all(bind=engine)
    except OperationalError as exc:
        message = str(exc).lower()
        if "already exists" not in message:
            raise


def _run_sqlite_migrations() -> None:
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    if "users" not in existing_tables:
        return

    existing_columns = {col["name"] for col in inspector.get_columns("users")}
    statements = []

    if "drive_folder_id" not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN drive_folder_id VARCHAR(128)")
    if "drive_folder_link" not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN drive_folder_link VARCHAR(512)")
    if "login_csv_file_id" not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN login_csv_file_id VARCHAR(128)")
    if "login_csv_file_name" not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN login_csv_file_name VARCHAR(255) DEFAULT 'login_history.csv'")
    if "login_csv_web_view_link" not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN login_csv_web_view_link VARCHAR(512)")
    if "location_cache" not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN location_cache TEXT")
    if "photo_capture_enabled" not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN photo_capture_enabled BOOLEAN NOT NULL DEFAULT 0")
    if "last_heartbeat" not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN last_heartbeat DATETIME")

    if not statements:
        return

    with engine.begin() as connection:
        for stmt in statements:
            connection.execute(text(stmt))


@contextmanager
def db_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
