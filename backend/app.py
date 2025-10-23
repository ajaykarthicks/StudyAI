import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  # Allow HTTP for local dev

from flask import Flask, request, jsonify, session, redirect
from flask_cors import CORS
from flask_session import Session
from dotenv import load_dotenv
import google_auth_oauthlib.flow
from groq import Groq
import PyPDF2
import requests

load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# Enable CORS for frontend with cookies
CORS(app, 
     supports_credentials=True, 
     resources={r"*": {
         "origins": ["http://localhost:3000", "http://127.0.0.1:3000"],
         "methods": ["GET", "POST", "OPTIONS"],
         "allow_headers": ["Content-Type"]
     }},
     expose_headers=["Content-Type"],
     max_age=3600
)

# Use server-side session to store PDF text (avoids huge cookies)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
Session(app)

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:5000/auth/google/callback')

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
    print(f"[DEBUG] GOOGLE_CLIENT_SECRET: {GOOGLE_CLIENT_SECRET[:20]}...")  # type: ignore
    print(f"[DEBUG] GOOGLE_REDIRECT_URI: {GOOGLE_REDIRECT_URI}")
    
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
    
    print(f"[DEBUG] Authorization URL: {authorization_url[:100]}...")
    session['state'] = state
    return redirect(authorization_url)

@app.route('/auth/google/callback')
def google_callback():
    state = session.get('state')

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
    authorization_response = request.url
    flow.fetch_token(authorization_response=authorization_response)

    credentials = flow.credentials

    # Get user info
    user_info = requests.get(
        'https://openidconnect.googleapis.com/v1/userinfo',
        headers={'Authorization': f'Bearer {credentials.token}'}
    ).json()

    session['user'] = user_info

    # Redirect to frontend dashboard (use query param for simple static hosting)
    # The session cookie will be set automatically during the redirect
    response = redirect('http://localhost:3000/?dashboard=1')
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