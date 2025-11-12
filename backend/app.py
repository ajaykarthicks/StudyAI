import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  # Allow HTTPS and HTTP

import base64
import csv
import hashlib
import io
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from flask import Flask, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from flask_session import Session
from dotenv import load_dotenv
import google_auth_oauthlib.flow
import PyPDF2
import requests
from groq import Groq
from sqlalchemy import func

from db import init_db, db_session
from models import DailyUploadStat, LoginEvent, PdfUpload, User
from services.google_drive import (
    download_file,
    ensure_user_folder,
    get_drive_service,
    upload_pdf as drive_upload_pdf,
    upload_text_file,
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
)

load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# Get frontend URL for CORS
FRONTEND_URL_FOR_CORS = os.getenv('FRONTEND_URL', 'https://studyai-gamma.vercel.app')

# Enable CORS for frontend with cookies
# IMPORTANT: Must specify actual origin, not *, when using credentials=True
CORS(app, 
     supports_credentials=True,
     origins=[FRONTEND_URL_FOR_CORS],  # Specific origin (not * when using cookies)
     methods=["GET", "POST", "OPTIONS", "PUT", "DELETE"],
     allow_headers=["Content-Type", "Authorization"],
     expose_headers=["Content-Type", "Set-Cookie"],
     max_age=3600
)

print(f"[CORS] Allowed origin: {FRONTEND_URL_FOR_CORS}")
print(f"[CORS] supports_credentials=True (cookies enabled)")

# Use server-side session ONLY for PDF storage (not auth)
# Auth uses cookies only
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600
print(f"[Session] Enabled for PDF storage only - auth uses COOKIES")
Session(app)

ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'ajaykarthick1207@gmail.com')

# Initialize database schema on startup
init_db()

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
FRONTEND_URL = os.getenv('FRONTEND_URL', 'https://studyai-gamma.vercel.app')

# Detect environment
if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    print(f"[WARNING] GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not set!")
    print(f"[WARNING] OAuth will not work - set these env vars on Railway")

# Production - use Railway public domain, fallback to env var
RAILWAY_PUBLIC_DOMAIN = os.getenv('RAILWAY_PUBLIC_DOMAIN') or os.getenv('RAILWAY_DOMAIN') or 'studyai-production.up.railway.app'

BACKEND_URL = f"https://{RAILWAY_PUBLIC_DOMAIN}"
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
GROQ_MODEL = os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')
print(f"[Init] Using Groq model: {GROQ_MODEL}")
_groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Unified chat helper: Groq only

def llm_chat(messages, max_tokens=None, temperature=0.2):
    if not _groq_client:
        raise RuntimeError("GROQ_API_KEY is not set on the server")
    
    # If max_tokens is not specified, let Groq use its default (no limit)
    kwargs = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": temperature
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    
    resp = _groq_client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content

# OAuth scopes (use full URIs to avoid scope-change warnings)
SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile'
]


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
    drive_service = get_drive_service()
    folder_info = None
    if drive_service:
        try:
            folder_info = ensure_user_folder(drive_service, user_info['email'], user_info.get('name'))
        except Exception as exc:
            print(f"[Drive] Failed to ensure user folder: {exc}")
            folder_info = None
    user = get_or_create_user(user_info, folder_info)
    user_id = getattr(user, 'id', None)
    if folder_info and isinstance(user_id, int):
        update_user_drive_folder(user_id, folder_info)

    if isinstance(user_id, int):
        with db_session() as session:
            refreshed = session.query(User).filter_by(id=user_id).first()
            if refreshed:
                # Load relationships before expunging to avoid lazy loads later
                _ = getattr(refreshed, 'drive_folder_id', None)
                _ = getattr(refreshed, 'photo_capture_enabled', None)
                _ = getattr(refreshed, 'login_csv_file_id', None)
                session.expunge(refreshed)
                return refreshed, drive_service, folder_info
    return user, drive_service, folder_info


def ensure_current_user() -> Optional[User]:
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


def append_login_csv_if_possible(user: User, drive_service, location: Optional[Dict[str, Any]], ip_address: Optional[str], user_agent: Optional[str]) -> None:
    drive_folder_id = getattr(user, 'drive_folder_id', None)
    login_csv_file_id = getattr(user, 'login_csv_file_id', None)
    login_csv_file_name = getattr(user, 'login_csv_file_name', 'login_history.csv')

    if not drive_service or not drive_folder_id:
        return

    existing_content = ""
    if login_csv_file_id:
        try:
            existing_bytes = download_file(drive_service, login_csv_file_id)
            existing_content = existing_bytes.decode('utf-8')
        except Exception as exc:
            print(f"[Drive] Failed to download login CSV: {exc}")
            existing_content = ""

    rows = []
    if existing_content:
        reader = csv.reader(existing_content.splitlines())
        rows = list(reader)
    else:
        rows = [[
            'timestamp',
            'ip',
            'city',
            'region',
            'country',
            'latitude',
            'longitude',
            'timezone',
            'user_agent',
        ]]

    loc = extract_location_for_csv(location)

    def csv_value(key: str) -> str:
        value = loc.get(key, '')
        return value if isinstance(value, str) else str(value)

    rows.append([
        datetime.now(timezone.utc).isoformat(),
        ip_address or '',
        csv_value('city'),
        csv_value('region'),
        csv_value('country'),
        csv_value('latitude'),
        csv_value('longitude'),
        csv_value('timezone'),
        (user_agent or '').replace('\n', ' '),
    ])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(rows)

    try:
        metadata = upload_text_file(
            drive_service,
            drive_folder_id,
            login_csv_file_name,
            output.getvalue(),
            existing_file_id=login_csv_file_id,
        )
        user_id = getattr(user, 'id', None)
        file_id = metadata.get('id') if metadata else None
        if isinstance(user_id, int) and isinstance(file_id, str):
            update_login_csv_metadata(user_id, file_id, metadata.get('webViewLink'))
    except Exception as exc:
        print(f"[Drive] Failed to upload login CSV: {exc}")


def handle_post_login(user_info: Dict[str, Any]) -> None:
    user, drive_service, _ = ensure_user_context(user_info)
    ip_address = get_client_ip()
    user_agent = request.headers.get('User-Agent')
    ip_location = lookup_location(ip_address)
    location_payload = build_login_location_payload(ip_location, ip_address)
    record_login_event(user, ip_address, user_agent, location_payload)
    append_login_csv_if_possible(user, drive_service, location_payload, ip_address, user_agent)


def require_admin() -> Optional[User]:
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

            session.expunge(user)
            users_payload.append(serialize_user_for_admin(user, daily_stats, uploads_count))

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
    print(f"[DEBUG] /me called - verifying cookies and DB record")

    user_info = decode_user_cookie()
    if not user_info:
        print(f"[DEBUG] No user_data cookie found ❌")
        return jsonify({"authenticated": False}), 401

    response_payload: Dict[str, Any] = {
        "authenticated": True,
        "user": user_info,
    }

    user_record = ensure_current_user()
    if user_record:
        user_id = getattr(user_record, 'id', None)
        email = getattr(user_record, 'email', None)
        response_payload.update(
            {
                "dbUser": {
                    "id": user_id,
                    "email": email,
                    "name": getattr(user_record, 'name', None),
                    "driveFolderLink": getattr(user_record, 'drive_folder_link', None),
                    "loginCsvLink": getattr(user_record, 'login_csv_web_view_link', None),
                },
                "photoCaptureEnabled": bool(getattr(user_record, 'photo_capture_enabled', False)),
                "isAdmin": bool(isinstance(email, str) and email == ADMIN_EMAIL),
            }
        )
    else:
        response_payload["isAdmin"] = False

    print(f"[DEBUG] User from cookie: {user_info.get('email')} ✅")
    print(f"[DEBUG] isAdmin={response_payload.get('isAdmin')}")
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
        
        # Set user_data cookie - THIS IS THE ONLY PLACE USER DATA IS STORED
        # CRITICAL: Must use SameSite=None with Secure=True for cross-site cookies
        response.set_cookie(
            'user_data',
            user_b64,
            max_age=86400,  # 24 hours
            secure=True,    # HTTPS only for production
            httponly=False, # Allow JS to read if needed
            samesite='None', # Cross-site (important for Vercel -> Railway)
            path='/',
            domain=None  # Browser will use request domain
        )
        print(f"[CALLBACK] ✅ user_data cookie SET")
        
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
    response.delete_cookie('user_data', path='/', samesite='None')
    response.delete_cookie('oauth_state', path='/')
    
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

    try:
        filename = file.filename or 'uploaded.pdf'
        user_info = decode_user_cookie()
        if not user_info:
            return jsonify({"error": "Authentication required"}), 401

        user, drive_service, folder_info = ensure_user_context(user_info)
        drive_folder_id = None
        if folder_info and folder_info.get('id'):
            drive_folder_id = folder_info['id']
        else:
            drive_folder_id = getattr(user, 'drive_folder_id', None)

        file_bytes = file.read()
        if not file_bytes:
            return jsonify({"error": "Empty file"}), 400

        pdf_stream = io.BytesIO(file_bytes)
        # Read PDF in-memory
        reader = PyPDF2.PdfReader(pdf_stream)  # type: ignore
        text_parts = []
        for page in reader.pages:
            # Some PDFs may return None for empty pages
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
        text = "\n".join(text_parts)

        # Store in server-side session as backup
        session['pdf_text'] = text
        
        # Also return the text to frontend for client-side storage
        pdf_b64 = base64.b64encode(text.encode()).decode()

        sha_hash = hashlib.sha256(file_bytes).hexdigest()
        size_bytes = len(file_bytes)

        drive_metadata: Optional[Dict[str, Any]] = None
        if drive_service and drive_folder_id:
            try:
                drive_metadata = drive_upload_pdf(
                    drive_service,
                    drive_folder_id,
                    filename,
                    file_bytes,
                )
                print(f"[Drive] Uploaded PDF {file.filename} -> {drive_metadata.get('id')}")
            except Exception as exc:
                print(f"[Drive] Failed to upload PDF: {exc}")

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
        
        print(f"[PDF] Uploaded PDF: {len(text)} characters, {len(reader.pages)} pages")
        return jsonify({
            "message": "PDF uploaded successfully", 
            "text_length": len(text),
            "pdf_text": text,  # Send text to frontend
            "pdf_base64": pdf_b64,  # Also send as Base64
            "drive_file_id": (drive_metadata or {}).get('id'),
            "drive_web_view_link": (drive_metadata or {}).get('webViewLink'),
        })
    except Exception as e:
        print(f"[ERROR] PDF upload failed: {e}")
        return jsonify({"error": f"Failed to read PDF: {str(e)}"}), 500

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

    user_id = getattr(user, 'id', None)
    if not isinstance(user_id, int):
        return jsonify({"error": "User record is malformed"}), 500

    update_precise_location(user_id, precise_location)

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

    payload = build_admin_user_payloads()
    return jsonify(payload)


@app.route('/api/admin/users/<int:user_id>/logins', methods=['GET'])
def admin_get_user_logins(user_id: int):
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Forbidden"}), 403

    limit_param = request.args.get('limit', type=int) or 50
    limit = max(1, min(limit_param, 250))
    payload = fetch_login_events_payload(user_id, limit)
    return jsonify(payload)


@app.route('/api/admin/users/<int:user_id>/uploads', methods=['GET'])
def admin_get_user_uploads(user_id: int):
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Forbidden"}), 403

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
    """Return a compact summary for the admin dashboard (current admin context + global stats)."""
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Forbidden"}), 403

    # Global summary (reuse existing builder for totals only)
    global_payload = build_admin_user_payloads()
    totals = global_payload.get("summary", {})

    # Admin user specific data
    admin_payload = {
        "id": getattr(admin, 'id', None),
        "email": getattr(admin, 'email', None),
        "name": getattr(admin, 'name', None),
        "driveFolderLink": getattr(admin, 'drive_folder_link', None),
        "loginCsvLink": getattr(admin, 'login_csv_web_view_link', None),
        "photoCaptureEnabled": bool(getattr(admin, 'photo_capture_enabled', False)),
        "location": getattr(admin, 'location_cache', None),
        "lastLoginAt": (getattr(admin, 'last_login_at').isoformat() if getattr(admin, 'last_login_at', None) else None),
    }

    # Recent events (limit small for dashboard)
    recent_logins = fetch_login_events_payload(getattr(admin, 'id', 0), limit=10).get('logins', [])
    recent_uploads = fetch_upload_events_payload(getattr(admin, 'id', 0), limit=10).get('uploads', [])

    return jsonify({
        "admin": admin_payload,
        "totals": totals,
        "recent": {
            "logins": recent_logins,
            "uploads": recent_uploads,
        }
    })


@app.route('/api/admin/photo-capture', methods=['POST'])
def admin_toggle_own_photo_capture():
    """Toggle photo capture for the current admin user (shortcut endpoint)."""
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Forbidden"}), 403

    data = request.get_json(silent=True) or {}
    enabled = bool(data.get('enabled'))
    admin_id = getattr(admin, 'id', None)
    if isinstance(admin_id, int):
        set_photo_capture(admin_id, enabled)
    return jsonify({
        "userId": admin_id,
        "photoCaptureEnabled": enabled,
    })


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
        metadata = drive_upload_pdf(
            drive_service,
            drive_folder_id,
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
def chat_with_pdf():
    data = request.get_json(silent=True) or {}
    question = data.get('question', '').strip()
    
    # Try to get PDF from request body first (client-side), then fall back to session
    pdf_text = data.get('pdf_text', '') or session.get('pdf_text', '')

    if not pdf_text:
        return jsonify({"error": "No PDF uploaded"}), 400
    if not question:
        return jsonify({"error": "Question is required"}), 400

    try:
        answer = llm_chat(
            messages=[
                {"role": "system", "content": f"You are a helpful assistant. Answer ONLY using the information in this document. If not found, say you don't know. Document:\n{pdf_text}"},
                {"role": "user", "content": question}
            ],
            temperature=0.2
        )
        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/summarize', methods=['POST'])
def summarize_pdf():
    data = request.get_json(silent=True) or {}
    # Try to get PDF from request body first (client-side), then fall back to session
    pdf_text = data.get('pdf_text', '') or session.get('pdf_text', '')
    
    if not pdf_text:
        return jsonify({"error": "No PDF uploaded"}), 400

    try:
        summary = llm_chat(
            messages=[
                {"role": "system", "content": "Summarize the following document clearly and concisely in bullet points."},
                {"role": "user", "content": pdf_text}
            ],
            temperature=0.3
        )
        return jsonify({"summary": summary})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate-quiz', methods=['POST'])
def generate_quiz():
    data = request.get_json(silent=True) or {}
    # Try to get PDF from request body first (client-side), then fall back to session
    pdf_text = data.get('pdf_text', '') or session.get('pdf_text', '')
    num_questions = int(data.get('num_questions', 5))

    if not pdf_text:
        return jsonify({"error": "No PDF uploaded"}), 400

    try:
        content = llm_chat(
            messages=[
                {"role": "system", "content": f"Generate {num_questions} multiple-choice questions based ONLY on the document. Return STRICT JSON: an array of objects with fields: question (string), options (array of 4 strings), correct_answer_index (0-3). No extra text."},
                {"role": "user", "content": pdf_text}
            ],
            temperature=0.3
        )

        # Try parsing as JSON, but if it fails, return raw content
        import json
        try:
            quiz = json.loads(content)  # type: ignore
            return jsonify({"quiz": quiz})
        except Exception:
            return jsonify({"quiz_text": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate-flashcards', methods=['POST'])
def generate_flashcards():
    data = request.get_json(silent=True) or {}
    # Try to get PDF from request body first (client-side), then fall back to session
    pdf_text = data.get('pdf_text', '') or session.get('pdf_text', '')
    num_cards = int(data.get('num_cards', 10))

    print(f"[Flashcards] Generating {num_cards} flashcards from PDF of size {len(pdf_text)} characters")

    if not pdf_text:
        return jsonify({"error": "No PDF uploaded"}), 400

    try:
        content = llm_chat(
            messages=[
                {"role": "system", "content": f"Create {num_cards} flashcards from the document. Return STRICT JSON: an array of objects with 'front' and 'back' strings. No extra commentary."},
                {"role": "user", "content": pdf_text}
            ],
            temperature=0.3
        )

        if content:
            print(f"[Flashcards] LLM Response: {str(content)[:200]}...")
        else:
            print("[Flashcards] LLM returned empty response")

        import json
        try:
            cards = json.loads(content)  # type: ignore
            print(f"[Flashcards] Successfully parsed {len(cards)} flashcards")
            return jsonify({"flashcards": cards})
        except Exception as e:
            print(f"[Flashcards] Failed to parse JSON: {e}")
            print(f"[Flashcards] Raw content: {content}")
            # Try to extract JSON from the response if it's embedded in text
            import re
            if content:
                json_match = re.search(r'\[.*\]', str(content), re.DOTALL)
                if json_match:
                    try:
                        cards = json.loads(json_match.group())
                        print(f"[Flashcards] Extracted {len(cards)} flashcards from embedded JSON")
                        return jsonify({"flashcards": cards})
                    except:
                        pass
            return jsonify({"flashcards_text": content})
    except Exception as e:
        print(f"[Flashcards] Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)