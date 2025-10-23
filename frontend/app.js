const API_BASE_URL = 'https://studyai-production.up.railway.app';

// ============================================
// STATE MANAGEMENT
// ============================================

let appState = {
  currentFileName: '',
  isAuthenticated: false,
  user: null,
  chatHistory: [],
  pdfText: '', // Store PDF text client-side
  pdfBase64: '' // Store PDF as Base64 for requests
};

// ============================================
// INITIALIZATION
// ============================================

document.addEventListener('DOMContentLoaded', () => {
  console.log('App initialized');
  console.log('API_BASE_URL:', API_BASE_URL);
  console.log('Cookies:', document.cookie);
  
  const urlParams = new URLSearchParams(window.location.search);
  
  // If redirected from OAuth callback with auth data, store it
  if (urlParams.has('auth')) {
    console.log('OAuth callback with auth data detected');
    const authB64 = urlParams.get('auth');
    try {
      const authJson = atob(authB64);
      const userData = JSON.parse(authJson);
      console.log('Storing auth data from callback:', userData.email);
      
      // Store in localStorage for mobile compatibility
      localStorage.setItem('user_data_backup', authJson);
      
      // Also try to trigger /me to ensure cookie is set
      window.history.replaceState({}, document.title, "/");
      setTimeout(() => {
        checkAuthAndShowDashboard();
      }, 300);
    } catch (e) {
      console.error('Failed to decode auth data:', e);
      checkAuthAndShowDashboard();
    }
  } else if (urlParams.has('dashboard')) {
    // Legacy: if just dashboard flag without auth
    console.log('OAuth callback detected - checking auth for dashboard');
    window.history.replaceState({}, document.title, "/");
    setTimeout(() => {
      checkAuthAndShowDashboard();
    }, 300);
  } else {
    // Regular page load - check if already authenticated
    checkAuth();
  }
});

// ============================================
// AUTHENTICATION
// ============================================

async function checkAuth() {
  try {
    console.log('Checking authentication...');
    const response = await fetch(`${API_BASE_URL}/me`, { 
      credentials: 'include',
      method: 'GET'
    });
    
    if (response.ok) {
      const data = await response.json();
      console.log('User authenticated via /me:', data.user.email);
      appState.isAuthenticated = true;
      appState.user = data.user;
      updateUserInfo();
      showPage('upload-page');
    } else {
      // Fallback: check localStorage (for mobile)
      const backupData = localStorage.getItem('user_data_backup');
      if (backupData) {
        try {
          const user = JSON.parse(backupData);
          console.log('User authenticated via localStorage:', user.email);
          appState.isAuthenticated = true;
          appState.user = user;
          updateUserInfo();
          showPage('upload-page');
        } catch (e) {
          console.error('Failed to parse backup auth:', e);
          appState.isAuthenticated = false;
          showPage('landing-page');
        }
      } else {
        console.log('Not authenticated - showing login');
        appState.isAuthenticated = false;
        showPage('landing-page');
      }
    }
  } catch (error) {
    console.error('Auth check error:', error);
    
    // Fallback: check localStorage
    const backupData = localStorage.getItem('user_data_backup');
    if (backupData) {
      try {
        const user = JSON.parse(backupData);
        console.log('User authenticated via localStorage (after error):', user.email);
        appState.isAuthenticated = true;
        appState.user = user;
        updateUserInfo();
        showPage('upload-page');
      } catch (e) {
        appState.isAuthenticated = false;
        showPage('landing-page');
      }
    } else {
      appState.isAuthenticated = false;
      showPage('landing-page');
    }
  }
}

async function checkAuthAndShowDashboard() {
  try {
    console.log('OAuth callback - checking auth for dashboard...');
    const response = await fetch(`${API_BASE_URL}/me`, { 
      credentials: 'include',
      method: 'GET'
    });
    
    console.log('Dashboard auth response status:', response.status);
    
    if (response.ok) {
      const data = await response.json();
      console.log('Authentication successful via /me:', data.user.email);
      appState.isAuthenticated = true;
      appState.user = data.user;
      updateUserInfo();
      showPage('dashboard');
    } else {
      // Fallback: check localStorage (for mobile)
      const backupData = localStorage.getItem('user_data_backup');
      if (backupData) {
        try {
          const user = JSON.parse(backupData);
          console.log('Authentication successful via localStorage:', user.email);
          appState.isAuthenticated = true;
          appState.user = user;
          updateUserInfo();
          showPage('dashboard');
        } catch (e) {
          console.error('Failed to parse backup auth:', e);
          appState.isAuthenticated = false;
          showPage('landing-page');
        }
      } else {
        console.log('Authentication failed - showing login');
        appState.isAuthenticated = false;
        showPage('landing-page');
      }
    }
  } catch (error) {
    console.error('Dashboard auth error:', error);
    
    // Fallback: check localStorage
    const backupData = localStorage.getItem('user_data_backup');
    if (backupData) {
      try {
        const user = JSON.parse(backupData);
        console.log('Authentication successful via localStorage (after error):', user.email);
        appState.isAuthenticated = true;
        appState.user = user;
        updateUserInfo();
        showPage('dashboard');
      } catch (e) {
        appState.isAuthenticated = false;
        showPage('landing-page');
      }
    } else {
      appState.isAuthenticated = false;
      showPage('landing-page');
    }
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
    
    // Clear localStorage backup
    localStorage.removeItem('user_data_backup');
    
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

  const file = fileInput.files[0];
  console.log('🔼 Starting PDF upload:', file.name, 'Size:', file.size);
  
  const formData = new FormData();
  formData.append('file', file);

  try {
    const response = await fetch(`${API_BASE_URL}/api/upload-pdf`, {
      method: 'POST',
      body: formData,
      credentials: 'include',
    });
    
    console.log('📦 Upload response status:', response.status);
    const data = await response.json();
    console.log('📊 Upload response data:', {
      message: data.message,
      text_length: data.text_length,
      has_pdf_text: !!data.pdf_text,
      has_pdf_base64: !!data.pdf_base64
    });
    
    if (!response.ok) throw new Error(data.error || 'Upload failed');
    
    // Store PDF text in appState for later use
    appState.pdfText = data.pdf_text;
    appState.pdfBase64 = data.pdf_base64;
    appState.currentFileName = file.name;
    
    console.log('✅ PDF stored in appState:', {
      pdfText_length: appState.pdfText ? appState.pdfText.length : 0,
      currentFileName: appState.currentFileName
    });
    
    // Also store in localStorage as backup
    localStorage.setItem('pdf_text_backup', appState.pdfText);
    localStorage.setItem('pdf_filename_backup', file.name);
    
    document.getElementById('current-file-name').textContent = appState.currentFileName;
    showPage('dashboard');
    selectTool('chatbot', document.querySelector('.tool-menu-item'));
  } catch (error) {
    console.error('❌ Upload error:', error);
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

  // Check if PDF is loaded
  if (!appState.pdfText && !appState.pdfBase64) {
    const backup = localStorage.getItem('pdf_text_backup');
    if (backup) {
      appState.pdfText = backup;
    } else {
      addChatMessage('assistant', 'Error: No PDF uploaded');
      return;
    }
  }

  // Add user message to chat
  addChatMessage('user', question);
  document.getElementById('chatbot-question').value = '';

  try {
    const response = await fetch(`${API_BASE_URL}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, pdf_text: appState.pdfText }),
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

  // Check if PDF is loaded
  if (!appState.pdfText && !appState.pdfBase64) {
    const backup = localStorage.getItem('pdf_text_backup');
    if (backup) {
      appState.pdfText = backup;
      console.log('📄 Restored PDF from localStorage');
    } else {
      resultBox.textContent = 'Error: No PDF uploaded';
      console.error('❌ No PDF in appState or localStorage');
      return;
    }
  }

  console.log('📝 Summarize: Sending PDF of size', appState.pdfText.length);

  try {
    const response = await fetch(`${API_BASE_URL}/api/summarize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pdf_text: appState.pdfText }),
      credentials: 'include',
    });

    console.log('📦 Summarize response status:', response.status);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Failed to summarize');
    
    resultBox.textContent = data.summary;
    console.log('✅ Summary generated');
  } catch (error) {
    resultBox.textContent = `Error: ${error.message}`;
    console.error('❌ Summarize error:', error);
  }
}

// ============================================
// QUIZ GENERATOR
// ============================================

async function handleQuiz() {
  const num_questions = parseInt(document.getElementById('quiz-count').value);
  const resultBox = document.getElementById('quiz-result');
  resultBox.textContent = `Generating ${num_questions} quiz questions...`;

  // Check if PDF is loaded
  if (!appState.pdfText && !appState.pdfBase64) {
    const backup = localStorage.getItem('pdf_text_backup');
    if (backup) {
      appState.pdfText = backup;
    } else {
      resultBox.textContent = 'Error: No PDF uploaded';
      return;
    }
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/generate-quiz`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ num_questions, pdf_text: appState.pdfText }),
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

  // Check if PDF is loaded
  if (!appState.pdfText && !appState.pdfBase64) {
    const backup = localStorage.getItem('pdf_text_backup');
    if (backup) {
      appState.pdfText = backup;
    } else {
      resultBox.textContent = 'Error: No PDF uploaded';
      return;
    }
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/generate-flashcards`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ num_cards, pdf_text: appState.pdfText }),
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
