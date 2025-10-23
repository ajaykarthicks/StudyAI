# Debugging Auth Issues - Console Inspection Guide

## How to Check If Auth is Working

### 1. Open Browser Developer Tools
- **Desktop**: Press `F12` or `Ctrl+Shift+I` (Windows/Linux) or `Cmd+Option+I` (Mac)
- **Phone**: Use remote debugging (see phone testing section)

### 2. Check Console Logs (Console Tab)
After clicking "Continue with Google", you should see:

```
App initialized
API_BASE_URL: https://studyai-production.up.railway.app
Current cookies: [your cookies]
LocalStorage user: null  (before login)

-- After redirect from Google --

App initialized (again)
Checking auth and showing dashboard...
No cached user info, checking /me endpoint...
Dashboard auth check response status: 200
User authenticated for dashboard: {email: "...", ...}
User authenticated from cached info: {email: "...", ...}
```

### 3. Check Application Tab (Storage)

#### LocalStorage
- Path: `Application` → `Local Storage` → `https://studyai-gamma.vercel.app`
- Look for key: `study_hub_user`
- Value: JSON string with user info
- Should appear after successful login ✅

#### Cookies
- Path: `Application` → `Cookies` → `https://studyai-gamma.vercel.app`
- Look for cookie: `study_hub_user` (might not be here, depends on cookie handling)
- Also check: `https://studyai-production.up.railway.app` cookies

### 4. Check Network Tab (Network)

#### First Login Request
1. GET `/auth/google` → 302 redirect to Google
   - Response: Redirect headers
   - Check if `oauth_state` cookie is set ✅

2. Google OAuth flow (external redirect)
   - You'll see requests to `accounts.google.com` and `oauth2.googleapis.com`

3. GET `/auth/google/callback?state=...&code=...`
   - Status: 302 redirect
   - Response headers should include Set-Cookie headers for:
     - `study_hub_user` (Base64-encoded user info) ✅
   - Redirect to: `https://studyai-gamma.vercel.app/?dashboard=1` ✅

4. GET `/?dashboard=1`
   - Page reloads
   - Frontend checks localStorage/cookies
   - If found, shows dashboard immediately ✅

5. GET `/me`
   - Status: 200 (if cookies/session work)
   - Response: `{"authenticated": true, "user": {...}}`
   - Headers: `Set-Cookie` for session ✅

---

## Common Issues & Solutions

### Issue 1: "Invalid state" Error
**Symptoms**: After logging in, error shows "Invalid state"

**Check**:
- Go to `Network` tab
- Find `/auth/google/callback` request
- Look at cookies before and after request
- `oauth_state` cookie should be present

**Solution**:
- Clear all cookies and cache
- Try login again
- If persists, backend state verification is failing

### Issue 2: After Login, Back to Login Page
**Symptoms**: Redirect works, but frontend shows login page

**Check in Console**:
```
Dashboard auth check response status: 401  ← Problem here!
User not authenticated for dashboard, showing landing
```

**Debug Steps**:
1. Check if `study_hub_user` exists in Application → LocalStorage
   - If NO: Backend isn't setting cookie properly
   - If YES: Frontend isn't reading it

2. Check if `study_hub_user` cookie exists (check both domains)
   - Vercel domain (`studyai-gamma.vercel.app`)
   - Railway domain (`studyai-production.up.railway.app`)

3. Check `/me` endpoint response:
   - Go to Network tab
   - Look for `/me` request
   - Status 401 = session not set on backend
   - Status 200 = session works ✅

### Issue 3: No Cookies Visible
**Symptoms**: `study_hub_user` cookie not showing in Application tab

**Possible Causes**:
1. Cookie not being set by backend
   - Check Network → `/auth/google/callback` response headers
   - Look for `Set-Cookie: study_hub_user=...` ✅

2. Cookie was set but not sent
   - Check Network → any request to Railway
   - Look at Request Headers → Cookie
   - Should include `study_hub_user=...` ✅

3. CORS/SameSite issue blocking cookie
   - Check Console for warnings like:
   ```
   Cookie "study_hub_user" has SameSite policy but no Secure flag
   ```
   - Backend needs `secure=False` for HTTP

### Issue 4: Phone Login Not Working
**Symptoms**: Login works on desktop but not on phone

**Check**:
1. Phone network is NOT localhost
   - Verify API_BASE_URL in `frontend/app.js` is production URL only ✅

2. Clear phone cookies/cache
   - Android: Settings → Apps → Browser → Clear Cache
   - iPhone: Settings → Safari → Clear History and Website Data

3. Check phone console (if available)
   - Remote debugging: https://developer.chrome.com/docs/devtools/remote-debugging/

4. Check if CORS allows all origins
   - Backend should have: `"origins": "*"` ✅
   - Check backend logs for CORS errors

---

## Expected Console Output - Successful Flow

### Before Login
```
App initialized
API_BASE_URL: https://studyai-production.up.railway.app
Current cookies: [may be empty]
LocalStorage user: null

Checking authentication status...
No cached user info, checking /me endpoint...
Auth check response status: 401
User not authenticated
```

### After Clicking "Continue with Google"
```
Google sign-in button clicked
Redirecting to: https://studyai-production.up.railway.app/auth/google
```

### After Google OAuth Completes (Backend Logs)
```
[DEBUG] /auth/google route called
[DEBUG] Generated state: [random-string]
[DEBUG] State cookie set with value: [random-string]

-- User logs in to Google --

[DEBUG] Callback received
[DEBUG] Received state: [random-string]
[DEBUG] Cookie state: [random-string]
[DEBUG] State verified successfully
[DEBUG] Token fetched successfully
[DEBUG] User info retrieved: user@gmail.com
[DEBUG] User stored in session
[DEBUG] Redirecting to: https://studyai-gamma.vercel.app/?dashboard=1
```

### After Redirect Back to Frontend
```
App initialized
API_BASE_URL: https://studyai-production.up.railway.app
Current cookies: study_hub_user=[base64-encoded]
LocalStorage user: null

Checking auth and showing dashboard...
No cached user info, checking /me endpoint...
Dashboard auth check response status: 200
User authenticated for dashboard: {email: "user@gmail.com", name: "User Name", ...}
User authenticated from cached info: {email: "user@gmail.com", ...}
```

### LocalStorage After Success
```
// Application → Local Storage → https://studyai-gamma.vercel.app
study_hub_user: '{"email":"user@gmail.com","name":"User Name","picture":"..."}'
```

---

## Debugging on Phone

### Chrome on Android
1. Install Chrome on desktop
2. Go to `chrome://inspect/#devices`
3. Connect Android via USB
4. Enable USB debugging on phone
5. Click "Inspect" for Vercel URL
6. See live console logs

### Safari on iPhone
1. Enable Developer Menu on iPhone
2. Connect to Mac
3. Open Safari on Mac
4. Develop → [Your Device] → [Your Tab]
5. Use Safari Web Inspector

### Remote Console Logs
- Even without remote debugging, check if Firebase/Sentry is logging
- Or add `console.log` with `window.fetch` to send to backend

---

## Quick Fixes to Try

1. **Clear Everything**
   ```
   1. Close all browser tabs
   2. Clear browser cache (Ctrl+Shift+Delete)
   3. Clear cookies specifically
   4. Clear LocalStorage (Application → Storage → Clear Site Data)
   5. Hard refresh (Ctrl+Shift+R)
   6. Try login again
   ```

2. **Check Backend Is Running**
   ```
   Curl to test:
   curl -i https://studyai-production.up.railway.app/health
   
   Expected:
   HTTP/2 200
   {"status": "healthy"}
   ```

3. **Force Redirect**
   ```
   Instead of using login button, manually visit:
   https://studyai-production.up.railway.app/auth/google
   ```

4. **Check OAuth Redirect URI**
   - Google Cloud Console:
     - Go to https://console.cloud.google.com
     - APIs & Services → Credentials
     - Edit OAuth Client
     - Check "Authorized redirect URIs"
     - Should include: `https://studyai-production.up.railway.app/auth/google/callback`

---

## If All Else Fails

Check these backend environment variables are set on Railway:

```
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
FLASK_SECRET_KEY=... (set to random string)
FRONTEND_URL=https://studyai-gamma.vercel.app
RAILWAY_PUBLIC_DOMAIN=... or RAILWAY_DOMAIN=...
GROQ_API_KEY=...
```

If any are missing, OAuth will fail silently or with errors.

**Contact Support**: If console logs show different errors, share:
1. Console error messages (screenshot or text)
2. Network tab of failing request
3. Whether error happens on desktop/phone/both
4. Which backend logs are visible (ask via SSH to Railway)
