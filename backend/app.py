import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '0'  # HTTPS only for production

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

load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# Store OAuth flows in memory (using state as key)
# In production, use Redis or database
oauth_flows = {}

# Enable CORS for frontend with cookies
# Production only - Vercel frontend URL
FRONTEND_URL = os.getenv('FRONTEND_URL', 'https://studyai-gamma.vercel.app')
CORS_ORIGINS = [FRONTEND_URL]

# Add additional Vercel URLs from environment if provided
VERCEL_URL = os.getenv('VERCEL_URL')
if VERCEL_URL and f"https://{VERCEL_URL}" not in CORS_ORIGINS:
    CORS_ORIGINS.append(f"https://{VERCEL_URL}")

print(f"[CORS] Allowed origins: {CORS_ORIGINS}")

CORS(app, 
     supports_credentials=True, 
     resources={r"*": {
         "origins": CORS_ORIGINS,
         "methods": ["GET", "POST", "OPTIONS"],
         "allow_headers": ["Content-Type"],
         "expose_headers": ["Content-Type"]
     }},
     max_age=3600
)

# Use server-side session to store data (avoids huge cookies)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
# Production HTTPS only
app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS required
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'None'  # Cross-site cookies required
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour
print(f"[Session] SECURE=True, SAMESITE=None (Production HTTPS)")
Session(app)

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')

# Production only - use Railway public domain
RAILWAY_PUBLIC_DOMAIN = os.getenv('RAILWAY_PUBLIC_DOMAIN')
if not RAILWAY_PUBLIC_DOMAIN:
    raise RuntimeError("RAILWAY_PUBLIC_DOMAIN environment variable is required for production")

BACKEND_URL = f"https://{RAILWAY_PUBLIC_DOMAIN}"
GOOGLE_REDIRECT_URI = f"{BACKEND_URL}/auth/google/callback"

print(f"[Init] BACKEND_URL: {BACKEND_URL}")
print(f"[Init] FRONTEND_URL: {FRONTEND_URL}")
print(f"[Init] GOOGLE_REDIRECT_URI: {GOOGLE_REDIRECT_URI}")

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

@app.route('/me')
def me():
    user = session.get('user')
    if not user:
        return jsonify({"authenticated": False}), 401
    return jsonify({"authenticated": True, "user": user})

@app.route('/auth/google')
def google_auth():
    print("[DEBUG] /auth/google route called")
    print(f"[DEBUG] GOOGLE_CLIENT_ID: {GOOGLE_CLIENT_ID}")
    print(f"[DEBUG] Using GOOGLE_REDIRECT_URI: {GOOGLE_REDIRECT_URI}")
    
    # Production only - use Railway public domain
    flow = google_auth_oauthlib.flow.Flow.from_client_config({
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [GOOGLE_REDIRECT_URI]
        }
    }, scopes=SCOPES)

    flow.redirect_uri = GOOGLE_REDIRECT_URI
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    
    # Store the flow object in memory using state as key
    oauth_flows[state] = flow
    print(f"[DEBUG] State generated: {state}")
    print(f"[DEBUG] Flow stored in oauth_flows")
    print(f"[DEBUG] Authorization URL: {authorization_url[:100]}...")
    return redirect(authorization_url)

@app.route('/auth/google/callback')
def google_callback():
    state = request.args.get('state')
    code = request.args.get('code')
    
    print(f"[DEBUG] Callback received")
    print(f"[DEBUG] Received state: {state}")
    print(f"[DEBUG] Received code: {code[:50] if code else 'None'}...")
    print(f"[DEBUG] Stored flows: {list(oauth_flows.keys())}")
    
    if not state or state not in oauth_flows:
        print(f"[ERROR] State not found in oauth_flows!")
        return jsonify({"error": "Invalid state"}), 400
    
    # Get the flow we stored
    flow = oauth_flows.pop(state)  # Remove it from memory after use
    print(f"[DEBUG] Flow retrieved from oauth_flows")
    
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

    # Store user info in session
    session['user'] = user_info
    session.modified = True
    print(f"[DEBUG] User stored in session")

    # Redirect to Vercel frontend
    frontend_url = f'{FRONTEND_URL}/?dashboard=1'
    print(f"[DEBUG] Redirecting to: {frontend_url}")
    response = redirect(frontend_url)
    return response

@app.route('/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})

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