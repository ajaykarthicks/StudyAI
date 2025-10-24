const API_BASE_URL = 'https://studyai-production.up.railway.app';

// ============================================
// STATE MANAGEMENT
// ============================================

let appState = {
  isAuthenticated: false,
  user: null,
  chatHistory: [],
  pdfsList: [], // Array of {name, text, base64}
  selectedPdfIndex: 0, // Index of currently selected PDF
  
  // Convenience getters
  get currentFileName() {
    return this.pdfsList.length > 0 ? this.pdfsList[this.selectedPdfIndex].name : '';
  },
  get pdfText() {
    return this.pdfsList.length > 0 ? this.pdfsList[this.selectedPdfIndex].text : '';
  },
  get pdfBase64() {
    return this.pdfsList.length > 0 ? this.pdfsList[this.selectedPdfIndex].base64 : '';
  }
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
    console.log('OAuth callback - checking auth for upload page...');
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
      showPage('upload-page');  // Show upload page after login, not dashboard
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
          showPage('upload-page');  // Show upload page after login
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
        showPage('upload-page');  // Show upload page after login
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
    // Update PDF count display when showing dashboard
    setTimeout(() => {
      updatePdfCountDisplay();
    }, 100);
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
    const fileCount = fileInput.files.length;
    const filesText = fileCount === 1 ? '1 file' : `${fileCount} files`;
    fileLabel.textContent = filesText + ' selected';
    uploadBtn.disabled = false;
  } else {
    fileLabel.textContent = 'Click to upload or drag and drop';
    uploadBtn.disabled = true;
  }
}

async function handleMainUpload() {
  const fileInput = document.getElementById('main-pdf-file');
  if (fileInput.files.length === 0) {
    alert('Please select PDF files first.');
    return;
  }

  const files = Array.from(fileInput.files);
  console.log('🔼 Starting upload of', files.length, 'PDF(s)');
  
  let successCount = 0;
  let errorCount = 0;

  for (const file of files) {
    console.log('📤 Uploading:', file.name, 'Size:', file.size);
    
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
      
      if (!response.ok) throw new Error(data.error || 'Upload failed');
      
      // Add PDF to appState.pdfsList
      appState.pdfsList.push({
        name: file.name,
        text: data.pdf_text,
        base64: data.pdf_base64
      });
      
      // Auto-select the first PDF
      if (appState.pdfsList.length === 1) {
        appState.selectedPdfIndex = 0;
      }
      
      console.log('✅ PDF added to list:', {
        fileName: file.name,
        textLength: data.pdf_text.length,
        totalPdfs: appState.pdfsList.length
      });
      
      successCount++;
    } catch (error) {
      console.error('❌ Upload error for', file.name, ':', error);
      errorCount++;
    }
  }
  
  // Store in localStorage as backup
  localStorage.setItem('pdfs_backup', JSON.stringify(appState.pdfsList));
  localStorage.setItem('selectedPdfIndex_backup', appState.selectedPdfIndex);
  
  // Update UI
  updatePdfCountDisplay();
  
  if (errorCount > 0) {
    alert(`Uploaded ${successCount} file(s) successfully. ${errorCount} file(s) failed.`);
  } else {
    alert(`Uploaded ${successCount} PDF(s) successfully!`);
  }
  
  if (successCount > 0) {
    showPage('dashboard');
    selectTool('chatbot', document.querySelector('.tool-menu-item'));
  }
}

// ============================================
// PDF MANAGEMENT
// ============================================

function restorePdfsFromStorage() {
  try {
    const pdfsBackup = localStorage.getItem('pdfs_backup');
    if (pdfsBackup) {
      appState.pdfsList = JSON.parse(pdfsBackup);
      const selectedIndex = localStorage.getItem('selectedPdfIndex_backup');
      if (selectedIndex !== null) {
        appState.selectedPdfIndex = parseInt(selectedIndex);
      }
      console.log('✅ Restored PDFs from localStorage:', appState.pdfsList.length, 'PDFs');
      updatePdfCountDisplay();
      return true;
    }
  } catch (e) {
    console.error('Failed to restore PDFs:', e);
  }
  return false;
}

function updatePdfCountDisplay() {
  const countDisplay = document.getElementById('pdf-count-display');
  if (!countDisplay) return;
  
  if (appState.pdfsList.length === 0) {
    countDisplay.textContent = 'Upload PDF to get started';
  } else if (appState.pdfsList.length === 1) {
    countDisplay.textContent = '1 PDF uploaded';
  } else {
    countDisplay.textContent = `${appState.pdfsList.length} PDFs uploaded`;
  }
  
  // Update dropdown menu
  updatePdfDropdown();
}

function updatePdfDropdown() {
  const dropdownList = document.getElementById('pdf-list-dropdown');
  if (!dropdownList) return;
  
  dropdownList.innerHTML = '';
  
  if (appState.pdfsList.length === 0) {
    return;
  }
  
  appState.pdfsList.forEach((pdf, index) => {
    const pdfItem = document.createElement('div');
    pdfItem.className = 'dropdown-pdf-item';
    if (index === appState.selectedPdfIndex) {
      pdfItem.classList.add('selected');
    }
    
    pdfItem.innerHTML = `
      <div class="dropdown-pdf-content" onclick="selectPdf(${index}); closePdfDropdown();">
        <i class="fas fa-file-pdf"></i>
        <div class="dropdown-pdf-info">
          <div class="dropdown-pdf-name">${pdf.name}</div>
          <div class="dropdown-pdf-size">${(pdf.text.length / 1024).toFixed(1)} KB</div>
        </div>
        ${index === appState.selectedPdfIndex ? '<i class="fas fa-check" style="color: var(--success);"></i>' : ''}
      </div>
      <button class="dropdown-pdf-delete" onclick="deletePdf(${index}, event); updatePdfDropdown();">
        <i class="fas fa-trash-alt"></i>
      </button>
    `;
    
    dropdownList.appendChild(pdfItem);
  });
}

function togglePdfDropdown() {
  const menu = document.getElementById('pdf-dropdown-menu');
  menu.classList.toggle('active');
}

function closePdfDropdown() {
  const menu = document.getElementById('pdf-dropdown-menu');
  menu.classList.remove('active');
}

// Close dropdown when clicking outside
document.addEventListener('click', (e) => {
  const dropdown = document.querySelector('.dropdown');
  if (dropdown && !dropdown.contains(e.target)) {
    closePdfDropdown();
  }
});

function updatePdfList() {
  // Updated to use new dropdown system
  updatePdfCountDisplay();
}

function selectPdf(index) {
  if (index >= 0 && index < appState.pdfsList.length) {
    appState.selectedPdfIndex = index;
    console.log('📌 Selected PDF:', appState.currentFileName);
    
    // Update localStorage backup
    localStorage.setItem('selectedPdfIndex_backup', appState.selectedPdfIndex);
    
    // Update UI
    updatePdfCountDisplay();
  }
}

function deletePdf(index, event) {
  if (event) {
    event.stopPropagation();
  }
  
  if (appState.pdfsList.length === 1) {
    alert('You must keep at least one PDF. Upload more before deleting.');
    return;
  }
  
  const pdfName = appState.pdfsList[index].name;
  if (confirm(`Delete "${pdfName}"?`)) {
    appState.pdfsList.splice(index, 1);
    
    // Adjust selected index if needed
    if (appState.selectedPdfIndex >= appState.pdfsList.length) {
      appState.selectedPdfIndex = appState.pdfsList.length - 1;
    }
    
    // Update localStorage backup
    localStorage.setItem('pdfs_backup', JSON.stringify(appState.pdfsList));
    localStorage.setItem('selectedPdfIndex_backup', appState.selectedPdfIndex);
    
    console.log('🗑️ Deleted PDF:', pdfName);
    updatePdfCountDisplay();
  }
}

function addMorePdfs() {
  // Clear the file input and trigger it again for adding more PDFs
  const fileInput = document.getElementById('main-pdf-file');
  fileInput.value = ''; // Reset
  fileInput.click();
  closePdfDropdown();
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
  
  // Update navbar header
  updateNavbarHeader(toolName);
}

// Update navbar with current tool info
function updateNavbarHeader(toolName) {
  const navbarCenter = document.getElementById('navbar-center');
  const toolInfo = {
    chatbot: {
      icon: 'fas fa-comment-dots',
      title: 'Chat with PDF',
      description: 'Ask any question about your PDF and get instant answers'
    },
    summarizer: {
      icon: 'fas fa-file-alt',
      title: 'Summarize',
      description: 'Get a concise summary of the entire document'
    },
    quiz: {
      icon: 'fas fa-question-circle',
      title: 'Quiz Generator',
      description: 'Create multiple-choice practice questions'
    },
    flashcards: {
      icon: 'fas fa-layer-group',
      title: 'Flashcards',
      description: 'Create interactive flashcards for quick revision'
    }
  };
  
  const tool = toolInfo[toolName];
  if (tool) {
    navbarCenter.innerHTML = `
      <div class="navbar-tool-info">
        <h2><i class="${tool.icon}"></i> ${tool.title}</h2>
        <p>${tool.description}</p>
      </div>
    `;
  }
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

let quizState = {
  questions: [],
  userAnswers: {},
  showAnswers: {}
};

async function handleQuiz() {
  const num_questions = parseInt(document.getElementById('quiz-count').value);
  const resultBox = document.getElementById('quiz-result');
  resultBox.innerHTML = `<div style="text-align: center; padding: 20px; color: var(--text-secondary);">
    <i class="fas fa-spinner fa-spin"></i> Generating ${num_questions} quiz questions...
  </div>`;

  // Check if PDF is loaded
  if (!appState.pdfText && !appState.pdfBase64) {
    resultBox.textContent = 'Error: No PDF uploaded';
    return;
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
    
    if (data.quiz && Array.isArray(data.quiz)) {
      quizState.questions = data.quiz;
      quizState.userAnswers = {};
      quizState.showAnswers = {};
      renderInteractiveQuiz(resultBox);
    } else {
      resultBox.textContent = data.quiz_text || 'No quiz generated';
    }
  } catch (error) {
    resultBox.innerHTML = `<div style="color: var(--error); padding: 20px;">Error: ${error.message}</div>`;
  }
}

function renderInteractiveQuiz(container) {
  let html = '<div class="quiz-container">';
  
  html += '<div class="quiz-header">';
  html += `<h3>Quiz: ${quizState.questions.length} Questions</h3>`;
  html += '<div class="quiz-actions">';
  html += '<button class="button-secondary" onclick="showAllAnswers()"><i class="fas fa-eye"></i> Show All Answers</button>';
  html += '</div>';
  html += '</div>';
  
  quizState.questions.forEach((q, i) => {
    const isAnswered = quizState.userAnswers[i] !== undefined;
    const selectedAnswer = quizState.userAnswers[i];
    const isCorrect = selectedAnswer === q.correct_answer_index;
    const showAnswer = quizState.showAnswers[i];
    
    html += `<div class="quiz-question">`;
    html += `<div class="quiz-question-header">`;
    html += `<span class="quiz-q-number">Question ${i + 1}</span>`;
    if (isAnswered) {
      html += `<span class="quiz-status ${isCorrect ? 'correct' : 'incorrect'}">`;
      html += isCorrect ? '<i class="fas fa-check"></i> Correct' : '<i class="fas fa-times"></i> Incorrect';
      html += '</span>';
    }
    html += `</div>`;
    html += `<p class="quiz-question-text">${q.question}</p>`;
    
    html += `<div class="quiz-options">`;
    q.options.forEach((opt, j) => {
      const isSelected = selectedAnswer === j;
      const isCorrectOption = j === q.correct_answer_index;
      
      let optionClass = 'quiz-option';
      if (isAnswered) {
        if (isCorrectOption) optionClass += ' correct';
        if (isSelected && !isCorrect) optionClass += ' incorrect';
      }
      if (isSelected && !isAnswered) optionClass += ' selected';
      
      html += `<button class="${optionClass}" onclick="selectQuizAnswer(${i}, ${j})">`;
      html += `<span class="option-letter">${String.fromCharCode(65 + j)}</span>`;
      html += `<span class="option-text">${opt}</span>`;
      html += `</button>`;
    });
    html += `</div>`;
    
    if (isAnswered) {
      html += `<div class="quiz-answer-section">`;
      if (!showAnswer) {
        html += `<button class="button-tertiary" onclick="toggleAnswerDisplay(${i})">`;
        html += `<i class="fas fa-lightbulb"></i> Show Answer`;
        html += `</button>`;
      } else {
        html += `<div class="correct-answer">`;
        html += `<strong>✓ Correct Answer: ${q.options[q.correct_answer_index]}</strong>`;
        if (q.explanation) {
          html += `<p>${q.explanation}</p>`;
        }
        html += `</div>`;
        html += `<button class="button-tertiary" onclick="toggleAnswerDisplay(${i})">`;
        html += `<i class="fas fa-times"></i> Hide Answer`;
        html += `</button>`;
      }
      html += `</div>`;
    }
    
    html += `</div>`;
  });
  
  html += '</div>';
  container.innerHTML = html;
}

function selectQuizAnswer(questionIndex, answerIndex) {
  quizState.userAnswers[questionIndex] = answerIndex;
  quizState.showAnswers[questionIndex] = false;
  const resultBox = document.getElementById('quiz-result');
  renderInteractiveQuiz(resultBox);
}

function toggleAnswerDisplay(questionIndex) {
  quizState.showAnswers[questionIndex] = !quizState.showAnswers[questionIndex];
  const resultBox = document.getElementById('quiz-result');
  renderInteractiveQuiz(resultBox);
}

function showAllAnswers() {
  quizState.questions.forEach((q, i) => {
    quizState.showAnswers[i] = true;
  });
  const resultBox = document.getElementById('quiz-result');
  renderInteractiveQuiz(resultBox);
}

// ============================================
// FLASHCARDS
// ============================================

let flashcardState = {
  cards: [],
  currentCardIndex: 0,
  flipped: {}
};

async function handleFlashcards() {
  const num_cards = parseInt(document.getElementById('flashcards-count').value);
  const resultBox = document.getElementById('flashcards-result');
  resultBox.innerHTML = `<div style="text-align: center; padding: 20px; color: var(--text-secondary);">
    <i class="fas fa-spinner fa-spin"></i> Generating ${num_cards} flashcards...
  </div>`;

  // Check if PDF is loaded
  if (!appState.pdfText && !appState.pdfBase64) {
    resultBox.textContent = 'Error: No PDF uploaded';
    return;
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

    if (data.flashcards && Array.isArray(data.flashcards)) {
      flashcardState.cards = data.flashcards;
      flashcardState.currentCardIndex = 0;
      flashcardState.flipped = {};
      renderFlashcards(resultBox);
    } else {
      resultBox.textContent = data.flashcards_text || 'No flashcards generated';
    }
  } catch (error) {
    resultBox.innerHTML = `<div style="color: var(--error); padding: 20px;">Error: ${error.message}</div>`;
  }
}

function renderFlashcards(container) {
  const card = flashcardState.cards[flashcardState.currentCardIndex];
  const isFlipped = flashcardState.flipped[flashcardState.currentCardIndex] || false;
  
  let html = '';
  
  // Header with navigation and progress
  html += '<div class="flashcards-container">';
  html += '<div class="flashcards-header">';
  html += `<h3>Flashcards</h3>`;
  html += `<span class="flashcard-counter">Card ${flashcardState.currentCardIndex + 1} of ${flashcardState.cards.length}</span>`;
  html += '</div>';
  
  // Advanced 3D Card Template
  html += '<div class="card-scene">';
  html += `<div id="card" class="card ${isFlipped ? 'card--flipped' : ''}" onclick="toggleFlashcardFlip()">`;
  
  // Card Backing (Back Side - Answer)
  html += '<div class="card-face card-backing">';
  html += '<div class="grain-overlay"></div>';
  html += '<div class="top-banner"></div>';
  html += '<div class="back-main">';
  html += '<h1 style="margin: 0 0 var(--spacing-lg) 0; font-size: 1.2rem;">Answer</h1>';
  html += `<div class="card-content" style="flex: 1; display: flex; align-items: center; justify-content: center; text-align: center;">${escapeHtml(card.back)}</div>`;
  html += '</div>';
  html += '</div>';
  
  // Card Front (Front Side - Question)
  html += '<div class="card-face card-front">';
  html += '<h1>Question</h1>';
  html += `<div class="card-content">${escapeHtml(card.front)}</div>`;
  html += '<div class="card-hint">Click card to reveal answer</div>';
  html += '<div class="grain-overlay"></div>';
  html += '</div>';
  
  html += '</div>'; // end card
  html += '</div>'; // end card-scene
  
  // Navigation Controls
  html += '<div class="flashcards-top-controls">';
  
  if (flashcardState.currentCardIndex > 0) {
    html += '<button class="arrow-button prev-arrow" onclick="previousFlashcard()" title="Previous card"><i class="fas fa-chevron-left"></i></button>';
  } else {
    html += '<button class="arrow-button prev-arrow" disabled style="opacity: 0.3;"><i class="fas fa-chevron-left"></i></button>';
  }
  
  html += `<span class="flip-hint">Card ${flashcardState.currentCardIndex + 1}/${flashcardState.cards.length}</span>`;
  
  if (flashcardState.currentCardIndex < flashcardState.cards.length - 1) {
    html += '<button class="arrow-button next-arrow" onclick="nextFlashcard()" title="Next card"><i class="fas fa-chevron-right"></i></button>';
  } else {
    html += '<button class="arrow-button next-arrow" disabled style="opacity: 0.3;"><i class="fas fa-chevron-right"></i></button>';
  }
  
  html += '</div>';
  
  // Progress Bar
  const progress = ((flashcardState.currentCardIndex + 1) / flashcardState.cards.length) * 100;
  html += `<div class="progress-bar"><div class="progress-fill" style="width: ${progress}%"></div></div>`;
  
  html += '</div>'; // end flashcards-container
  
  container.innerHTML = html;
  
  // Attach event listener to card after rendering
  setTimeout(() => {
    const cardElement = document.getElementById('card');
    if (cardElement) {
      cardElement.onclick = toggleFlashcardFlip;
    }
  }, 0);
}

function flipCard() {
  flashcardState.flipped[flashcardState.currentCardIndex] = !flashcardState.flipped[flashcardState.currentCardIndex];
  const resultBox = document.getElementById('flashcards-result');
  renderFlashcards(resultBox);
}

function toggleFlashcardFlip() {
  flipCard();
}

function nextFlashcard() {
  if (flashcardState.currentCardIndex < flashcardState.cards.length - 1) {
    flashcardState.currentCardIndex++;
    flashcardState.flipped[flashcardState.currentCardIndex] = false;
    const resultBox = document.getElementById('flashcards-result');
    renderFlashcards(resultBox);
  }
}

function previousFlashcard() {
  if (flashcardState.currentCardIndex > 0) {
    flashcardState.currentCardIndex--;
    flashcardState.flipped[flashcardState.currentCardIndex] = false;
    const resultBox = document.getElementById('flashcards-result');
    renderFlashcards(resultBox);
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function previousFlashcard() {
  if (flashcardState.currentCardIndex > 0) {
    const wrapper = document.querySelector('.flip-card-wrapper-3d');
    if (wrapper) wrapper.classList.add('slide-exit-right');
    
    setTimeout(() => {
      flashcardState.currentCardIndex--;
      flashcardState.flipped[flashcardState.currentCardIndex] = false;
      const resultBox = document.getElementById('flashcards-result');
      renderFlashcards(resultBox);
      
      const newWrapper = document.querySelector('.flip-card-wrapper-3d');
      if (newWrapper) {
        newWrapper.classList.add('slide-enter-left');
        setTimeout(() => newWrapper.classList.remove('slide-enter-left'), 500);
      }
    }, 300);
  }
}
