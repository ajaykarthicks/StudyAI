# Production-Only Deployment Setup

## ✅ What Changed

The application is now **production-only** with zero localhost support. All traffic goes through:
- **Frontend:** Vercel (`https://studyai-gamma.vercel.app`)
- **Backend:** Railway (`https://studyai-production.up.railway.app`)

## 🔴 CRITICAL: Google Cloud Console Configuration

You MUST update Google OAuth to allow ONLY production URLs:

### Go to: https://console.cloud.google.com
1. APIs & Services → **Credentials**
2. Click your **OAuth Client ID** (web application)
3. In **Authorized redirect URIs**, set ONLY:
   ```
   https://studyai-production.up.railway.app/auth/google/callback
   ```
4. Remove any localhost URIs
5. Click **Save**

## 📋 Required Environment Variables

### Railway Backend Environment Variables
Set these in Railway dashboard (Backend service → Variables):

| Variable | Value | Required |
|----------|-------|----------|
| `FLASK_SECRET_KEY` | Your secret key | ✅ Yes |
| `GOOGLE_CLIENT_ID` | Your Client ID from Google Cloud | ✅ Yes |
| `GOOGLE_CLIENT_SECRET` | Your Client Secret | ✅ Yes |
| `GROQ_API_KEY` | Your Groq API key | ✅ Yes |
| `FRONTEND_URL` | `https://studyai-gamma.vercel.app` | ✅ Yes |
| `ENVIRONMENT` | `production` | ✅ Yes |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | ⚠️ Optional |
| `RAILWAY_PUBLIC_DOMAIN` | Auto-set by Railway | ✅ Auto |

**IMPORTANT:** `RAILWAY_PUBLIC_DOMAIN` must be set by Railway automatically. If the app fails to start, it means this variable is not available.

### Vercel Frontend Environment Variables
Set these in Vercel dashboard (Settings → Environment Variables):

Currently none needed (API URL is hardcoded in frontend code).

## 🚀 Deployment Steps

### 1. Update Google Cloud Console ⚠️
```
https://console.cloud.google.com
→ Credentials
→ Edit OAuth Client
→ Authorized redirect URIs:
   https://studyai-production.up.railway.app/auth/google/callback
→ Save
```

### 2. Update Railway Variables
Go to Railway dashboard and ensure all required variables are set (see table above).

### 3. Push to GitHub
```powershell
git push origin main
```

### 4. Vercel Auto-Deploys
- Vercel automatically deploys when you push to GitHub
- Wait 2-3 minutes for deployment

### 5. Railway Auto-Deploys
- Railway automatically re-deploys when environment variables change
- Wait 2-3 minutes for deployment

### 6. Test Production
1. Open `https://studyai-gamma.vercel.app`
2. Click "Continue with Google"
3. Complete OAuth login
4. Should see dashboard ✅

## 🔒 Production Security

### Session Cookies
- ✅ `SESSION_COOKIE_SECURE = True` (HTTPS only)
- ✅ `SESSION_COOKIE_HTTPONLY = True` (JS can't access)
- ✅ `SESSION_COOKIE_SAMESITE = 'None'` (cross-site allowed)

### CORS
- ✅ Only allows requests from: `https://studyai-gamma.vercel.app`
- ✅ Credentials required for all cross-origin requests

### OAuth
- ✅ `OAUTHLIB_INSECURE_TRANSPORT = 0` (HTTPS required)
- ✅ In-memory OAuth flow storage (secure state management)
- ✅ Automatic state validation

## 🔍 Debugging

### Check Backend Logs
Railway Dashboard → Backend Service → Logs

Look for:
```
[CORS] Allowed origins: ['https://studyai-gamma.vercel.app', ...]
[Session] SECURE=True, SAMESITE=None (Production HTTPS)
[Init] BACKEND_URL: https://studyai-production.up.railway.app
[Init] FRONTEND_URL: https://studyai-gamma.vercel.app
[Init] GOOGLE_REDIRECT_URI: https://studyai-production.up.railway.app/auth/google/callback
```

### Login Flow Logs
When user clicks "Continue with Google":
```
[DEBUG] /auth/google route called
[DEBUG] State generated: abc123def456...
[DEBUG] Flow stored in oauth_flows
```

After Google redirects:
```
[DEBUG] Callback received
[DEBUG] Received state: abc123def456...
[DEBUG] Flow retrieved from oauth_flows
[DEBUG] Token fetched successfully
[DEBUG] User info retrieved: user@gmail.com
[DEBUG] Redirecting to: https://studyai-gamma.vercel.app/?dashboard=1
```

### Common Issues

**Error: "Invalid state"**
- ✅ Check Google Cloud Console has correct redirect URI
- ✅ Make sure Railway variables include `FRONTEND_URL`
- ✅ Check backend logs show flow was stored/retrieved

**Error: CORS error in console**
- ✅ Check frontend is calling correct API_BASE_URL
- ✅ Verify FRONTEND_URL matches Vercel domain
- ✅ Check backend CORS configuration

**Login redirects to blank page**
- ✅ Check FRONTEND_URL is set in Railway variables
- ✅ Hard refresh browser (Ctrl+Shift+R)
- ✅ Clear all cookies for the domain

## 📝 Code Changes Summary

### backend/app.py
- ✅ Removed all localhost detection
- ✅ Changed `OAUTHLIB_INSECURE_TRANSPORT` to `0` (HTTPS only)
- ✅ Set `SESSION_COOKIE_SECURE = True` (always)
- ✅ Set `SESSION_COOKIE_SAMESITE = 'None'` (always)
- ✅ Simplified CORS to only allow Vercel URL
- ✅ Removed dynamic redirect URI detection
- ✅ Uses `RAILWAY_PUBLIC_DOMAIN` for backend URL (required)
- ✅ Uses `FRONTEND_URL` for redirect target

### frontend/app.js
- ✅ Hardcoded `API_BASE_URL` to Railway production URL
- ✅ Removed localhost detection logic

## ✨ Result

```
User on Phone/Desktop/Tablet
↓
Opens: https://studyai-gamma.vercel.app
↓
Frontend loads from Vercel
↓
Clicks "Continue with Google"
↓
Redirects to: https://studyai-production.up.railway.app/auth/google
↓
Backend redirects to Google OAuth
↓
User logs in with Gmail
↓
Google redirects to: https://studyai-production.up.railway.app/auth/google/callback
↓
Backend validates, creates session
↓
Redirects to: https://studyai-gamma.vercel.app/?dashboard=1
↓
Dashboard shows ✅
```

**No more "Invalid state" errors!** 🎉
**Works anywhere, anytime, any device!** 🌍
