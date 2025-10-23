# Google OAuth Redirect URI Fix

## Problem
When logging in from Vercel (production), Google was trying to redirect to `http://localhost:5000/auth/google/callback`, which:
1. Doesn't exist (localhost doesn't resolve from internet)
2. Causes "Invalid state" error because the state is generated on Railway but localhost isn't listening
3. User sees error in browser

## Root Cause
The `GOOGLE_REDIRECT_URI` was hardcoded to `http://localhost:5000` in the .env file.

## Solution

### Backend Changes (app.py)
Changed from hardcoded URI to **dynamic detection**:

```python
# If running on Railway, use the Railway URL; otherwise use localhost for dev
if os.getenv('RAILWAY_PUBLIC_DOMAIN'):
    BACKEND_URL = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}"
else:
    BACKEND_URL = 'http://localhost:5000'

GOOGLE_REDIRECT_URI = f"{BACKEND_URL}/auth/google/callback"
```

**Railway automatically sets `RAILWAY_PUBLIC_DOMAIN`** to your backend URL (e.g., `studyai-production.up.railway.app`)

### Environment Changes (.env)
Removed hardcoded `GOOGLE_REDIRECT_URI` - now generated automatically based on environment

## How It Works

### Local Development (http://localhost:3000)
1. `RAILWAY_PUBLIC_DOMAIN` is NOT set (local environment)
2. Backend URL = `http://localhost:5000`
3. OAuth redirect = `http://localhost:5000/auth/google/callback` ✅
4. Works perfectly for local testing

### Production (https://studyai-gamma.vercel.app)
1. `RAILWAY_PUBLIC_DOMAIN` = `studyai-production.up.railway.app` (set by Railway)
2. Backend URL = `https://studyai-production.up.railway.app`
3. OAuth redirect = `https://studyai-production.up.railway.app/auth/google/callback` ✅
4. Google redirects to correct backend URL

## Google Cloud Console - UPDATE REQUIRED ⚠️

You MUST add the production redirect URI to your Google OAuth app:

### Steps:
1. Go to **https://console.cloud.google.com**
2. Search for **"Credentials"** in top search
3. Click on your **OAuth Client ID** (the one with your Client ID)
4. In **Authorized redirect URIs** section, add:
   - ✅ `http://localhost:5000/auth/google/callback` (development - already there)
   - ➕ `https://studyai-production.up.railway.app/auth/google/callback` (production - ADD THIS)

5. Click **Save**

### Current Authorized Redirect URIs (should be):
```
http://localhost:5000/auth/google/callback
https://studyai-production.up.railway.app/auth/google/callback
```

## Testing Flow

### Before Google Console Update
1. Login from localhost: ✅ Works
2. Login from Vercel: ❌ Google rejects because URI not authorized

### After Google Console Update
1. Login from localhost: ✅ Works (uses localhost redirect)
2. Login from Vercel: ✅ Works (uses Railway redirect)

## Verification

### Check Backend is Using Correct URL
When you start the backend, look for logs:
```
[Init] BACKEND_URL: http://localhost:5000
[Init] GOOGLE_REDIRECT_URI: http://localhost:5000/auth/google/callback
```

When deployed to Railway, it will show:
```
[Init] BACKEND_URL: https://studyai-production.up.railway.app
[Init] GOOGLE_REDIRECT_URI: https://studyai-production.up.railway.app/auth/google/callback
```

## Next Steps

1. ✅ Backend code updated to use dynamic GOOGLE_REDIRECT_URI
2. ✅ .env cleaned up (removed hardcoded URI)
3. ⚠️ **TODO: Add production URL to Google Cloud Console**
4. Push to GitHub: `git push origin main`
5. Vercel auto-deploys frontend (no changes)
6. Railway auto-deploys backend (will use correct redirect URI)
7. Test login from production: `https://studyai-gamma.vercel.app`

## If Still Getting "Invalid state" Error

After updating Google Console, if error persists:

1. **Clear browser cache**: Hard refresh (Ctrl+Shift+R)
2. **Clear cookies**: Delete all cookies for the domain
3. **Check Railway logs**: Verify GOOGLE_REDIRECT_URI is correct
4. **Verify Google Console**: Make sure the URL is exactly as shown above

The production login should work after you add the redirect URI to Google Cloud Console!
