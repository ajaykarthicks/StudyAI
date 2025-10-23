const API_BASE_URL = window.location.hostname === 'localhost' 
  ? 'http://localhost:5000' 
  : 'https://studyai-production.up.railway.app';

// ============================================
// STATE MANAGEMENT
// ============================================

let appState = {
  currentFileName: '',
  isAuthenticated: false,
  user: null,
  chatHistory: []
};

// ============================================
// INITIALIZATION
// ============================================

document.addEventListener('DOMContentLoaded', () => {
  console.log('App initialized');
  console.log('API_BASE_URL:', API_BASE_URL);
  
  const urlParams = new URLSearchParams(window.location.search);
  
  // If redirected from OAuth callback, go straight to dashboard after auth check
  if (urlParams.has('dashboard')) {
    window.history.replaceState({}, document.title, "/");
    // Add a slight delay to ensure session is properly set
    setTimeout(() => {
      checkAuthAndShowDashboard();
    }, 500);
  } else {
    checkAuth();
  }
});

// ============================================
// AUTHENTICATION
// ============================================

async function checkAuth() {
  try {
    const response = await fetch(`${API_BASE_URL}/me`, { 
      credentials: 'include',
      headers: {
        'Accept': 'application/json'
      }
    });
    if (response.ok) {
      const data = await response.json();
      appState.isAuthenticated = true;
      appState.user = data.user;
      updateUserInfo();
      showPage('upload-page');
    } else {
      appState.isAuthenticated = false;
      showPage('landing-page');
    }
  } catch (error) {
    console.error('Auth check failed:', error);
    appState.isAuthenticated = false;
    showPage('landing-page');
  }
}

async function checkAuthAndShowDashboard() {
  try {
    const response = await fetch(`${API_BASE_URL}/me`, { 
      credentials: 'include',
      headers: {
        'Accept': 'application/json'
      }
    });
    if (response.ok) {
      const data = await response.json();
      appState.isAuthenticated = true;
      appState.user = data.user;
      updateUserInfo();
      // Skip upload page and go directly to dashboard after OAuth callback
      showPage('dashboard');
    } else {
      appState.isAuthenticated = false;
      showPage('landing-page');
    }
  } catch (error) {
    console.error('Auth check failed:', error);
    appState.isAuthenticated = false;
    showPage('landing-page');
  }
}

function signInWithGoogle() {
  console.log('Google sign-in button clicked');
  console.log('Redirecting to:', `${API_BASE_URL}/auth/google`);
  window.location.href = `${API_BASE_URL}/auth/google`;
}

async function signOut() {
  try {
    await fetch(`${API_BASE_URL}/auth/logout`, { method: 'POST', credentials: 'include' });
    appState.isAuthenticated = false;
    appState.user = null;
    appState.chatHistory = [];
    showPage('landing-page');
  } catch (error) {
    console.error('Logout failed:', error);
  }
}

function updateUserInfo() {
  const userInfoElements = document.querySelectorAll('#user-info-header');
  if (appState.user) {
    userInfoElements.forEach(el => {
      el.innerHTML = `
        <img src="${appState.user.picture}" alt="${appState.user.name}" style="width: 32px; height: 32px; border-radius: 50%; margin-right: 8px;">
        <span>${appState.user.given_name}</span>
      `;
    });
  }
}

// ============================================
// PAGE NAVIGATION
// ============================================

function showPage(pageId) {
  document.querySelectorAll('.page').forEach(page => {
    page.classList.remove('active');
  });
  document.getElementById(pageId).classList.add('active');
  
  // Reset chat on page change
  if (pageId === 'dashboard') {
    appState.chatHistory = [];
    document.getElementById('chat-history').innerHTML = '';
  }
}

function backToUpload() {
  appState.chatHistory = [];
  document.getElementById('chat-history').innerHTML = '';
  document.getElementById('main-pdf-file').value = '';
  document.getElementById('file-label-text').textContent = 'Click to upload or drag and drop';
  document.getElementById('upload-btn').disabled = true;
  showPage('upload-page');
}

// ============================================
// FILE UPLOAD
// ============================================

function handleFileSelected() {
  const fileInput = document.getElementById('main-pdf-file');
  const uploadBtn = document.getElementById('upload-btn');
  const fileLabel = document.getElementById('file-label-text');
  
  if (fileInput.files.length > 0) {
    const fileName = fileInput.files[0].name;
    fileLabel.textContent = fileName;
    uploadBtn.disabled = false;
    appState.currentFileName = fileName;
  } else {
    fileLabel.textContent = 'Click to upload or drag and drop';
    uploadBtn.disabled = true;
  }
}

async function handleMainUpload() {
  const fileInput = document.getElementById('main-pdf-file');
  if (fileInput.files.length === 0) {
    alert('Please select a PDF file first.');
    return;
  }

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);

  try {
    const response = await fetch(`${API_BASE_URL}/api/upload-pdf`, {
      method: 'POST',
      body: formData,
      credentials: 'include',
    });
    
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Upload failed');
    
    appState.currentFileName = fileInput.files[0].name;
    document.getElementById('current-file-name').textContent = appState.currentFileName;
    showPage('dashboard');
    selectTool('chatbot', document.querySelector('.tool-menu-item'));
  } catch (error) {
    console.error('Upload error:', error);
    alert(`Error: ${error.message}`);
  }
}

// ============================================
// TOOL SELECTION
// ============================================

function selectTool(toolName, element) {
  // Update active menu item
  document.querySelectorAll('.tool-menu-item').forEach(item => {
    item.classList.remove('active');
  });
  element.classList.add('active');
  
  // Update active content
  document.querySelectorAll('.tool-content').forEach(content => {
    content.classList.remove('active');
  });
  document.getElementById(`${toolName}-content`).classList.add('active');
}

// ============================================
// CHAT INTERFACE
// ============================================

async function handleChat() {
  const question = document.getElementById('chatbot-question').value;
  if (!question) {
    alert('Please enter a question.');
    return;
  }

  // Add user message to chat
  addChatMessage('user', question);
  document.getElementById('chatbot-question').value = '';

  try {
    const response = await fetch(`${API_BASE_URL}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
      credentials: 'include',
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Failed to get answer');
    
    // Add assistant response to chat
    addChatMessage('assistant', data.answer);
  } catch (error) {
    addChatMessage('assistant', `Error: ${error.message}`);
  }
}

function addChatMessage(role, content) {
  const chatHistory = document.getElementById('chat-history');
  const messageDiv = document.createElement('div');
  messageDiv.className = `chat-message ${role}`;
  
  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble';
  bubble.textContent = content;
  
  messageDiv.appendChild(bubble);
  chatHistory.appendChild(messageDiv);
  
  // Auto-scroll to bottom
  chatHistory.scrollTop = chatHistory.scrollHeight;
  
  appState.chatHistory.push({ role, content });
}

// ============================================
// SUMMARIZER
// ============================================

async function handleSummarize() {
  const resultBox = document.getElementById('summarizer-result');
  resultBox.textContent = 'Generating summary...';

  try {
    const response = await fetch(`${API_BASE_URL}/api/summarize`, {
      method: 'POST',
      credentials: 'include',
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Failed to summarize');
    
    resultBox.textContent = data.summary;
  } catch (error) {
    resultBox.textContent = `Error: ${error.message}`;
  }
}

// ============================================
// QUIZ GENERATOR
// ============================================

async function handleQuiz() {
  const num_questions = parseInt(document.getElementById('quiz-count').value);
  const resultBox = document.getElementById('quiz-result');
  resultBox.textContent = `Generating ${num_questions} quiz questions...`;

  try {
    const response = await fetch(`${API_BASE_URL}/api/generate-quiz`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ num_questions }),
      credentials: 'include',
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Failed to generate quiz');
    
    let quizContent = '';
    if (data.quiz && Array.isArray(data.quiz)) {
      data.quiz.forEach((q, i) => {
        quizContent += `Q${i + 1}. ${q.question}\n\n`;
        q.options.forEach((opt, j) => {
          quizContent += `  ${String.fromCharCode(97 + j)}) ${opt}\n`;
        });
        quizContent += `\n✓ Answer: ${q.options[q.correct_answer_index]}\n\n`;
      });
    } else {
      quizContent = data.quiz_text || 'No quiz generated';
    }
    resultBox.textContent = quizContent;
  } catch (error) {
    resultBox.textContent = `Error: ${error.message}`;
  }
}

// ============================================
// FLASHCARDS
// ============================================

async function handleFlashcards() {
  const num_cards = parseInt(document.getElementById('flashcards-count').value);
  const resultBox = document.getElementById('flashcards-result');
  resultBox.textContent = `Generating ${num_cards} flashcards...`;

  try {
    const response = await fetch(`${API_BASE_URL}/api/generate-flashcards`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ num_cards }),
      credentials: 'include',
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Failed to generate flashcards');

    let flashcardContent = '';
    if (data.flashcards && Array.isArray(data.flashcards)) {
      data.flashcards.forEach((card, i) => {
        flashcardContent += `📇 Card ${i + 1}:\n`;
        flashcardContent += `   Front: ${card.front}\n`;
        flashcardContent += `   Back: ${card.back}\n\n`;
      });
    } else {
      flashcardContent = data.flashcards_text || 'No flashcards generated';
    }
    resultBox.textContent = flashcardContent;
  } catch (error) {
    resultBox.textContent = `Error: ${error.message}`;
  }
}
