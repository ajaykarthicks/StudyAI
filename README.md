---
title: Smart Study Hub
emoji: 📚
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
app_port: 7860
---

# AI-Powered Smart Study Hub

This is a full-stack web application that allows users to upload PDFs and interact with them using various AI-powered tools, including a chatbot, summarizer, quiz generator, and flashcard generator.

## Features

- **Google Authentication:** Securely sign in with your Google account.
- **PDF Chatbot:** Ask questions about your uploaded PDF and get answers from the content.
- **PDF Summarizer:** Generate concise summaries of your PDF documents.
- **Quiz Generator:** Create multiple-choice quizzes based on the PDF content.
- **Flashcard Generator:** Automatically create flashcards from key points in the PDF.

## Technology Stack

- **Frontend:** HTML, CSS, JavaScript
- **Backend:** Python (Flask)
- **AI Integration:** Groq API (for LLM-powered features)

## Prerequisites

Before you begin, ensure you have the following installed:

- [Python 3.8+](https://www.python.org/downloads/)
- [Node.js](https://nodejs.org/) (for a simple HTTP server to serve the frontend)
- A Google account for OAuth setup.
- A Groq API key.

## Setup and Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd smart-study-hub
```

### 2. Backend Setup

a. **Navigate to the `backend` directory:**
   ```bash
   cd backend
   ```

b. **Create and activate a virtual environment:**
   ```bash
   # For Windows
   python -m venv venv
   venv\Scripts\activate

   # For macOS/Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

c. **Install the required Python packages:**
   ```bash
   pip install -r requirements.txt
   ```

d. **Create a `.env` file** in the `backend` directory and add the following environment variables. You will need to obtain these credentials from the Google Cloud Console and Groq.

   ```env
   FLASK_SECRET_KEY='your_super_secret_key_here'
   GOOGLE_CLIENT_ID='your_google_client_id.apps.googleusercontent.com'
   GOOGLE_CLIENT_SECRET='your_google_client_secret'
   GOOGLE_REDIRECT_URI='http://localhost:5000/auth/google/callback'
   GROQ_API_KEY='your_groq_api_key'
   GROQ_MODEL='llama3-8b-8192' # Or any other model you prefer
   ```

### 3. Frontend Setup

The frontend is composed of static files (HTML, CSS, JS) and can be served using any simple HTTP server. We'll use the `http-server` package from npm.

a. **Install `http-server` globally:**
   ```bash
   npm install -g http-server
   ```

## Running the Application

You will need to run both the backend and frontend servers simultaneously in two separate terminals.

### 1. Start the Backend Server

- Make sure you are in the `backend` directory with your virtual environment activated.
- Run the Flask application:
  ```bash
  python app.py
  ```
- The backend server will start on `http://localhost:5000`.

### 2. Start the Frontend Server

- Open a new terminal and navigate to the `frontend` directory.
- Run the HTTP server:
  ```bash
  http-server -p 3000 --cors
  ```
- The frontend will be available at `http://localhost:3000`.

### 3. Access the Application

- Open your web browser and navigate to `http://localhost:3000`.
- You should see the landing page. Click the "Sign in with Google" button to authenticate.
- After signing in, you will be redirected to the dashboard where you can use the AI tools.

---
