# ⚠️ GOOGLE OAUTH SETUP CHECKLIST

## Problem: Cookies Not Being Generated

This means the OAuth callback (`/auth/google/callback`) is **never being reached**. This happens when:

1. ❌ Google credentials not registered in Google Cloud Console
2. ❌ Redirect URI doesn't match exactly
3. ❌ OAuth credentials not set on Railway

## Step 1: Check Your Credentials Are On Railway

Go to https://railway.app → Your Project → Settings → Variables

You should see:
- ✅ `GOOGLE_CLIENT_ID` = `xxxxx.apps.googleusercontent.com`
- ✅ `GOOGLE_CLIENT_SECRET` = `GOCSPX-xxxxxx`
- ✅ `FLASK_SECRET_KEY` = some random string
- ✅ `GROQ_API_KEY` = your Groq API key

**If ANY are missing**, add them now!

### How to Get Google Credentials

1. Go to https://console.cloud.google.com
2. Create a new project or select existing
3. Enable "Google+ API"
4. Go to **Credentials** → **Create Credentials** → **OAuth Client ID**
5. Application type: **Web application**
6. Name it: `StudyAI`
7. Add authorized redirect URIs (see below)
8. Copy `Client ID` and `Client Secret`
9. Go to Railway Variables and paste them

## Step 2: Register Your Redirect URI in Google Cloud Console

This is **CRITICAL** - it must match EXACTLY!

1. Go to https://console.cloud.google.com
2. APIs & Services → Credentials
3. Click your OAuth Client ID (the one you created)
4. Under "Authorized redirect URIs" click **Edit**
5. **Add this URI EXACTLY**:
   ```
   https://studyai-production.up.railway.app/auth/google/callback
   ```
6. Click **Save**

## Step 3: Test the Debug Endpoint

1. Go to:
   ```
   https://studyai-production.up.railway.app/debug/config
   ```

2. You should see:
   ```json
   {
     "backend_url": "https://studyai-production.up.railway.app",
     "frontend_url": "https://studyai-gamma.vercel.app",
     "google_redirect_uri": "https://studyai-production.up.railway.app/auth/google/callback",
     "google_client_id_set": true,
     "google_client_secret_set": true,
     "cors_origins": "*"
   }
   ```

3. If `google_client_id_set` is `false`, the credentials aren't set on Railway

## Step 4: Manually Test OAuth Flow

1. In browser console, run:
   ```javascript
   window.location.href = 'https://studyai-production.up.railway.app/auth/google'
   ```

2. You should be redirected to Google login page

3. After logging in with Gmail, you should be redirected to:
   ```
   https://studyai-production.up.railway.app/auth/google/callback?state=...&code=...
   ```

4. **If you get a Google error** instead:
   - "Redirect URI mismatch" → Step 2 (fix the URI)
   - "Invalid client" → Check credentials in Step 1

## Step 5: Check Railway Logs

If the callback is reached but still no cookies:

1. Go to Railway dashboard
2. View app logs
3. Look for:
   ```
   [DEBUG] Callback received
   [DEBUG] Token fetched successfully
   [DEBUG] User info retrieved: your@gmail.com
   [DEBUG] user_data cookie SET
   [DEBUG] Redirecting to: https://studyai-gamma.vercel.app/?dashboard=1
   ```

4. **If you see errors**, they'll be here with details

## Common Errors & Fixes

### Error: "Redirect URI mismatch"
**Cause**: URI in Google Cloud Console doesn't match code
**Fix**: 
1. Check Google Cloud Console exactly has:
   ```
   https://studyai-production.up.railway.app/auth/google/callback
   ```
2. Case matters! Check capital letters
3. No trailing slash!

### Error: "Invalid client ID"
**Cause**: GOOGLE_CLIENT_ID not set on Railway
**Fix**: Go to Railway Variables and add it

### Error: "The redirect URI does not match the one in the request"
**Cause**: Frontend using wrong URL
**Fix**: Make sure frontend has:
   ```javascript
   const API_BASE_URL = 'https://studyai-production.up.railway.app'
   ```

### No logs appearing
**Cause**: Request not reaching backend
**Fix**: 
1. Check frontend is calling right URL
2. Check CORS is enabled on backend
3. Check Firebase/Network logs

## Quick Checklist

- [ ] GOOGLE_CLIENT_ID set on Railway
- [ ] GOOGLE_CLIENT_SECRET set on Railway  
- [ ] Exactly this URI in Google Cloud Console:
  ```
  https://studyai-production.up.railway.app/auth/google/callback
  ```
- [ ] No typos or extra slashes
- [ ] Frontend has correct API_BASE_URL
- [ ] CORS allows all origins on backend
- [ ] /debug/config endpoint shows `true` for both credentials
- [ ] Can reach Google login page at `/auth/google`
- [ ] Redirected back from Google (not stuck on Google login)

## Step-by-Step for First-Time Setup

### 1. Create Google Project
```
https://console.cloud.google.com
→ New Project → "StudyAI"
→ Enable APIs & Services
→ Search "Google+ API" → Enable
```

### 2. Create OAuth Credentials
```
Credentials → Create Credentials → OAuth Client ID
→ Web application
→ Name: StudyAI
→ Add Authorized redirect URI:
   https://studyai-production.up.railway.app/auth/google/callback
→ Create
→ Copy Client ID and Secret
```

### 3. Set on Railway
```
Railway Dashboard
→ Your Project
→ Settings → Variables
→ Add GOOGLE_CLIENT_ID = (paste client ID)
→ Add GOOGLE_CLIENT_SECRET = (paste secret)
→ Railway auto-redeploys
→ Wait 2-3 minutes
```

### 4. Test
```
Open: https://studyai-gamma.vercel.app
Click: "Continue with Google"
→ Should redirect to Google login
→ After Gmail login, should see dashboard
```

## If Still Not Working

After all above steps, if cookies still don't generate:

1. **Check browser console for errors**
   - Press F12 → Console
   - Look for red errors

2. **Check Network tab**
   - F12 → Network
   - Click "Continue with Google"
   - Look for request to `/auth/google`
   - Does it redirect to Google?

3. **Check backend logs on Railway**
   - Should show when `/auth/google` is called
   - Should show when `/auth/google/callback` is called

4. **Verify callback is working**
   - Manually visit:
   ```
   https://studyai-production.up.railway.app/auth/google/callback
   ```
   - Should show error (because no state/code)
   - But proves endpoint exists

5. **Contact support with info**:
   - What error do you see (screenshot)?
   - Does `/debug/config` show both credentials as true?
   - What do the Railway logs show?

---

**Once you've done all these steps, try logging in and you should get the `user_data` cookie!** ✅
