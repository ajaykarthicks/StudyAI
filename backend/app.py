import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  # Allow HTTPS and HTTP

from flask import Flask, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from flask_session import Session
from dotenv import load_dotenv
import google_auth_oauthlib.flow
from groq import Groq
import PyPDF2
import requests
import hashlib
import hmac
import json
import secrets
import base64

load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# Enable CORS for frontend with cookies
# Allow all origins during development, lock down in production if needed
CORS(app, 
     supports_credentials=True, 
     resources={r"*": {
         "origins": "*",  # Allow all origins
         "methods": ["GET", "POST", "OPTIONS"],
         "allow_headers": ["Content-Type"],
         "expose_headers": ["Content-Type"]
     }},
     max_age=3600
)

print(f"[CORS] Allowed origins: * (All origins)")

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

def llm_chat(messages, max_tokens=500, temperature=0.2):
    if not _groq_client:
        raise RuntimeError("GROQ_API_KEY is not set on the server")
    resp = _groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature
    )
    return resp.choices[0].message.content

# OAuth scopes (use full URIs to avoid scope-change warnings)
SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile'
]

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
    # ONLY check for user_data cookie
    user_cookie = request.cookies.get('user_data')
    print(f"[DEBUG] /me called - checking for user_data cookie")
    
    if user_cookie:
        try:
            user_json = base64.b64decode(user_cookie).decode('utf-8')
            user = json.loads(user_json)
            print(f"[DEBUG] User from cookie: {user.get('email')} ✅")
            return jsonify({"authenticated": True, "user": user}), 200
        except Exception as e:
            print(f"[DEBUG] Failed to decode user_data cookie: {e}")
            return jsonify({"authenticated": False, "error": str(e)}), 400
    
    print(f"[DEBUG] No user_data cookie found ❌")
    return jsonify({"authenticated": False}), 401

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
    state_from_url = request.args.get('state')
    code = request.args.get('code')
    
    print(f"[DEBUG] Callback received")
    print(f"[DEBUG] Received state: {state_from_url}")
    print(f"[DEBUG] Received code: {code[:50] if code else 'None'}...")
    
    # Verify state from cookie
    state_from_cookie = request.cookies.get('oauth_state')
    print(f"[DEBUG] Cookie state: {state_from_cookie}")
    
    if not state_from_url or not state_from_cookie or state_from_url != state_from_cookie:
        print(f"[ERROR] State mismatch! URL state: {state_from_url}, Cookie state: {state_from_cookie}")
        return jsonify({"error": "Invalid state"}), 400
    
    print(f"[DEBUG] State verified successfully")
    
    # Create flow again with the stored state
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
    
    # Complete the OAuth flow
    authorization_response = request.url
    print(f"[DEBUG] Authorization response URL: {authorization_response[:150]}...")
    
    try:
        flow.fetch_token(authorization_response=authorization_response)
        credentials = flow.credentials
        print(f"[DEBUG] Token fetched successfully")
    except Exception as e:
        print(f"[ERROR] Failed to fetch token: {e}")
        return jsonify({"error": str(e)}), 400

    # Get user info
    try:
        user_info = requests.get(
            'https://openidconnect.googleapis.com/v1/userinfo',
            headers={'Authorization': f'Bearer {credentials.token}'}
        ).json()
        print(f"[DEBUG] User info retrieved: {user_info.get('email')}")
    except Exception as e:
        print(f"[ERROR] Failed to get user info: {e}")
        return jsonify({"error": str(e)}), 400

    # Store user info in ONLY the cookie (no session)
    # Cookie is sent with every request automatically
    user_json = json.dumps(user_info)
    user_b64 = base64.b64encode(user_json.encode()).decode()
    
    print(f"[DEBUG] User info prepared for cookie: {user_info.get('email')}")

    # Redirect to Vercel frontend with dashboard flag
    frontend_url = f'{FRONTEND_URL}/?dashboard=1'
    print(f"[DEBUG] Redirecting to: {frontend_url}")
    print("=" * 60)
    print("[DEBUG] OAUTH CALLBACK SUCCEEDED - redirecting to Vercel")
    print("=" * 60)
    response = redirect(frontend_url)
    
    # Set user_data cookie - THIS IS THE ONLY PLACE USER DATA IS STORED
    response.set_cookie(
        'user_data',
        user_b64,
        max_age=86400,  # 24 hours
        secure=False,   # Allow HTTP
        httponly=False, # Allow JS to read if needed
        samesite='None', # Cross-site (important for Vercel -> Railway)
        path='/'
    )
    print(f"[DEBUG] user_data cookie SET with {len(user_b64)} bytes")
    
    # Clear the state cookie after verification
    response.delete_cookie('oauth_state', path='/')
    
    return response

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
        # Read PDF in-memory
        reader = PyPDF2.PdfReader(file)  # type: ignore
        text_parts = []
        for page in reader.pages:
            # Some PDFs may return None for empty pages
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
        text = "\n".join(text_parts)

        # Store in server-side session
        session['pdf_text'] = text
        return jsonify({"message": "PDF uploaded successfully", "text_length": len(text)})
    except Exception as e:
        return jsonify({"error": f"Failed to read PDF: {str(e)}"}), 500

@app.route('/api/chat', methods=['POST'])
def chat_with_pdf():
    data = request.get_json(silent=True) or {}
    question = data.get('question', '').strip()
    pdf_text = session.get('pdf_text', '')

    if not pdf_text:
        return jsonify({"error": "No PDF uploaded"}), 400
    if not question:
        return jsonify({"error": "Question is required"}), 400

    try:
        context_snippet = pdf_text[:12000]  # Keep prompt reasonable
        answer = llm_chat(
            messages=[
                {"role": "system", "content": f"You are a helpful assistant. Answer ONLY using the information in this document. If not found, say you don't know. Document:\n{context_snippet}"},
                {"role": "user", "content": question}
            ],
            max_tokens=500,
            temperature=0.2
        )
        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/summarize', methods=['POST'])
def summarize_pdf():
    pdf_text = session.get('pdf_text', '')
    if not pdf_text:
        return jsonify({"error": "No PDF uploaded"}), 400

    try:
        summary = llm_chat(
            messages=[
                {"role": "system", "content": "Summarize the following document clearly and concisely in bullet points."},
                {"role": "user", "content": pdf_text[:12000]}
            ],
            max_tokens=400,
            temperature=0.3
        )
        return jsonify({"summary": summary})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate-quiz', methods=['POST'])
def generate_quiz():
    pdf_text = session.get('pdf_text', '')
    data = request.get_json(silent=True) or {}
    num_questions = int(data.get('num_questions', 5))

    if not pdf_text:
        return jsonify({"error": "No PDF uploaded"}), 400

    try:
        content = llm_chat(
            messages=[
                {"role": "system", "content": f"Generate {num_questions} multiple-choice questions based ONLY on the document. Return STRICT JSON: an array of objects with fields: question (string), options (array of 4 strings), correct_answer_index (0-3). No extra text."},
                {"role": "user", "content": pdf_text[:12000]}
            ],
            max_tokens=800,
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
    pdf_text = session.get('pdf_text', '')
    data = request.get_json(silent=True) or {}
    num_cards = int(data.get('num_cards', 10))

    if not pdf_text:
        return jsonify({"error": "No PDF uploaded"}), 400

    try:
        content = llm_chat(
            messages=[
                {"role": "system", "content": f"Create {num_cards} flashcards from the document. Return STRICT JSON: an array of objects with 'front' and 'back' strings. No extra commentary."},
                {"role": "user", "content": pdf_text[:12000]}
            ],
            max_tokens=800,
            temperature=0.3
        )

        import json
        try:
            cards = json.loads(content)  # type: ignore
            return jsonify({"flashcards": cards})
        except Exception:
            return jsonify({"flashcards_text": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)