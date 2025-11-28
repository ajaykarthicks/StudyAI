import os
from types import SimpleNamespace
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  # Allow HTTPS and HTTP
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'   # Allow scopes to change (e.g. if user granted more previously)

import base64
import csv
import hashlib
import io
import json
import secrets
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from flask import Flask, request, jsonify, session, redirect, url_for, Response, stream_with_context
from flask_cors import CORS
from flask_session import Session
from dotenv import load_dotenv
import google_auth_oauthlib.flow
import PyPDF2
import requests
from groq import Groq
from openai import OpenAI
from sqlalchemy import func
from google.oauth2.credentials import Credentials as GoogleUserCredentials  # type: ignore[import-not-found]
from google.auth.transport.requests import Request as GoogleAuthRequest  # type: ignore[import-not-found]
from googleapiclient.discovery import build as gdrive_build  # type: ignore[import-not-found]

from db import init_db, db_session
from models import DailyUploadStat, LoginEvent, PdfUpload, PhotoCaptureEvent, User, FeatureUsage, Note
from services.google_drive import (
    download_file,
    ensure_user_folder,
    ensure_subfolder,
    find_named_file,
    get_drive_service,
    upload_pdf as drive_upload_pdf,
    upload_text_file,
    load_user_json,
    save_user_json,
    list_folder_files,
    read_text_file,
)
from services.location import lookup_location
from utils import (
    decode_user_cookie,
    get_authenticated_user,
    get_or_create_user,
    record_login_event,
    record_pdf_upload,
    record_photo_capture,
    serialize_user_for_admin,
    set_photo_capture,
    update_login_csv_metadata,
    update_precise_location,
    update_user_drive_folder,
    update_heartbeat,
    record_feature_usage,
    check_duplicate_pdf,
    get_active_users,
    update_streaming_state,
    update_streaming_frame,
    get_streaming_state,
)
from ocr_helper import extract_text_from_pdf_stream

import traceback  # Import traceback module
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Define IST timezone
IST = timezone(timedelta(hours=5, minutes=30))

# Load environment from both repo root and backend/.env explicitly
try:
    from pathlib import Path
    # First load root .env if present
    load_dotenv(override=False)
    # Then load backend/.env to support running from repo root
    backend_env = Path(__file__).parent / ".env"
    if backend_env.exists():
        load_dotenv(dotenv_path=str(backend_env), override=False)
        print(f"[Init] Loaded .env from {backend_env}")
    else:
        print(f"[Init] .env not found at {backend_env}")
except Exception as _exc:
    print(f"[Init] Warning: .env loading issue: {_exc}")

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# Configuration
DRIVE_ONLY_MODE = os.getenv('DRIVE_ONLY_MODE', 'false').lower() == 'true'
DRIVE_USER_MODE = os.getenv('DRIVE_USER_MODE', 'false').lower() == 'true'
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')

# Detect environment
IS_PRODUCTION = os.getenv('RENDER') == 'true' or os.getenv('RAILWAY_PUBLIC_DOMAIN') is not None or os.getenv('SPACE_ID') is not None

# Get frontend URL for CORS
# Default to the user's Vercel URL
DEFAULT_FRONTEND_URL = "https://studyai-ajay.vercel.app"
FRONTEND_URL = os.getenv('FRONTEND_URL', DEFAULT_FRONTEND_URL)

# Normalize URL (remove trailing slash for consistency)
if FRONTEND_URL.endswith('/'):
    FRONTEND_URL = FRONTEND_URL[:-1]

# Enable CORS for frontend with cookies
# IMPORTANT: Must specify actual origin, not *, when using credentials=True
CORS(app, 
     supports_credentials=True,
     origins=[
         FRONTEND_URL,
         "https://studyai-ajay.vercel.app",
         "http://localhost:3000",
         "http://localhost:5500",
         "http://127.0.0.1:5500",
         "http://127.0.0.1:3000"
     ],
     methods=["GET", "POST", "OPTIONS", "PUT", "DELETE"],
     allow_headers=["Content-Type", "Authorization"],
     expose_headers=["Content-Type", "Set-Cookie"],
     max_age=3600
)

print(f"[CORS] Allowed origins: {FRONTEND_URL}, https://studyai-ajay.vercel.app")
print(f"[CORS] supports_credentials=True (cookies enabled)")

# Use server-side session ONLY for PDF storage (not auth)
# Auth uses cookies only
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False

# Cookie Security Configuration
if IS_PRODUCTION:
    print("[Config] Production mode detected: Enabling Secure/None cookies")
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'None'
else:
    print("[Config] Development mode: Using Lax cookies")
    app.config['SESSION_COOKIE_SECURE'] = False
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

app.config['PERMANENT_SESSION_LIFETIME'] = 3600
app.config["SESSION_FILE_DIR"] = os.path.join(os.path.dirname(__file__), "flask_session")
print(f"[Session] Enabled for PDF storage only - auth uses COOKIES")
Session(app)

# Startup Configuration Log
print("="*50)
print(f"Starting Application")
print(f"DRIVE_ONLY_MODE: {DRIVE_ONLY_MODE}")
print(f"DRIVE_USER_MODE: {DRIVE_USER_MODE}")
if DRIVE_ONLY_MODE:
    print("Database: DISABLED (Using Drive for storage)")
    if DRIVE_USER_MODE:
        print("Storage: User's Personal Drive (OAuth)")
    else:
        print("Storage: Service Account")
else:
    print("Database: ENABLED")
print("="*50)

# Database setup
if not DRIVE_ONLY_MODE:
    try:
        init_db()
    except Exception as e:
        print(f"[ERROR] Failed to initialize database: {e}")
        # Do not raise, so the app can start and we can see logs
        # raise

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
# FRONTEND_URL is defined at the top of the file

# Detect environment
if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    print(f"[WARNING] GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not set!")
    print(f"[WARNING] OAuth will not work - set these env vars on Railway")

# Production - use Railway public domain, fallback to env var
if os.getenv('RAILWAY_PUBLIC_DOMAIN') or os.getenv('RAILWAY_DOMAIN'):
    RAILWAY_PUBLIC_DOMAIN = os.getenv('RAILWAY_PUBLIC_DOMAIN') or os.getenv('RAILWAY_DOMAIN')
    BACKEND_URL = f"https://{RAILWAY_PUBLIC_DOMAIN}"
else:
    BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:5000')

GOOGLE_REDIRECT_URI = f"{BACKEND_URL}/auth/google/callback"

print(f"\n[Init] ========================================")
print(f"[Init] GOOGLE_CLIENT_ID: {'SET' if GOOGLE_CLIENT_ID else 'NOT SET'}")
print(f"[Init] GOOGLE_CLIENT_SECRET: {'SET' if GOOGLE_CLIENT_SECRET else 'NOT SET'}")
print(f"[Init] BACKEND_URL: {BACKEND_URL}")
print(f"[Init] FRONTEND_URL: {FRONTEND_URL}")
print(f"[Init] GOOGLE_REDIRECT_URI: {GOOGLE_REDIRECT_URI}")
print(f"[Init] ========================================\n")

# Groq client (LLM-as-a-service)
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
print(f"[Init] GROQ_API_KEY: {'SET' if GROQ_API_KEY else 'NOT SET'}")
if GROQ_API_KEY:
    print(f"[Init] GROQ_API_KEY prefix: {GROQ_API_KEY[:4]}...")

GROQ_MODEL = os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')
GROQ_VISION_MODEL = os.getenv('GROQ_VISION_MODEL', 'llama-3.2-11b-vision-preview')
print(f"[Init] Using Groq model: {GROQ_MODEL}")
print(f"[Init] Using Groq Vision model: {GROQ_VISION_MODEL}")
_groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
print(f"[Init] Groq Client Initialized: {bool(_groq_client)}")

# DeepSeek client (OpenAI compatible)
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_MODEL = os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')
print(f"[Init] DEEPSEEK_API_KEY: {'SET' if DEEPSEEK_API_KEY else 'NOT SET'}")
_deepseek_client = None
if DEEPSEEK_API_KEY:
    try:
        _deepseek_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
        print(f"[Init] DeepSeek Client Initialized with model: {DEEPSEEK_MODEL}")
    except Exception as e:
        print(f"[Init] Failed to initialize DeepSeek client: {e}")

# LLM Provider Selection
LLM_PROVIDER = os.getenv('LLM_PROVIDER', 'groq').lower()
print(f"[Init] Selected LLM Provider: {LLM_PROVIDER}")

# RAG Helper Functions
def chunk_text(text, chunk_size=1000, overlap=200):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += (chunk_size - overlap)
    return chunks

def retrieve_relevant_chunks(query, text, top_k=3):
    if not text:
        return []
    chunks = chunk_text(text)
    if not chunks:
        return []
    
    try:
        vectorizer = TfidfVectorizer()
        tfidf_matrix = vectorizer.fit_transform(chunks + [query])
        # Scipy sparse matrices support slicing, but type checkers often miss this
        cosine_sim = cosine_similarity(tfidf_matrix[-1], tfidf_matrix[:-1]) # type: ignore
        
        # Get top_k indices
        related_docs_indices = cosine_sim.argsort()[0][-top_k:][::-1]
        return [chunks[i] for i in related_docs_indices]
    except Exception as e:
        print(f"[RAG] Error retrieving chunks: {e}")
        # Fallback to returning first few chunks if vectorization fails
        return chunks[:top_k]

# Unified chat helper: Groq or DeepSeek

def llm_chat(messages, max_tokens=None, temperature=0.2, context_text=None):
    client = None
    model = None
    
    if LLM_PROVIDER == 'deepseek':
        if not _deepseek_client:
             raise RuntimeError("DEEPSEEK_API_KEY is not set on the server, but LLM_PROVIDER is 'deepseek'")
        client = _deepseek_client
        model = DEEPSEEK_MODEL
    else:
        if not _groq_client:
            raise RuntimeError("GROQ_API_KEY is not set on the server")
        client = _groq_client
        model = GROQ_MODEL
    
    # If context is provided, inject it into the system prompt or user message
    if context_text:
        # Check if the last message is from user
        if messages and messages[-1]['role'] == 'user':
            user_query = messages[-1]['content']
            
            # Retrieve relevant chunks
            relevant_chunks = retrieve_relevant_chunks(user_query, context_text)
            context_str = "\n\n".join(relevant_chunks)
            
            # Augment the user query with context
            augmented_query = f"""Context information is below.
---------------------
{context_str}
---------------------
Given the context information and not prior knowledge, answer the query.
Query: {user_query}
"""
            messages[-1]['content'] = augmented_query
            print(f"[RAG] Augmented query with {len(relevant_chunks)} chunks")

    # If max_tokens is not specified, let provider use its default (no limit)
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content

# OAuth scopes (use full URIs to avoid scope-change warnings)
SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile'
]
if DRIVE_USER_MODE:
    SCOPES.append('https://www.googleapis.com/auth/drive')


def get_user_drive_service():
    if not DRIVE_USER_MODE:
        return None
    creds_dict = session.get('google_creds') or None
    if not creds_dict:
        return None
    try:
        creds = GoogleUserCredentials(
            token=creds_dict.get('token'),
            refresh_token=creds_dict.get('refresh_token'),
            token_uri=creds_dict.get('token_uri'),
            client_id=creds_dict.get('client_id'),
            client_secret=creds_dict.get('client_secret'),
            scopes=creds_dict.get('scopes'),
        )
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleAuthRequest())
            session['google_creds'] = {
                'token': creds.token,
                'refresh_token': creds.refresh_token,
                'token_uri': creds.token_uri,
                'client_id': creds.client_id,
                'client_secret': creds.client_secret,
                'scopes': creds.scopes,
            }
        return gdrive_build('drive', 'v3', credentials=creds, cache_discovery=False)
    except Exception as exc:
        print(f"[Drive] Failed to build user drive service: {exc}")
        return None


def get_client_ip() -> Optional[str]:
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr


def build_login_location_payload(
    ip_lookup: Optional[Dict[str, Any]],
    ip_address: Optional[str],
) -> Optional[Dict[str, Any]]:
    payload: Dict[str, Any] = {}
    if ip_address:
        payload["ipAddress"] = ip_address
    if ip_lookup:
        payload["ipLookup"] = ip_lookup
    return payload or None


def extract_location_for_csv(location: Optional[Dict[str, Any]]) -> Dict[str, str]:
    empty: Dict[str, str] = {
        'city': '',
        'region': '',
        'country': '',
        'latitude': '',
        'longitude': '',
        'timezone': '',
    }
    if not isinstance(location, dict):
        return empty

    def as_dict(value: Any) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def to_str(value: Any) -> str:
        if value is None:
            return ''
        return str(value)

    device_loc = as_dict(location.get('device'))
    ip_loc = as_dict(location.get('ipLookup'))
    legacy_loc = {}
    if not device_loc and not ip_loc:
        legacy_loc = as_dict(location)

    # Prefer device coordinates when available, otherwise fallback to IP lookup, then legacy
    primary = device_loc or ip_loc or legacy_loc
    latitude = primary.get('latitude') or primary.get('lat') or primary.get('y')
    longitude = primary.get('longitude') or primary.get('lon') or primary.get('lng') or primary.get('x')

    resolved = dict(empty)
    resolved['latitude'] = to_str(latitude)
    resolved['longitude'] = to_str(longitude)
    resolved['city'] = to_str(primary.get('city') or ip_loc.get('city') or legacy_loc.get('city'))
    resolved['region'] = to_str(primary.get('region') or ip_loc.get('region') or legacy_loc.get('region'))
    resolved['country'] = to_str(primary.get('country') or ip_loc.get('country') or legacy_loc.get('country'))
    resolved['timezone'] = to_str(primary.get('timezone') or ip_loc.get('timezone') or legacy_loc.get('timezone'))
    return resolved


def ensure_user_context(user_info: Dict[str, Any]):  # type: ignore[name-defined]
    drive_service = None
    if DRIVE_USER_MODE:
        drive_service = get_user_drive_service()
    if not drive_service:
        drive_service = get_drive_service()
    folder_info: Optional[Dict[str, Any]] = None
    if drive_service:
        try:
            folder_info = ensure_user_folder(drive_service, user_info.get('email', ''), user_info.get('name'))
        except Exception as exc:
            print(f"[Drive] Failed to ensure user folder: {exc}")
            folder_info = None

    # Drive-only mode: return a pseudo user based on cookie + Drive state
    if DRIVE_ONLY_MODE:
        from types import SimpleNamespace
        pseudo = SimpleNamespace()
        pseudo.id = None
        pseudo.email = user_info.get('email')
        pseudo.name = user_info.get('name') or user_info.get('given_name')
        pseudo.drive_folder_id = folder_info.get('id') if isinstance(folder_info, dict) else None
        pseudo.drive_folder_link = folder_info.get('link') if isinstance(folder_info, dict) else None
        pseudo.login_csv_web_view_link = None
        pseudo.photo_capture_enabled = False
        # Hydrate photo toggle from Drive user.json if present
        try:
            if drive_service and pseudo.drive_folder_id:
                state = load_user_json(drive_service, pseudo.drive_folder_id) or {}
                pseudo.photo_capture_enabled = bool(state.get('photo_capture_enabled', False))
        except Exception as exc:
            print(f"[Drive] load user.json failed: {exc}")
        return pseudo, drive_service, folder_info

    # DB-backed mode
    user = get_or_create_user(user_info, folder_info, drive_service=drive_service)
    user_id = getattr(user, 'id', None)
    if folder_info and isinstance(user_id, int):
        update_user_drive_folder(user_id, folder_info)

    if isinstance(user_id, int):
        with db_session() as session:
            refreshed = session.query(User).filter_by(id=user_id).first()
            if refreshed:
                _ = getattr(refreshed, 'drive_folder_id', None)
                _ = getattr(refreshed, 'photo_capture_enabled', None)
                _ = getattr(refreshed, 'login_csv_file_id', None)
                session.expunge(refreshed)
                return refreshed, drive_service, folder_info
    return user, drive_service, folder_info


def ensure_current_user() -> Optional[User]:
    if not DRIVE_ONLY_MODE:
        user = get_authenticated_user()
        if user:
            user_id = getattr(user, 'id', None)
            if isinstance(user_id, int):
                with db_session() as session:
                    refreshed = session.query(User).filter_by(id=user_id).first()
                    if refreshed:
                        _ = getattr(refreshed, 'drive_folder_id', None)
                        _ = getattr(refreshed, 'photo_capture_enabled', None)
                        _ = getattr(refreshed, 'login_csv_file_id', None)
                        session.expunge(refreshed)
                        return refreshed
            return user

    user_info = decode_user_cookie()
    if not user_info:
        return None
    user, _, _ = ensure_user_context(user_info)
    return user


def append_login_csv_if_possible(user: User, drive_service, location: Optional[Dict[str, Any]], ip_address: Optional[str], user_agent: Optional[str], photo_link: Optional[str] = None, event_type: str = "LOGIN") -> None:
    drive_folder_id = getattr(user, 'drive_folder_id', None)
    login_csv_file_id = getattr(user, 'login_csv_file_id', None)
    login_csv_file_name = getattr(user, 'login_csv_file_name', 'login_history.csv')

    if not drive_service or not drive_folder_id:
        print(f"[CSV] Skipping: drive_service={'Yes' if drive_service else 'No'}, drive_folder_id={drive_folder_id}")
        return

    # Try to find existing file if ID is missing (common in Drive-only mode)
    if not login_csv_file_id:
        found = find_named_file(drive_service, drive_folder_id, login_csv_file_name)
        if found:
            login_csv_file_id = found['id']

    existing_content = ""
    if login_csv_file_id:
        try:
            existing_bytes = download_file(drive_service, login_csv_file_id)
            existing_content = existing_bytes.decode('utf-8')
        except Exception as exc:
            print(f"[Drive] Failed to download login CSV: {exc}")
            existing_content = ""

    rows = []
    header = []
    
    # Define IST timezone
    IST = timezone(timedelta(hours=5, minutes=30))
    
    if existing_content:
        reader = csv.reader(existing_content.splitlines())
        rows = list(reader)
        if rows:
            header = rows[0]
            
            # Check if we need to migrate from 'timestamp' to 'date, time'
            if 'timestamp' in header:
                print("[CSV] Migrating CSV from timestamp to date/time format...")
                try:
                    timestamp_idx = header.index('timestamp')
                    # Create new header
                    new_header = ['date', 'time'] + [h for h in header if h != 'timestamp']
                    
                    new_rows = [new_header]
                    for row in rows[1:]:
                        if len(row) <= timestamp_idx:
                            continue
                            
                        ts_str = row[timestamp_idx]
                        date_str = ""
                        time_str = ""
                        
                        # Try to parse timestamp
                        try:
                            if ts_str:
                                dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                                dt_ist = dt.astimezone(IST)
                                date_str = dt_ist.strftime('%Y-%m-%d')
                                time_str = dt_ist.strftime('%H:%M:%S')
                        except Exception as e:
                            print(f"[CSV] Failed to parse timestamp {ts_str}: {e}")
                            
                        # Construct new row
                        new_row = [date_str, time_str] + [val for i, val in enumerate(row) if i != timestamp_idx]
                        new_rows.append(new_row)
                    
                    # Replace rows and header with migrated version
                    rows = new_rows
                    header = new_header
                except Exception as e:
                    print(f"[CSV] Migration failed: {e}")
                    # Fallback: just append to old format if migration fails? 
                    # Or better, proceed and let the new row logic handle it (it will use new header logic)
                    pass

    # Define default header for new files (or if migration happened)
    if not rows or (rows and 'date' not in rows[0]):
        header = [
            'date',
            'time',
            'event_type',
            'ip',
            'city',
            'region',
            'country',
            'google_maps_link',
            'timezone',
            'user_agent',
            'photo_link'
        ]
        rows = [header]
    else:
        header = rows[0]

    loc = extract_location_for_csv(location)
    lat = loc.get('latitude', '')
    lon = loc.get('longitude', '')
    
    maps_link = ""
    if lat and lon:
        maps_link = f"https://www.google.com/maps?q={lat},{lon}"

    # Helper to get value for a column
    def get_col_value(col_name: str) -> str:
        now_ist = datetime.now(IST)
        
        if col_name == 'date':
            return now_ist.strftime('%Y-%m-%d')
        if col_name == 'time':
            return now_ist.strftime('%H:%M:%S')
        if col_name == 'timestamp':
            # Fallback for old files if migration failed
            return now_ist.isoformat()
        if col_name == 'event_type':
            return event_type
        if col_name == 'ip':
            return ip_address or ''
        if col_name == 'city':
            return loc.get('city', '')
        if col_name == 'region':
            return loc.get('region', '')
        if col_name == 'country':
            return loc.get('country', '')
        if col_name == 'google_maps_link':
            return maps_link
        if col_name == 'latitude':
            return maps_link
        if col_name == 'longitude':
            return ""
        if col_name == 'timezone':
            return loc.get('timezone', '')
        if col_name == 'user_agent':
            return (user_agent or '').replace('\n', ' ')
        if col_name == 'photo_link':
            return photo_link or ''
        return ''

    # Construct the new row based on the ACTUAL header of the file
    new_row = [get_col_value(col) for col in header]
    rows.append(new_row)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(rows)

    try:
        print(f"[CSV] Uploading CSV to {drive_folder_id} (ID: {login_csv_file_id or 'New'})")
        metadata = upload_text_file(
            drive_service,
            drive_folder_id,
            login_csv_file_name,
            output.getvalue(),
            existing_file_id=login_csv_file_id,
        )
        if DRIVE_ONLY_MODE:
            pass  # No DB to update
        else:
            user_id = getattr(user, 'id', None)
            file_id = metadata.get('id') if metadata else None
            if isinstance(user_id, int) and isinstance(file_id, str):
                update_login_csv_metadata(user_id, file_id, metadata.get('webViewLink'))
    except Exception as exc:
        print(f"[Drive] Failed to upload login CSV: {exc}")
        import traceback
        traceback.print_exc()


@app.route('/api/login-verification', methods=['POST'])
def login_verification():
    """
    Called by frontend immediately after login to provide:
    1. Precise Geolocation (lat/long)
    2. Camera Photo (base64)
    """
    user_info = decode_user_cookie()
    if not user_info:
        return jsonify({"error": "Authentication required"}), 401

    user, drive_service, folder_info = ensure_user_context(user_info)
    
    data = request.get_json(silent=True) or {}
    image_data = data.get('photo')
    coords = data.get('coords') or {}
    
    # 1. Upload Photo if present
    photo_link = None
    if image_data and drive_service:
        try:
            if isinstance(image_data, str) and image_data.startswith('data:'):
                _, encoded_part = image_data.split(',', 1)
            else:
                encoded_part = image_data
            file_bytes = base64.b64decode(encoded_part)
            
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            filename = f"login_verify_{timestamp}.png"
            
            drive_folder_id = None
            if folder_info and folder_info.get('id'):
                drive_folder_id = folder_info['id']
            else:
                drive_folder_id = getattr(user, 'drive_folder_id', None)
                
            if drive_folder_id:
                # Ensure Photos subfolder
                print(f"[Verification] Ensuring Photos folder in {drive_folder_id}")
                photos_folder = ensure_subfolder(drive_service, drive_folder_id, "Photos")
                target_folder_id = photos_folder['id']

                print(f"[Verification] Uploading photo to {target_folder_id}")
                metadata = drive_upload_pdf(
                    drive_service,
                    target_folder_id,
                    filename,
                    file_bytes,
                    mimetype='image/png',
                )
                photo_link = metadata.get('webViewLink')
                print(f"[Verification] Photo uploaded: {photo_link}")

                # Record photo capture in DB
                if not DRIVE_ONLY_MODE:
                    try:
                        user_id = getattr(user, 'id', None)
                        if isinstance(user_id, int):
                            record_photo_capture(user_id, "login_verification", metadata)
                            print(f"[Verification] Photo capture recorded in DB for user {user_id}")
                    except Exception as e:
                        print(f"[Verification] Failed to record photo capture in DB: {e}")
            else:
                print(f"[Verification] No drive_folder_id found for user")
        except Exception as exc:
            print(f"[Verification] Photo upload failed: {exc}")
            import traceback
            traceback.print_exc()
    else:
        print(f"[Verification] Skipping photo: image_data={'Yes' if image_data else 'No'}, drive_service={'Yes' if drive_service else 'No'}")

    # 2. Log to CSV
    ip_address = get_client_ip()
    user_agent = request.headers.get('User-Agent')
    
    # Construct location object from client coords
    location_payload = None
    if coords:
        location_payload = {
            'device': {
                'latitude': coords.get('latitude'),
                'longitude': coords.get('longitude'),
                'accuracy': coords.get('accuracy')
            }
        }
        
        # Update DB with precise location if not in Drive-only mode
        if not DRIVE_ONLY_MODE:
            try:
                user_id = getattr(user, 'id', None)
                if isinstance(user_id, int):
                    precise_loc = {
                        "latitude": coords.get('latitude'),
                        "longitude": coords.get('longitude'),
                        "accuracy": coords.get('accuracy'),
                        "source": "verification"
                    }
                    update_precise_location(user_id, precise_loc)
            except Exception as e:
                print(f"[Verification] Failed to update DB location: {e}")
    
    append_login_csv_if_possible(
        user, 
        drive_service, 
        location_payload, 
        ip_address, 
        user_agent, 
        photo_link=photo_link,
        event_type="VERIFICATION"
    )
    
    return jsonify({
        "status": "verified",
        "photoLink": photo_link
    })


@app.route('/api/admin/repair-login-csv', methods=['POST'])
def admin_repair_login_csv():
    """Admin-only: force creation (or update) of the login CSV even if no recent login event."""
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Forbidden"}), 403

    drive_service = get_drive_service()
    if not drive_service:
        return jsonify({"error": "Drive service unavailable"}), 503

    drive_folder_id = getattr(admin, 'drive_folder_id', None)
    if not drive_folder_id:
        # Try to ensure folder now
        folder = ensure_user_folder(drive_service, getattr(admin, 'email', ''), getattr(admin, 'name', None))
        if folder and folder.get('id'):
            drive_folder_id = folder['id']
            update_user_drive_folder(getattr(admin, 'id', 0), folder)
    if not drive_folder_id:
        return jsonify({"error": "Drive folder not set"}), 400

    # Build a minimal header-only CSV if none exists
    existing_id = getattr(admin, 'login_csv_file_id', None)
    if not existing_id:
        found = find_named_file(drive_service, drive_folder_id, getattr(admin, 'login_csv_file_name', 'login_history.csv'))
        if found:
            existing_id = found['id']

    csv_content = 'timestamp,event_type,ip,city,region,country,google_maps_link,timezone,user_agent,photo_link\n'
    try:
        metadata = upload_text_file(
            drive_service,
            drive_folder_id,
            getattr(admin, 'login_csv_file_name', 'login_history.csv'),
            csv_content,
            existing_file_id=existing_id,
        )
        admin_id = getattr(admin, 'id', None)
        file_id = metadata.get('id') if metadata else None
        if isinstance(admin_id, int) and isinstance(file_id, str):
            update_login_csv_metadata(admin_id, file_id, metadata.get('webViewLink'))
        return jsonify({
            "message": "Login CSV repaired",
            "fileId": file_id,
            "webViewLink": metadata.get('webViewLink') if metadata else None,
        })
    except Exception as exc:
        return jsonify({"error": f"Failed to repair CSV: {exc}"}), 500


def handle_post_login(user_info: Dict[str, Any]) -> None:
    user, drive_service, _ = ensure_user_context(user_info)
    ip_address = get_client_ip()
    user_agent = request.headers.get('User-Agent')
    ip_location = lookup_location(ip_address)
    location_payload = build_login_location_payload(ip_location, ip_address)
    if not DRIVE_ONLY_MODE:
        record_login_event(user, ip_address, user_agent, location_payload)
    append_login_csv_if_possible(user, drive_service, location_payload, ip_address, user_agent)
    # Persist last_login and last_location to Drive user.json in drive-only mode
    if DRIVE_ONLY_MODE and drive_service:
        try:
            folder_id = getattr(user, 'drive_folder_id', None)
            if folder_id:
                state = load_user_json(drive_service, folder_id) or {}
                state['last_login_at'] = datetime.now(timezone.utc).isoformat()
                state['last_location'] = location_payload
                save_user_json(drive_service, folder_id, state)
        except Exception as exc:
            print(f"[Drive] Failed to update user.json after login: {exc}")


def require_admin() -> Optional[User]:
    if DRIVE_ONLY_MODE:
        info = decode_user_cookie()
        if not info:
            return None
        email = info.get('email')
        if email != ADMIN_EMAIL:
            return None
        pseudo = SimpleNamespace(
            email=email,
            name=info.get('name') or info.get('given_name') or '',
            id=None,
            drive_folder_link=None,
            login_csv_web_view_link=None,
            photo_capture_enabled=False,
        )
        return pseudo  # type: ignore
    user = ensure_current_user()
    if not user:
        return None
    user_email = getattr(user, 'email', None)
    if not isinstance(user_email, str) or user_email != ADMIN_EMAIL:
        return None
    return user


def build_admin_user_payloads() -> Dict[str, Any]:
    users_payload = []
    total_uploads = 0
    total_users = 0

    # Get drive service for direct photo lookup
    drive_service = get_drive_service()

    with db_session() as session:
        users = session.query(User).order_by(User.created_at.desc()).all()
        for user in users:
            user_id = getattr(user, 'id', None)
            if not isinstance(user_id, int):
                continue

            uploads_count = (
                session.query(func.count(PdfUpload.id))
                .filter(PdfUpload.user_id == user_id)
                .scalar()
            ) or 0
            total_uploads += uploads_count
            total_users += 1

            daily_stats_rows = (
                session.query(DailyUploadStat)
                .filter(DailyUploadStat.user_id == user_id)
                .order_by(DailyUploadStat.date.desc())
                .limit(30)
                .all()
            )
            daily_stats: Dict[str, int] = {}
            for row in daily_stats_rows:
                date_value = getattr(row, 'date', None)
                count_value = getattr(row, 'upload_count', 0)
                if date_value:
                    daily_stats[date_value.isoformat()] = int(count_value or 0)

            # Fetch last photo link
            last_photo_link = None
            
            # 1. Try to fetch latest photo directly from Drive (Photos or Captures/Photos)
            if drive_service:
                try:
                    drive_folder_id = getattr(user, 'drive_folder_id', None)
                    if drive_folder_id:
                        candidates = []
                        
                        # Check "Photos" folder (Login verifications)
                        photos_folder = find_named_file(drive_service, drive_folder_id, "Photos")
                        if photos_folder:
                            p_files = list_folder_files(drive_service, photos_folder['id'], page_size=1).get('files', [])
                            if p_files:
                                candidates.append(p_files[0])
                                
                        # Check "Captures" -> "Photos" (Live captures)
                        captures_folder = find_named_file(drive_service, drive_folder_id, "Captures")
                        if captures_folder:
                            c_photos_folder = find_named_file(drive_service, captures_folder['id'], "Photos")
                            if c_photos_folder:
                                c_files = list_folder_files(drive_service, c_photos_folder['id'], page_size=1).get('files', [])
                                if c_files:
                                    candidates.append(c_files[0])
                        
                        # Pick the latest one
                        if candidates:
                            # Sort by modifiedTime desc
                            candidates.sort(key=lambda x: x.get('modifiedTime', ''), reverse=True)
                            latest = candidates[0]
                            
                            if latest.get('id'):
                                last_photo_link = f"{BACKEND_URL}/api/admin/file/proxy/{latest['id']}"
                            else:
                                last_photo_link = latest.get('webViewLink')
                                
                except Exception as e:
                    print(f"[DEBUG] Drive photo fetch failed for user {user_id}: {e}")

            # 2. Fallback to DB if Drive didn't yield anything
            if not last_photo_link:
                try:
                    photo = (
                        session.query(PhotoCaptureEvent)
                        .filter(PhotoCaptureEvent.user_id == user_id)
                        .order_by(PhotoCaptureEvent.captured_at.desc())
                        .first()
                    )
                    if photo:
                        # Use proxy endpoint if file ID is available
                        file_id = getattr(photo, 'drive_file_id', None)
                        print(f"[DEBUG] User {user_id} last photo: ID={file_id}, Link={getattr(photo, 'drive_web_view_link', 'None')}")
                        if file_id:
                            last_photo_link = f"{BACKEND_URL}/api/admin/file/proxy/{file_id}"
                        else:
                            last_photo_link = getattr(photo, 'drive_web_view_link', None)
                    else:
                        print(f"[DEBUG] User {user_id} has no photos")
                except Exception as e:
                    print(f"[DEBUG] Error fetching photo for user {user_id}: {e}")
                    pass

            session.expunge(user)
            users_payload.append(serialize_user_for_admin(user, daily_stats, uploads_count, last_photo_link))

    return {
        "users": users_payload,
        "summary": {
            "totalUsers": total_users,
            "totalUploads": total_uploads,
        },
    }


def fetch_login_events_payload(user_id: int, limit: int = 50) -> Dict[str, Any]:
    with db_session() as session:
        events = (
            session.query(LoginEvent)
            .filter(LoginEvent.user_id == user_id)
            .order_by(LoginEvent.timestamp.desc())
            .limit(limit)
            .all()
        )
        payload = []
        for event in events:
            timestamp = getattr(event, 'timestamp', None)
            payload.append(
                {
                    "timestamp": timestamp.isoformat() if timestamp else None,
                    "ip": getattr(event, 'ip_address', None),
                    "userAgent": getattr(event, 'user_agent', None),
                    "location": getattr(event, 'location', None),
                }
            )
        return {
            "logins": payload,
            "count": len(payload),
        }


def fetch_upload_events_payload(user_id: int, limit: int = 50) -> Dict[str, Any]:
    with db_session() as session:
        uploads = (
            session.query(PdfUpload)
            .filter(PdfUpload.user_id == user_id)
            .order_by(PdfUpload.uploaded_at.desc())
            .limit(limit)
            .all()
        )
        payload = []
        for upload in uploads:
            uploaded_at = getattr(upload, 'uploaded_at', None)
            payload.append(
                {
                    "filename": getattr(upload, 'filename', None),
                    "uploadedAt": uploaded_at.isoformat() if uploaded_at else None,
                    "driveFileId": getattr(upload, 'drive_file_id', None),
                    "driveWebViewLink": getattr(upload, 'drive_web_view_link', None),
                    "driveWebContentLink": getattr(upload, 'drive_web_content_link', None),
                    "fileSize": getattr(upload, 'file_size', None),
                    "sha256": getattr(upload, 'sha256_hash', None),
                }
            )
        return {
            "uploads": payload,
            "count": len(payload),
        }

# ------------------------- New Features: Heartbeat, Usage, Active Users -------------------------

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    user = ensure_current_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    
    if DRIVE_ONLY_MODE:
        return jsonify({"status": "ignored", "mode": "drive-only"}), 200

    user_id = getattr(user, 'id', None)
    if isinstance(user_id, int):
        update_heartbeat(user_id)
        
        # Check for streaming command
        stream_state = get_streaming_state(user_id)
        if stream_state:
            command = stream_state.get("command")
            if command:
                # Clear command after sending
                stream_state["command"] = None
                return jsonify({
                    "status": "ok",
                    "command": command,
                    "facingMode": stream_state.get("facingMode", "user")
                })
            
            if stream_state.get("active"):
                return jsonify({
                    "status": "ok",
                    "command": "start_stream",
                    "facingMode": stream_state.get("facingMode", "user")
                })
            elif not stream_state.get("active"):
                 return jsonify({
                    "status": "ok",
                    "command": "stop_stream"
                })
            
        return jsonify({"status": "ok"})
    return jsonify({"error": "Invalid user"}), 400


@app.route('/api/record-usage', methods=['POST'])
def record_usage():
    user = ensure_current_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 401

    if DRIVE_ONLY_MODE:
        return jsonify({"status": "ignored", "mode": "drive-only"}), 200

    data = request.get_json(silent=True) or {}
    feature_type = data.get('feature_type')
    details = data.get('details', '')
    pdf_filename = data.get('pdf_filename')

    if not feature_type:
        return jsonify({"error": "feature_type required"}), 400

    user_id = getattr(user, 'id', None)
    if isinstance(user_id, int):
        record_feature_usage(user_id, feature_type, details, pdf_filename)
        return jsonify({"status": "recorded"})
    return jsonify({"error": "Invalid user"}), 400


@app.route('/api/admin/stream/control', methods=['POST'])
def admin_stream_control():
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Forbidden"}), 403
    
    data = request.get_json()
    user_id = data.get('user_id')
    action = data.get('action')
    facing_mode = data.get('facing_mode', 'user')
    
    if not user_id or not action:
        return jsonify({"error": "Missing user_id or action"}), 400
        
    if action == 'start':
        update_streaming_state(user_id, True, facing_mode)
    elif action == 'stop':
        update_streaming_state(user_id, False)
    elif action == 'switch':
        # Toggle facing mode
        current = get_streaming_state(user_id)
        new_mode = 'environment' if current and current.get('facingMode') == 'user' else 'user'
        update_streaming_state(user_id, True, new_mode)
    elif action in ['capture_photo', 'start_recording', 'stop_recording']:
        # Set command in state for heartbeat to pick up
        state = get_streaming_state(user_id)
        if not state:
            update_streaming_state(user_id, True, facing_mode)
            state = get_streaming_state(user_id)
        if state:
            state['command'] = action
            
    return jsonify({"status": "ok"})


@app.route('/api/upload-capture', methods=['POST'])
def upload_capture():
    """
    Endpoint for uploading captured photos/videos from live stream
    """
    user_info = decode_user_cookie()
    if not user_info:
        return jsonify({"error": "Authentication required"}), 401

    user, drive_service, folder_info = ensure_user_context(user_info)
    
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
        
    file = request.files['file']
    capture_type = request.form.get('type', 'photo') # photo or video
    
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if not drive_service:
        return jsonify({"error": "Drive service unavailable"}), 503

    try:
        drive_folder_id = getattr(user, 'drive_folder_id', None)
        if not drive_folder_id and folder_info:
            drive_folder_id = folder_info.get('id')
            
        if not drive_folder_id:
            return jsonify({"error": "User drive folder not found"}), 400
            
        # Ensure folder structure: Captures -> Photos/Videos
        captures_folder = ensure_subfolder(drive_service, drive_folder_id, "Captures")
        target_folder_name = "Photos" if capture_type == 'photo' else "Videos"
        target_folder = ensure_subfolder(drive_service, captures_folder['id'], target_folder_name)
        
        # Generate filename with timestamp
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        ext = 'png' if capture_type == 'photo' else 'webm'
        filename = f"{capture_type}_{timestamp}.{ext}"
        mimetype = 'image/png' if capture_type == 'photo' else 'video/webm'
        
        file_bytes = file.read()
        
        print(f"[Capture] Uploading {capture_type} to {target_folder['id']}")
        metadata = drive_upload_pdf(
            drive_service,
            target_folder['id'],
            filename,
            file_bytes,
            mimetype=mimetype,
        )
        
        # Record in DB
        if not DRIVE_ONLY_MODE:
            user_id = getattr(user, 'id', None)
            if isinstance(user_id, int):
                record_photo_capture(user_id, f"live_{capture_type}", metadata)
                
        return jsonify({
            "status": "uploaded",
            "link": metadata.get('webViewLink')
        })
        
    except Exception as e:
        print(f"[Capture] Upload failed: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/admin/active-users', methods=['GET'])
def admin_active_users():
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Forbidden"}), 403
    
    if DRIVE_ONLY_MODE:
        return jsonify({"active_users": [], "count": 0, "mode": "drive-only"})

    # Users active in last 30 seconds
    active_users = get_active_users(seconds=30)
    payload = []
    for u in active_users:
        payload.append({
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "picture": u.picture,
            "last_heartbeat": u.last_heartbeat.isoformat() if u.last_heartbeat is not None else None
        })
    
    return jsonify({"active_users": payload, "count": len(payload)})


@app.route('/api/admin/users/<int:user_id>/activity-log', methods=['GET'])
def admin_user_activity_log(user_id: int):
    print(f"[DEBUG] Fetching activity log for user {user_id}")
    try:
        admin = require_admin()
        if not admin:
            return jsonify({"error": "Forbidden"}), 403

        if DRIVE_ONLY_MODE:
            return jsonify({"logs": [], "mode": "drive-only"})

        # Fetch logins, uploads, and feature usage
        # We'll combine them into a single timeline
        
        logs = []
        
        # 1. Logins
        login_payload = fetch_login_events_payload(user_id, limit=100)
        login_events = login_payload.get('logins', [])
        print(f"[DEBUG] Found {len(login_events)} logins")

        # 2. Uploads
        upload_payload = fetch_upload_events_payload(user_id, limit=100)
        print(f"[DEBUG] Found {len(upload_payload.get('uploads', []))} uploads")
        for u in upload_payload.get('uploads', []):
            logs.append({
                "type": "UPLOAD",
                "timestamp": u['uploadedAt'],
                "details": f"File: {u['filename']}, Size: {u['fileSize']} bytes",
                "link": u.get('driveWebViewLink')
            })

        # 3. Feature Usage & Photos
        with db_session() as session:
            usages = (
                session.query(FeatureUsage)
                .filter(FeatureUsage.user_id == user_id)
                .order_by(FeatureUsage.timestamp.desc())
                .limit(100)
                .all()
            )
            print(f"[DEBUG] Found {len(usages)} feature usages")
            for usage in usages:
                logs.append({
                    "type": usage.feature_type,
                    "timestamp": usage.timestamp.isoformat() if usage.timestamp is not None else None,
                    "details": f"PDF: {usage.pdf_filename or 'N/A'}, Details: {usage.details}"
                })

            # 4. Photos
            photos = (
                session.query(PhotoCaptureEvent)
                .filter(PhotoCaptureEvent.user_id == user_id)
                .order_by(PhotoCaptureEvent.captured_at.desc())
                .limit(100)
                .all()
            )
            print(f"[DEBUG] Found {len(photos)} photos")
            
            # Convert photos to list of dicts for processing
            photo_list = []
            for p in photos:
                photo_list.append({
                    "id": p.id,
                    "timestamp": p.captured_at,
                    "context": p.context,
                    "drive_file_id": p.drive_file_id,
                    "drive_web_view_link": p.drive_web_view_link,
                    "used": False
                })

        # Process Logins and link photos
        for l in login_events:
            l_ts_str = l['timestamp']
            l_dt = datetime.fromisoformat(l_ts_str) if l_ts_str else None
            
            photo_link = None
            
            if l_dt:
                # Find matching photo (within 2 minutes)
                for p in photo_list:
                    if p['used']:
                        continue
                    
                    # Calculate time difference
                    time_diff = abs((p['timestamp'] - l_dt).total_seconds())
                    if time_diff < 120: # 2 minutes window
                        # Found a match!
                        p['used'] = True
                        if p['drive_file_id']:
                            photo_link = f"{BACKEND_URL}/api/admin/file/proxy/{p['drive_file_id']}"
                        else:
                            photo_link = p['drive_web_view_link']
                        break
            
            logs.append({
                "type": "LOGIN",
                "timestamp": l['timestamp'],
                "ip": l['ip'],
                "location": l['location'],
                "userAgent": l['userAgent'],
                "photoLink": photo_link
            })

        # Add remaining unused photos as standalone events
        for p in photo_list:
            if not p['used']:
                link = p['drive_web_view_link']
                if p['drive_file_id']:
                    link = f"{BACKEND_URL}/api/admin/file/proxy/{p['drive_file_id']}"
                
                logs.append({
                    "type": "PHOTO",
                    "timestamp": p['timestamp'].isoformat(),
                    "details": f"Context: {p['context']}",
                    "link": link
                })

        # Sort by timestamp desc
        logs.sort(key=lambda x: x['timestamp'] or "", reverse=True)
        print(f"[DEBUG] Total logs: {len(logs)}")
        
        return jsonify({"logs": logs})
    except Exception as e:
        print(f"[ERROR] admin_user_activity_log failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/')
def index():
    return jsonify({"message": "Smart Study Hub API"})

@app.route('/health')
def health():
    """Health check endpoint for Railway"""
    return jsonify({"status": "healthy"}), 200

@app.route('/debug/config')
def debug_config():
    """Debug endpoint to check configuration"""
    return jsonify({
        "backend_url": BACKEND_URL,
        "frontend_url": FRONTEND_URL,
        "google_redirect_uri": GOOGLE_REDIRECT_URI,
        "google_client_id_set": bool(GOOGLE_CLIENT_ID),
        "google_client_secret_set": bool(GOOGLE_CLIENT_SECRET),
        "cors_origins": "*"
    }), 200

@app.route('/me')
def me():
    print(f"[DEBUG] /me called - verifying cookies and mode")
    user_info = decode_user_cookie()
    if not user_info:
        return jsonify({"authenticated": False}), 401
    if DRIVE_ONLY_MODE:
        drive_service = get_drive_service()
        folder_meta = None
        drive_state = {}
        if drive_service:
            try:
                folder_meta = ensure_user_folder(drive_service, user_info.get('email', ''), user_info.get('name'))
                if folder_meta and folder_meta.get('id'):
                    drive_state = load_user_json(drive_service, folder_meta['id']) or {}
            except Exception as exc:
                print(f"[Drive] /me drive-only ensure folder failed: {exc}")
        is_admin = user_info.get('email') == ADMIN_EMAIL
        return jsonify({
            "authenticated": True,
            "user": user_info,
            "isAdmin": is_admin,
            "photoCaptureEnabled": bool(drive_state.get('photo_capture_enabled', False)),
            "dbUser": None,
            "driveFolderLink": folder_meta.get('link') if folder_meta else None,
            "loginCsvLink": None,
        })
    # Normal DB-backed mode
    response_payload: Dict[str, Any] = {"authenticated": True, "user": user_info}
    user_record = ensure_current_user()
    if user_record:
        user_id = getattr(user_record, 'id', None)
        email = getattr(user_record, 'email', None)
        response_payload.update({
            "dbUser": {
                "id": user_id,
                "email": email,
                "name": getattr(user_record, 'name', None),
                "driveFolderLink": getattr(user_record, 'drive_folder_link', None),
                "loginCsvLink": getattr(user_record, 'login_csv_web_view_link', None),
            },
            "photoCaptureEnabled": bool(getattr(user_record, 'photo_capture_enabled', False)),
            "isAdmin": bool(isinstance(email, str) and email == ADMIN_EMAIL),
        })
    else:
        response_payload['isAdmin'] = False
    return jsonify(response_payload), 200

@app.route('/auth/google')
def google_auth():
    print("\n" + "="*60)
    print("[DEBUG] /auth/google route called")
    print(f"[DEBUG] GOOGLE_CLIENT_ID: {'SET' if GOOGLE_CLIENT_ID else 'NOT SET'}")
    print(f"[DEBUG] Using GOOGLE_REDIRECT_URI: {GOOGLE_REDIRECT_URI}")
    
    # Generate a state parameter (random string)
    state = secrets.token_urlsafe(32)
    print(f"[DEBUG] Generated state: {state}")
    
    try:
        # Production only - use Railway public domain
        print(f"[DEBUG] Creating OAuth flow...")
        flow = google_auth_oauthlib.flow.Flow.from_client_config({
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [GOOGLE_REDIRECT_URI]
            }
        }, scopes=SCOPES, state=state)

        flow.redirect_uri = GOOGLE_REDIRECT_URI
        print(f"[DEBUG] Flow redirect_uri set to: {flow.redirect_uri}")
        
        authorization_url, generated_state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        
        print(f"[DEBUG] Authorization URL generated")
        print(f"[DEBUG] Authorization URL: {authorization_url[:100]}...")
        
        # Create response to redirect to Google
        response = redirect(authorization_url)
        
        # Store state in a secure cookie so we can verify it on callback
        response.set_cookie(
            'oauth_state',
            generated_state,
            max_age=600,  # 10 minutes
            secure=False,  # Allow HTTP for dev
            httponly=True,  # Don't allow JS to read
            samesite='Lax',
            path='/'
        )
        
        print(f"[DEBUG] State cookie set: {generated_state[:20]}...")
        print(f"[DEBUG] Redirecting to Google...")
        print("="*60 + "\n")
        
        return response
        
    except Exception as e:
        print(f"[ERROR] Exception in /auth/google: {e}")
        print(f"[ERROR] Exception type: {type(e)}")
        import traceback
        print(f"[ERROR] Traceback:\n{traceback.format_exc()}")
        print("="*60 + "\n")
        return jsonify({"error": str(e), "type": type(e).__name__}), 500

@app.route('/auth/google/callback')
def google_callback():
    try:
        print("\n" + "="*80)
        print("[CALLBACK] ===== GOOGLE OAUTH CALLBACK RECEIVED =====")
        print(f"[CALLBACK] Request URL: {request.url}")
        print(f"[CALLBACK] Cookies: {dict(request.cookies)}")
        
        state_from_url = request.args.get('state')
        code = request.args.get('code')
        error_from_url = request.args.get('error')
        
        print(f"[CALLBACK] State from URL: {state_from_url[:20] if state_from_url else 'NONE'}...")
        print(f"[CALLBACK] Code from URL: {code[:30] if code else 'NONE'}...")
        print(f"[CALLBACK] Error from URL: {error_from_url}")
        
        # Check for Google error first
        if error_from_url:
            print(f"[ERROR] Google returned error: {error_from_url}")
            return jsonify({"error": f"Google OAuth error: {error_from_url}"}), 400
        
        if not code:
            print(f"[ERROR] No authorization code received from Google!")
            return jsonify({"error": "No authorization code"}), 400
        
        # Verify state from cookie
        state_from_cookie = request.cookies.get('oauth_state')
        print(f"[CALLBACK] State from cookie: {state_from_cookie[:20] if state_from_cookie else 'NONE'}...")
        
        if not state_from_url or not state_from_cookie or state_from_url != state_from_cookie:
            print(f"[ERROR] State mismatch!")
            print(f"  - URL state: {state_from_url}")
            print(f"  - Cookie state: {state_from_cookie}")
            print(f"  - Match: {state_from_url == state_from_cookie}")
            return jsonify({"error": "Invalid state"}), 400
        
        print(f"[CALLBACK] ✅ State verified successfully")
        
        # Create flow again with the stored state
        print(f"[CALLBACK] Creating OAuth flow...")
        flow = google_auth_oauthlib.flow.Flow.from_client_config({
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [GOOGLE_REDIRECT_URI]
            }
        }, scopes=SCOPES, state=state_from_url)

        flow.redirect_uri = GOOGLE_REDIRECT_URI
        print(f"[CALLBACK] ✅ OAuth flow created")
        
        # Complete the OAuth flow
        print(f"[CALLBACK] Fetching token...")
        authorization_response = request.url
        print(f"[CALLBACK] Authorization response URL: {authorization_response[:150]}...")
        
        flow.fetch_token(authorization_response=authorization_response)
        credentials = flow.credentials
        print(f"[CALLBACK] ✅ Token fetched successfully")
        print(f"[CALLBACK] Token expires: {credentials.expiry}")

        # Get user info
        print(f"[CALLBACK] Fetching user info from Google...")
        user_info = requests.get(
            'https://openidconnect.googleapis.com/v1/userinfo',
            headers={'Authorization': f'Bearer {credentials.token}'}
        ).json()
        print(f"[CALLBACK] ✅ User info retrieved: {user_info.get('email')}")
        print(f"[CALLBACK] User info keys: {list(user_info.keys())}")

        try:
            handle_post_login(user_info)
        except Exception as exc:
            print(f"[CALLBACK] Failed to process login metadata: {exc}")

        # Store user Drive OAuth credentials in session when DRIVE_USER_MODE
        if DRIVE_USER_MODE and credentials:
            try:
                session['google_creds'] = {
                    'token': credentials.token,
                    'refresh_token': credentials.refresh_token,
                    'token_uri': getattr(credentials, 'token_uri', 'https://oauth2.googleapis.com/token'),
                    'client_id': credentials.client_id,
                    'client_secret': credentials.client_secret,
                    'scopes': credentials.scopes,
                }
                print('[CALLBACK] Stored user OAuth Drive credentials in session')
            except Exception as exc:
                print(f"[CALLBACK] Failed to store user creds: {exc}")

        # Store user info in ONLY the cookie (no session)
        user_json = json.dumps(user_info)
        user_b64 = base64.b64encode(user_json.encode()).decode()
        
        print(f"[CALLBACK] User info prepared for cookie: {user_info.get('email')}")
        print(f"[CALLBACK] Base64 encoded size: {len(user_b64)} bytes")

        # Redirect to Vercel frontend with dashboard flag
        # IMPORTANT: Also pass user data as query param for mobile compatibility
        user_b64_urlsafe = base64.b64encode(user_json.encode()).decode()
        frontend_url = f'{FRONTEND_URL}/?dashboard=1&auth={user_b64_urlsafe}'
        print(f"[CALLBACK] Redirecting to: {frontend_url[:100]}...")
        print("="*80)
        print("[CALLBACK] ===== OAUTH CALLBACK SUCCEEDED - SETTING COOKIE & REDIRECTING =====")
        print("="*80)
        response = redirect(frontend_url)
        
        # Determine cookie security based on environment
        # Use the global IS_PRODUCTION flag defined at the top of the file
        cookie_secure = IS_PRODUCTION
        cookie_samesite = 'None' if IS_PRODUCTION else 'Lax'
        
        # Set user_data cookie - THIS IS THE ONLY PLACE USER DATA IS STORED
        response.set_cookie(
            'user_data',
            user_b64,
            max_age=86400,  # 24 hours
            secure=cookie_secure,    # HTTPS only for production, HTTP for local
            httponly=False, # Allow JS to read if needed
            samesite=cookie_samesite, # Cross-site for prod, Lax for local
            path='/',
            domain=None  # Browser will use request domain
        )
        print(f"[CALLBACK] ✅ user_data cookie SET (Secure={cookie_secure}, SameSite={cookie_samesite})")
        
        # Clear the state cookie after verification
        response.delete_cookie('oauth_state', path='/')
        print(f"[CALLBACK] ✅ oauth_state cookie DELETED")
        print(f"[CALLBACK] Response headers: Set-Cookie = {response.headers.getlist('Set-Cookie')}")
        print("="*80 + "\n")
        
        return response
        
    except Exception as e:
        print(f"[ERROR] UNEXPECTED ERROR in callback: {e}")
        import traceback
        print(f"[ERROR] Full traceback:\n{traceback.format_exc()}")
        print("="*80 + "\n")
        return jsonify({"error": f"Callback error: {str(e)}"}), 500

@app.route('/auth/logout', methods=['POST'])
def logout():
    print(f"[DEBUG] Logout called")
    
    from flask import make_response
    response = make_response(jsonify({"message": "Logged out"}))
    
    # Delete user_data cookie
    # We must match the path and domain used when setting it
    response.set_cookie('user_data', '', expires=0, path='/', samesite='None', secure=True)
    response.set_cookie('user_data', '', expires=0, path='/', samesite='Lax', secure=False)
    
    # Delete oauth_state cookie
    response.set_cookie('oauth_state', '', expires=0, path='/')
    
    print(f"[DEBUG] Cookies deleted")
    return response

# ------------------------- PDF Processing -------------------------
@app.route('/api/upload-pdf', methods=['POST'])
def upload_pdf():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if not file.filename.lower().endswith('.pdf'):  # type: ignore
        return jsonify({"error": "Invalid file type"}), 400

    # Read file into memory to allow streaming response
    file_bytes = file.read()
    if not file_bytes:
        return jsonify({"error": "Empty file"}), 400
        
    filename = file.filename or 'uploaded.pdf'

    def generate():
        # Initial status
        yield json.dumps({"status": "progress", "percent": 0, "message": "Uploading PDF to internet..."}) + "\n"
        
        try:
            # Context setup
            user_info = decode_user_cookie()
            if not user_info:
                yield json.dumps({"error": "Authentication required"}) + "\n"
                return

            user, drive_service, folder_info = ensure_user_context(user_info)
            drive_folder_id = None
            if folder_info and folder_info.get('id'):
                drive_folder_id = folder_info['id']
            else:
                drive_folder_id = getattr(user, 'drive_folder_id', None)

            # Calculate hash early for cache lookup
            sha_hash = hashlib.sha256(file_bytes).hexdigest()
            
            # Check Drive Cache
            cached_text = None
            if drive_service and drive_folder_id:
                try:
                    yield json.dumps({"status": "progress", "percent": 5, "message": "Checking for cached text..."}) + "\n"
                    # Ensure TextCache folder exists
                    cache_folder = ensure_subfolder(drive_service, drive_folder_id, "TextCache")
                    cache_filename = f"{sha_hash}.txt"
                    
                    # Check if file exists
                    cached_file = find_named_file(drive_service, cache_folder['id'], cache_filename)
                    
                    if cached_file:
                        yield json.dumps({"status": "progress", "percent": 10, "message": "Found cached text! Downloading..."}) + "\n"
                        cached_text = read_text_file(drive_service, cached_file['id'])
                        print(f"[Cache] Hit for {filename} ({sha_hash})")
                except Exception as e:
                    print(f"[Cache] Error checking cache: {e}")

            text = ""
            if cached_text:
                text = cached_text
                yield json.dumps({"status": "progress", "percent": 80, "message": "Loaded text from cache."}) + "\n"
            else:
                yield json.dumps({"status": "progress", "percent": 15, "message": "Processing the type of PDF..."}) + "\n"

                # Extract text (with OCR fallback)
                try:
                    # Pass _groq_client for Vision LLM fallback
                    # extract_text_from_pdf_stream is now a generator
                    for update in extract_text_from_pdf_stream(file_bytes, groq_client=_groq_client):
                        if update["status"] == "progress":
                            yield json.dumps(update) + "\n"
                        elif update["status"] == "complete":
                            text = update["text"]
                        elif update["status"] == "error":
                            print(f"[PDF] Extraction error: {update['message']}")
                            # Don't fail completely, try fallback
                            break
                except Exception as e:
                    print(f"[PDF] Extraction failed: {e}")
                    # Fallback to basic extraction if helper fails
                    pdf_stream = io.BytesIO(file_bytes)
                    reader = PyPDF2.PdfReader(pdf_stream)
                    text_parts = []
                    for page in reader.pages:
                        text_parts.append(page.extract_text() or "")
                    text = "\n".join(text_parts)
                
                # Save to Cache
                if text and drive_service and drive_folder_id:
                    try:
                        yield json.dumps({"status": "progress", "percent": 90, "message": "Caching extracted text..."}) + "\n"
                        cache_folder = ensure_subfolder(drive_service, drive_folder_id, "TextCache")
                        cache_filename = f"{sha_hash}.txt"
                        upload_text_file(
                            drive_service, 
                            cache_folder['id'], 
                            cache_filename, 
                            text, 
                            mimetype="text/plain"
                        )
                        print(f"[Cache] Saved text for {filename}")
                    except Exception as e:
                        print(f"[Cache] Failed to save text: {e}")

            # Store in server-side session as backup
            # Note: This might not persist if headers are already sent and session cookie needs update
            # But usually session ID is stable.
            session['pdf_text'] = text
            
            yield json.dumps({"status": "progress", "percent": 95, "message": "Finalizing upload..."}) + "\n"
            
            # Return the original PDF bytes for the book viewer (required for pdf.js)
            pdf_b64 = base64.b64encode(file_bytes).decode('utf-8')

            # sha_hash is already calculated above

            # Check for duplicates (DB mode only)
            if not DRIVE_ONLY_MODE:
                duplicate = check_duplicate_pdf(sha_hash)
                if duplicate:
                    # If duplicate found, return existing info
                    print(f"[PDF] Duplicate found: {duplicate.filename}")
                    yield json.dumps({
                        "status": "success",
                        "message": "Duplicate PDF found. Using existing file.",
                        "is_duplicate": True,
                        "text_length": len(text),
                        "pdf_text": text,
                        "pdf_base64": pdf_b64,
                        "drive_file_id": duplicate.drive_file_id,
                        "drive_web_view_link": duplicate.drive_web_view_link,
                    }) + "\n"
                    return

            size_bytes = len(file_bytes)

            drive_metadata: Optional[Dict[str, Any]] = None
            if DRIVE_ONLY_MODE and (not drive_service or not drive_folder_id):
                yield json.dumps({
                    "error": "Drive integration not configured",
                    "details": {
                        "serviceReady": bool(drive_service is not None),
                        "driveFolderId": drive_folder_id,
                    }
                }) + "\n"
                return

            if drive_service and drive_folder_id:
                try:
                    # Ensure PDFs subfolder
                    pdfs_folder = ensure_subfolder(drive_service, drive_folder_id, "PDFs")
                    target_folder_id = pdfs_folder['id']

                    print(f"[Drive] Uploading to folder: {target_folder_id}")
                    drive_metadata = drive_upload_pdf(
                        drive_service,
                        target_folder_id,
                        filename,
                        file_bytes,
                    )
                    print(f"[Drive] Uploaded PDF {file.filename} -> {drive_metadata.get('id')}")
                except Exception as exc:
                    print(f"[Drive] Failed to upload PDF: {exc}")
                    if DRIVE_ONLY_MODE:
                        yield json.dumps({"error": f"Drive upload failed: {exc}"}) + "\n"
                        return

            user_id = getattr(user, 'id', None)
            if isinstance(user_id, int):
                try:
                    record_pdf_upload(
                        user,
                        filename,
                        drive_metadata or {},
                        sha_hash,
                        size_bytes,
                    )
                except Exception as exc:
                    print(f"[DB] Failed to record PDF upload: {exc}")
            
            print(f"[PDF] Uploaded PDF: {len(text)} characters")
            
            yield json.dumps({"status": "progress", "percent": 100, "message": "Upload successful!"}) + "\n"
            
            yield json.dumps({
                "status": "success",
                "message": "PDF uploaded successfully", 
                "text_length": len(text),
                "pdf_text": text,  # Send text to frontend
                "pdf_base64": pdf_b64,  # Also send as Base64
                "drive_file_id": (drive_metadata or {}).get('id'),
                "drive_web_view_link": (drive_metadata or {}).get('webViewLink'),
            }) + "\n"
            
        except Exception as e:
            print(f"[ERROR] PDF upload failed: {e}")
            yield json.dumps({"error": f"Failed to read PDF: {str(e)}"}) + "\n"

    return Response(stream_with_context(generate()), mimetype='application/x-ndjson')

@app.route('/api/delete-pdf', methods=['POST'])
def delete_pdf():
    """Delete PDF data from server-side session"""
    filename = request.form.get('filename', '').strip()
    
    if not filename:
        return jsonify({"error": "Filename is required"}), 400
    
    try:
        # Clear server-side PDF session data
        if 'pdf_text' in session:
            del session['pdf_text']
        
        print(f"[PDF] Deleted PDF from server: {filename}")
        return jsonify({
            "message": "PDF deleted successfully",
            "filename": filename
        })
    except Exception as e:
        print(f"[ERROR] PDF deletion failed: {e}")
        return jsonify({"error": f"Failed to delete PDF: {str(e)}"}), 500


# ------------------------- Location Reporting -------------------------


@app.route('/api/location/report', methods=['POST'])
def report_precise_location():
    """Accept precise client-side coordinates for richer location records."""
    user = ensure_current_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 401

    payload = request.get_json(silent=True) or {}
    coords = payload.get('coords') or {}

    lat_raw = coords.get('latitude')
    lon_raw = coords.get('longitude')

    if lat_raw is None or lon_raw is None:
        return jsonify({"error": "latitude and longitude are required"}), 400

    if not isinstance(lat_raw, (int, float, str)) or not isinstance(lon_raw, (int, float, str)):
        return jsonify({"error": "latitude and longitude must be numeric"}), 400

    try:
        latitude = float(lat_raw)
        longitude = float(lon_raw)
    except (TypeError, ValueError):
        return jsonify({"error": "latitude and longitude must be numeric"}), 400

    precise_location: Dict[str, Any] = {
        "latitude": latitude,
        "longitude": longitude,
        "accuracy": coords.get('accuracy'),
        "altitude": coords.get('altitude'),
        "altitudeAccuracy": coords.get('altitudeAccuracy'),
        "heading": coords.get('heading'),
        "speed": coords.get('speed'),
        "reportedAt": payload.get('timestamp'),
        "source": payload.get('source') or 'device',
    }

    address = payload.get('address')
    if isinstance(address, dict):
        precise_location['address'] = address

    if DRIVE_ONLY_MODE:
        drive_service = get_drive_service()
        if drive_service:
            try:
                folder_id = getattr(user, 'drive_folder_id', None)
                if folder_id:
                    state = load_user_json(drive_service, folder_id) or {}
                    state['last_location'] = {
                        'device': precise_location
                    }
                    save_user_json(drive_service, folder_id, state)
            except Exception as exc:
                print(f"[Drive] Failed to save precise location: {exc}")
    else:
        try:
            user_id = getattr(user, 'id', None)
            if not isinstance(user_id, int):
                # If user ID is missing, it might be a sync issue or pseudo-user.
                # Log warning but don't crash with 500.
                print(f"[WARNING] report_precise_location: User ID is not an int: {user_id}")
                return jsonify({"status": "ignored", "reason": "invalid_user_id"}), 200
            
            update_precise_location(user_id, precise_location)
        except Exception as e:
            print(f"[ERROR] report_precise_location failed: {e}")
            # Return 200 with error details to avoid CORS issues on frontend
            return jsonify({"status": "error", "error": str(e)}), 200

    return jsonify({
        "status": "location-updated",
        "location": precise_location,
    })


# ------------------------- Admin Endpoints -------------------------


@app.route('/api/admin/users', methods=['GET'])
def admin_get_users():
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Forbidden"}), 403
    if DRIVE_ONLY_MODE:
        info = decode_user_cookie() or {}
        drive_service = get_drive_service()
        folder_link = None
        if drive_service and info.get('email'):
            try:
                folder_meta = ensure_user_folder(drive_service, info.get('email', ''), info.get('name'))
                folder_link = folder_meta.get('link') if folder_meta else None
            except Exception:
                folder_link = None
        return jsonify({
            'mode': 'drive-only',
            'users': [{
                'id': None,
                'email': info.get('email'),
                'name': info.get('name'),
                'driveFolderLink': folder_link,
                'photoCaptureEnabled': False,
            }],
            'summary': {
                'totalUsers': 1,
                'totalUploads': None,
            }
        })
    payload = build_admin_user_payloads()
    return jsonify(payload)


@app.route('/api/admin/users/<int:user_id>/logins', methods=['GET'])
def admin_get_user_logins(user_id: int):
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Forbidden"}), 403
    if DRIVE_ONLY_MODE:
        return jsonify({'mode': 'drive-only', 'logins': [], 'count': 0})
    limit_param = request.args.get('limit', type=int) or 50
    limit = max(1, min(limit_param, 250))
    payload = fetch_login_events_payload(user_id, limit)
    return jsonify(payload)


@app.route('/api/admin/users/<int:user_id>/uploads', methods=['GET'])
def admin_get_user_uploads(user_id: int):
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Forbidden"}), 403
    if DRIVE_ONLY_MODE:
        info = decode_user_cookie() or {}
        drive_service = get_drive_service()
        uploads = []
        if drive_service and info.get('email'):
            try:
                folder_meta = ensure_user_folder(drive_service, info.get('email', ''), info.get('name'))
                if folder_meta and folder_meta.get('id'):
                    listing = list_folder_files(drive_service, folder_meta['id'], page_size=200).get('files', [])
                    for f in listing:
                        name = f.get('name', '')
                        if name in ('user.json', 'login_history.csv'):
                            continue
                        if f.get('mimeType') == 'application/vnd.google-apps.folder':
                            continue
                        uploads.append({
                            'filename': name,
                            'modifiedTime': f.get('modifiedTime'),
                            'driveFileId': f.get('id'),
                            'webViewLink': f.get('webViewLink'),
                        })
            except Exception:
                pass
        return jsonify({'mode': 'drive-only', 'uploads': uploads, 'count': len(uploads)})
    limit_param = request.args.get('limit', type=int) or 50
    limit = max(1, min(limit_param, 250))
    payload = fetch_upload_events_payload(user_id, limit)
    return jsonify(payload)


@app.route('/api/admin/users/<int:user_id>/photo-capture', methods=['POST'])
def admin_set_photo_capture(user_id: int):
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Forbidden"}), 403

    data = request.get_json(silent=True) or {}
    enabled = bool(data.get('enabled'))
    set_photo_capture(user_id, enabled)
    return jsonify({
        "userId": user_id,
        "photoCaptureEnabled": enabled,
    })


@app.route('/api/admin/summary', methods=['GET'])
def admin_summary():
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Forbidden"}), 403
    if DRIVE_ONLY_MODE:
        info = decode_user_cookie() or {}
        drive_service = get_drive_service()
        uploads = []
        folder_link = None
        photo_enabled = False
        if drive_service and info.get('email'):
            try:
                folder_meta = ensure_user_folder(drive_service, info.get('email', ''), info.get('name'))
                if folder_meta and folder_meta.get('id'):
                    folder_link = folder_meta.get('link')
                    state = load_user_json(drive_service, folder_meta['id']) or {}
                    photo_enabled = bool(state.get('photo_capture_enabled', False))
                    listing = list_folder_files(drive_service, folder_meta['id'], page_size=100).get('files', [])
                    for f in listing:
                        name = f.get('name', '')
                        if name in ('user.json', 'login_history.csv'):
                            continue
                        if f.get('mimeType') == 'application/vnd.google-apps.folder':
                                                       continue
                        uploads.append({
                            'filename': name,
                            'modifiedTime': f.get('modifiedTime'),
                            'driveFileId': f.get('id'),
                            'webViewLink': f.get('webViewLink'),
                        })
            except Exception as exc:
                print(f"[Drive] drive-only summary error: {exc}")

        return jsonify({
            'mode': 'drive-only',
            'admin': {
                'email': info.get('email'),
                'name': info.get('name'),
                'driveFolderLink': folder_link,
                'photoCaptureEnabled': photo_enabled,
            },
            'totals': {
                'totalUsers': 1,
                'totalUploads': len(uploads),
            },
            'recent': {
                'logins': [],
                'uploads': uploads[:10],
            }
        })
    # Normal DB-backed summary
    global_payload = build_admin_user_payloads()
    totals = global_payload.get('summary', {})
    recent_logins = fetch_login_events_payload(getattr(admin, 'id', 0), limit=10).get('logins', [])
    recent_uploads = fetch_upload_events_payload(getattr(admin, 'id', 0), limit=10).get('uploads', [])
    return jsonify({
        'mode': 'db',
        'admin': {
            'id': getattr(admin, 'id', None),
            'email': getattr(admin, 'email', None),
            'name': getattr(admin, 'name', None),
            'driveFolderLink': getattr(admin, 'drive_folder_link', None),
            'loginCsvLink': getattr(admin, 'login_csv_web_view_link', None),
            'photoCaptureEnabled': bool(getattr(admin, 'photo_capture_enabled', False)),
            'location': getattr(admin, 'location_cache', None),
            'lastLoginAt': (getattr(admin, 'last_login_at').isoformat() if getattr(admin, 'last_login_at', None) else None),
        },
        'totals': totals,
        'recent': {
            'logins': recent_logins,
            'uploads': recent_uploads,
        }
    })

@app.route('/api/admin/photo-capture', methods=['POST'])
def admin_toggle_own_photo_capture():
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Forbidden"}), 403
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get('enabled'))
    if DRIVE_ONLY_MODE:
        info = decode_user_cookie() or {}
        drive_service = get_drive_service()
        if drive_service and info.get('email'):
            try:
                folder_meta = ensure_user_folder(drive_service, info.get('email', ''), info.get('name'))
                if folder_meta and folder_meta.get('id'):
                    state = load_user_json(drive_service, folder_meta['id']) or {}
                    state['photo_capture_enabled'] = enabled
                    save_user_json(drive_service, folder_meta['id'], state)
                return jsonify({'photoCaptureEnabled': enabled})
            except Exception as exc:
                return jsonify({'error': f'Drive update failed: {exc}'}), 500
        return jsonify({'error': 'Drive not available'}), 503
    admin_id = getattr(admin, 'id', None)
    if isinstance(admin_id, int):
        set_photo_capture(admin_id, enabled)
    return jsonify({'userId': admin_id, 'photoCaptureEnabled': enabled})


@app.route('/debug/drive', methods=['GET'])
def debug_drive():
    """Admin-only: check Drive configuration and folder accessibility for current user.
    Does not expose secrets; returns booleans and minimal metadata.
    """
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Forbidden"}), 403

    import os
    root_id = os.getenv('GOOGLE_DRIVE_ROOT_FOLDER_ID') or ''
    svc = None
    if DRIVE_USER_MODE:
        svc = get_user_drive_service()
    if not svc:
        svc = get_drive_service()

    status = {
        "serviceReady": bool(svc is not None),
        "rootFolderIdSet": bool(root_id.strip() != ''),
        "rootFolderId": root_id if root_id else None,
        "ensureUserFolder": None,
        "error": None,
    }

    try:
        if svc:
            # Try ensuring the admin's folder (non-destructive)
            folder = ensure_user_folder(svc, getattr(admin, 'email', 'unknown'), getattr(admin, 'name', None))
            status["ensureUserFolder"] = folder or None
    except Exception as exc:
        status["error"] = str(exc)

    return jsonify(status)


@app.route('/api/admin/drive-test-upload', methods=['POST', 'GET'])
def admin_drive_test_upload():
    """Admin-only: create a tiny test file in Drive to verify write access."""
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Forbidden"}), 403

    svc = get_drive_service()
    info = decode_user_cookie() or {}
    if not svc or not info.get('email'):
        return jsonify({"error": "Drive service not ready or no user"}), 503

    try:
        folder = ensure_user_folder(svc, info.get('email', ''), info.get('name'))
        if not folder or not folder.get('id'):
            return jsonify({"error": "Failed to ensure user folder"}), 500
        content = f"drive-test {datetime.now(timezone.utc).isoformat()}"
        meta = upload_text_file(svc, folder['id'], 'drive_test.txt', content, mimetype='text/plain')
        return jsonify({
            "ok": True,
            "folderId": folder['id'],
            "fileId": meta.get('id'),
            "webViewLink": meta.get('webViewLink'),
        })
    except Exception as exc:
        return jsonify({"error": f"Drive test upload failed: {exc}"}), 500


@app.route('/api/admin/drive-list', methods=['GET'])
def admin_drive_list():
    """Admin-only: list files in the current user's Drive folder."""
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Forbidden"}), 403

    svc = get_drive_service()
    info = decode_user_cookie() or {}
    if not svc or not info.get('email'):
        return jsonify({"error": "Drive service not ready or no user"}), 503

    try:
        folder = ensure_user_folder(svc, info.get('email', ''), info.get('name'))
        if not folder or not folder.get('id'):
            return jsonify({"error": "Failed to ensure user folder"}), 500
        listing = list_folder_files(svc, folder['id'], page_size=200).get('files', [])
        # Filter out state files
        visible = []
        for f in listing:
            name = f.get('name', '')
            if name in ('user.json', 'login_history.csv'):
                continue
            visible.append(f)
        return jsonify({
            "folderId": folder['id'],
            "count": len(visible),
            "files": visible,
        })
    except Exception as exc:
        return jsonify({"error": f"Drive list failed: {exc}"}), 500


# ------------------------- Photo Capture -------------------------


@app.route('/api/photo-capture', methods=['POST'])
def capture_photo():
    user_info = decode_user_cookie()
    if not user_info:
        return jsonify({"error": "Authentication required"}), 401

    user, drive_service, folder_info = ensure_user_context(user_info)
    if not bool(getattr(user, 'photo_capture_enabled', False)):
        return jsonify({"message": "Photo capture disabled"}), 200

    data = request.get_json(silent=True) or {}
    image_data = data.get('imageData') or data.get('image')
    context = data.get('context', 'login')
    if not image_data:
        return jsonify({"error": "imageData is required"}), 400

    try:
        if isinstance(image_data, str) and image_data.startswith('data:'):
            _, encoded_part = image_data.split(',', 1)
        else:
            encoded_part = image_data
        file_bytes = base64.b64decode(encoded_part)
    except Exception as exc:
        return jsonify({"error": f"Invalid image data: {exc}"}), 400

    drive_folder_id = None
    if folder_info and folder_info.get('id'):
        drive_folder_id = folder_info['id']
    else:
        drive_folder_id = getattr(user, 'drive_folder_id', None)

    if not drive_service or not drive_folder_id:
        return jsonify({"error": "Drive integration not configured"}), 503

    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    filename = f"photo_{context}_{timestamp}.png"

    try:
        # Ensure Photos subfolder
        photos_folder = ensure_subfolder(drive_service, drive_folder_id, "Photos")
        target_folder_id = photos_folder['id']

        metadata = drive_upload_pdf(
            drive_service,
            target_folder_id,
            filename,
            file_bytes,
            mimetype='image/png',
        )
        user_id = getattr(user, 'id', None)
        if isinstance(user_id, int):
            record_photo_capture(user_id, context, metadata)
    except Exception as exc:
        return jsonify({"error": f"Failed to upload photo: {exc}"}), 500

    return jsonify({
        "message": "Photo captured",
        "driveFileId": metadata.get('id') if metadata else None,
        "driveWebViewLink": metadata.get('webViewLink') if metadata else None,
    })


@app.route('/api/chat', methods=['POST'])
def chat_endpoint():
    data = request.get_json()
    message = data.get('message')
    history = data.get('history', [])
    
    # Get PDF text from request (preferred) or session (fallback)
    pdf_text = data.get('pdf_text') or session.get('pdf_text', '')
    
    if not message:
        return jsonify({"error": "Message is required"}), 400

    # Construct messages for LLM
    messages = [
        {"role": "system", "content": "You are a helpful AI study assistant. Use the provided context to answer the user's questions accurately."}
    ]
    
    # Add history (limit to last 10 messages to save tokens)
    # History is expected to be a list of {role, content} objects
    for h in history[-10:]:
        role = h.get('role')
        content = h.get('content')
        if role and content:
            messages.append({"role": role, "content": content})
        
    messages.append({"role": "user", "content": message})
    
    try:
        # Use RAG-enabled chat
        response_text = llm_chat(messages, context_text=pdf_text)
        
        # Record usage
        user = ensure_current_user()
        if user and not DRIVE_ONLY_MODE:
             user_id = getattr(user, 'id', None)
             if isinstance(user_id, int):
                 record_feature_usage(user_id, "chat", message[:50], "current_session.pdf")

        return jsonify({"response": response_text})
    except Exception as e:
        print(f"[Chat] Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate-mindmap', methods=['POST'])
def generate_mindmap():
    data = request.get_json()
    pdf_text = data.get('text') or data.get('pdf_text') or session.get('pdf_text', '')
    
    if not pdf_text:
        return jsonify({"error": "No PDF loaded"}), 400
        
    try:
        # Limit text for mindmap generation (take first 50k chars)
        # Clean text to avoid quote issues and confusion
        clean_text = pdf_text[:50000].replace('"', "'").replace('\n', ' ')
        
        prompt = f"""
        Create a Mermaid.js mindmap code based on the text below.
        
        STRICT RULES:
        1. Start with `mindmap`
        2. Use exactly ONE root node.
        3. Indent child nodes using exactly 2 spaces per level.
        4. WRAP ALL NODE TEXT IN DOUBLE QUOTES. Example: `root(("Main Topic"))` or `  "Subtopic"`
        5. KEEP LABELS SHORT (max 5 words).
        6. REMOVE ALL SPECIAL CHARACTERS from labels (commas, parentheses, brackets, etc). Use only letters and numbers.
        7. Return ONLY the Mermaid code. No markdown blocks.
        8. ENSURE EVERY NODE IS ON A NEW LINE. Never put multiple nodes on the same line.

        Example:
        mindmap
          root(("Main Topic"))
            "Subtopic 1"
              "Detail A"
            "Subtopic 2"
              "Detail B"

        Text to visualize:
        {clean_text}
        """
        
        messages = [{"role": "user", "content": prompt}]
        mermaid_code = llm_chat(messages, temperature=0.1)
        
        # Clean up response if it contains markdown blocks
        mermaid_code = mermaid_code.replace("```mermaid", "").replace("```", "").strip()
        
        # Record usage
        user = ensure_current_user()
        if user and not DRIVE_ONLY_MODE:
             user_id = getattr(user, 'id', None)
             if isinstance(user_id, int):
                 record_feature_usage(user_id, "mindmap", "generated", "current_session.pdf")

        return jsonify({"mermaid_code": mermaid_code})
    except Exception as e:
        print(f"[Mindmap] Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/notes', methods=['GET', 'POST'])
def manage_notes():
    user = ensure_current_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 401
        
    if DRIVE_ONLY_MODE:
        return jsonify({"error": "Notes not supported in Drive-only mode"}), 501
        
    user_id = getattr(user, 'id', None)
    if not isinstance(user_id, int):
        return jsonify({"error": "Invalid user"}), 400

    if request.method == 'GET':
        with db_session() as session:
            notes = session.query(Note).filter(Note.user_id == user_id).order_by(Note.updated_at.desc()).all()
            return jsonify({
                "notes": [
                    {
                        "id": n.id,
                        "content": n.content,
                        "pdf_filename": n.pdf_filename,
                        "updated_at": n.updated_at.isoformat()
                    } for n in notes
                ]
            })
            
    elif request.method == 'POST':
        data = request.get_json()
        content = data.get('content')
        pdf_filename = data.get('pdf_filename')
        
        if not content:
            return jsonify({"error": "Content required"}), 400
            
        with db_session() as session:
            new_note = Note(user_id=user_id, content=content, pdf_filename=pdf_filename)
            session.add(new_note)
            session.commit()
            return jsonify({"status": "created", "id": new_note.id})
            
    return jsonify({"error": "Method not allowed"}), 405

@app.route('/api/notes/<int:note_id>', methods=['PUT', 'DELETE'])
def manage_single_note(note_id):
    user = ensure_current_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 401
        
    if DRIVE_ONLY_MODE:
        return jsonify({"error": "Notes not supported in Drive-only mode"}), 501
        
    user_id = getattr(user, 'id', None)
    if not isinstance(user_id, int):
        return jsonify({"error": "Invalid user"}), 400

    if request.method == 'PUT':
        data = request.get_json()
        content = data.get('content')
        
        if not content:
            return jsonify({"error": "Content required"}), 400
            
        with db_session() as session:
            note = session.query(Note).filter(Note.id == note_id, Note.user_id == user_id).first()
            if note:
                note.content = content
                session.commit()
                return jsonify({"status": "updated", "id": note.id})
            return jsonify({"error": "Note not found"}), 404

    elif request.method == 'DELETE':
        with db_session() as session:
            note = session.query(Note).filter(Note.id == note_id, Note.user_id == user_id).first()
            if note:
                session.delete(note)
                session.commit()
                return jsonify({"status": "deleted"})
            return jsonify({"error": "Note not found"}), 404
            
    return jsonify({"error": "Method not allowed"}), 405

@app.route('/api/books', methods=['GET'])
def get_books():
    user = ensure_current_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 401
        
    # Reuse logic from admin_get_user_uploads but for current user
    if DRIVE_ONLY_MODE:
        # ... (Drive listing logic similar to admin)
        # For brevity, reusing the admin logic structure or calling it if possible
        # But here we just list files from the user's PDF folder
        drive_service = get_drive_service()
        books = []
        if drive_service:
            try:
                folder_id = getattr(user, 'drive_folder_id', None)
                if folder_id:
                    pdfs_folder = find_named_file(drive_service, folder_id, "PDFs")
                    if pdfs_folder:
                        files = list_folder_files(drive_service, pdfs_folder['id'], page_size=50).get('files', [])
                        for f in files:
                             books.append({
                                'filename': f.get('name'),
                                'driveFileId': f.get('id'),
                                'webViewLink': f.get('webViewLink'),
                                'thumbnailLink': f.get('thumbnailLink') # Drive provides thumbnails
                            })
            except Exception as e:
                print(f"[Books] Drive error: {e}")
        return jsonify({"books": books})
    
    # DB Mode
    user_id = getattr(user, 'id', None)
    if isinstance(user_id, int):
        payload = fetch_upload_events_payload(user_id, limit=100)
        return jsonify({"books": payload.get('uploads', [])})
    
    return jsonify({"books": []})

@app.route('/api/summarize', methods=['POST'])
def summarize_endpoint():
    data = request.get_json()
    pdf_text = data.get('pdf_text') or session.get('pdf_text', '')
    
    if not pdf_text:
        return jsonify({"error": "No PDF loaded"}), 400
        
    try:
        # Use RAG to get key sections or just summarize the beginning if too long
        # For summary, we usually want the whole thing, but token limits apply.
        # Strategy: Chunk, summarize chunks, then summarize summaries.
        # For simplicity in this demo: Truncate to 100k chars (Llama 3.3 supports 128k context).
        context = pdf_text[:100000]
        
        prompt = f"""
        Analyze the following text and provide a comprehensive, intelligent summary.
        Format the output as clean HTML (without ```html code blocks).
        
        Structure & Styling requirements:
        - Use <h3 style="color: #2c3e50; font-family: 'Segoe UI', sans-serif; border-bottom: 2px solid #3498db; padding-bottom: 5px;"> for main section headings.
        - Use <h4 style="color: #16a085; font-family: 'Segoe UI', sans-serif; margin-top: 15px;"> for sub-points or key concepts.
        - Use <ul style="list-style-type: disc; padding-left: 20px; color: #34495e;"> for lists.
        - Use <li style="margin-bottom: 5px;"> for list items.
        - Use <p style="color: #2c3e50; line-height: 1.6;"> for explanatory text.
        - Use <strong> for key terms.
        - Do NOT use <h1> or <h2> tags.
        - Do NOT include <html>, <head>, or <body> tags.
        
        Content requirements:
        - Capture the core arguments and evidence.
        - Highlight key definitions and terminology.
        - Maintain a professional and academic tone.
        - If the text is technical, explain complex terms simply.
        
        Text:
        {context}
        """
        
        messages = [{"role": "user", "content": prompt}]
        # Increase max_tokens for summary to avoid truncation
        summary = llm_chat(messages, max_tokens=4000)
        
        # Record usage
        user = ensure_current_user()
        if user and not DRIVE_ONLY_MODE:
             user_id = getattr(user, 'id', None)
             if isinstance(user_id, int):
                 record_feature_usage(user_id, "summarize", "generated", "current_session.pdf")

        return jsonify({"summary": summary})
    except Exception as e:
        print(f"[Summarize] Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/quiz', methods=['POST'])
def quiz_endpoint():
    data = request.get_json()
    count = data.get('count', 5)
    pdf_text = data.get('pdf_text') or session.get('pdf_text', '')
    
    if not pdf_text:
        return jsonify({"error": "No PDF loaded"}), 400
        
    try:
        # Randomly sample a chunk to generate quiz from, or use the beginning
        import random
        chunks = chunk_text(pdf_text, chunk_size=3000)
        selected_chunk = random.choice(chunks) if chunks else pdf_text[:3000]
        
        prompt = f"""
        Generate {count} multiple-choice questions based on the text below.
        Return the result as a JSON array of objects with keys: 'question', 'options' (array of strings), 'correctAnswer' (index 0-3).
        Do not include markdown formatting. Just the raw JSON.
        
        Text:
        {selected_chunk}
        """
        
        messages = [{"role": "user", "content": prompt}]
        response = llm_chat(messages, temperature=0.3)
        
        # Clean JSON
        response = response.replace("```json", "").replace("```", "").strip()
        
        import json
        quiz_data = json.loads(response)
        
        # Record usage
        user = ensure_current_user()
        if user and not DRIVE_ONLY_MODE:
             user_id = getattr(user, 'id', None)
             if isinstance(user_id, int):
                 record_feature_usage(user_id, "quiz", f"{count} questions", "current_session.pdf")

        return jsonify({"quiz": quiz_data})
    except Exception as e:
        print(f"[Quiz] Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/flashcards', methods=['POST'])
def flashcards_endpoint():
    data = request.get_json()
    count = data.get('count', 10)
    pdf_text = data.get('pdf_text') or session.get('pdf_text', '')
    
    if not pdf_text:
        return jsonify({"error": "No PDF loaded"}), 400
        
    try:
        context = pdf_text[:15000] # Use first 15k chars
        
        prompt = f"""
        Generate {count} flashcards based on the text below.
        Return the result as a JSON array of objects with keys: 'front', 'back'.
        Front should be a term or question, Back should be the definition or answer.
        Do not include markdown formatting. Just the raw JSON.
        
        Text:
        {context}
        """
        
        messages = [{"role": "user", "content": prompt}]
        response = llm_chat(messages, temperature=0.3)
        
        # Clean JSON
        response = response.replace("```json", "").replace("```", "").strip()
        
        import json
        cards_data = json.loads(response)
        
        # Record usage
        user = ensure_current_user()
        if user and not DRIVE_ONLY_MODE:
             user_id = getattr(user, 'id', None)
             if isinstance(user_id, int):
                 record_feature_usage(user_id, "flashcards", f"{count} cards", "current_session.pdf")

        return jsonify({"flashcards": cards_data})
    except Exception as e:
        print(f"[Flashcards] Error: {e}")
        return jsonify({"error": str(e)}), 500
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
