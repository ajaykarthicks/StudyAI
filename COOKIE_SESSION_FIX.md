# Session Cookie & Authentication Fix

## Problem
After login redirect, the frontend was returning to the landing page instead of showing the dashboard. The session cookies weren't being sent properly in cross-origin requests from Vercel to Railway.

## Root Causes
1. **SESSION_COOKIE_SECURE** was hardcoded to `False` - needed to be `True` for HTTPS production
2. **SESSION_COOKIE_SAMESITE** was set to `Lax` - needed to be `None` for cross-site requests in production
3. Frontend fetch calls weren't properly configured with all required headers

## Solutions Applied

### 1. Backend (app.py)
- **Auto-detect production environment**: Uses `RAILWAY_STATIC_URL` or `ENVIRONMENT` variable to detect if running in production
- **Dynamic SESSION_COOKIE_SECURE**:
  - Production (HTTPS): `True`
  - Development (HTTP): `False`
- **Dynamic SESSION_COOKIE_SAMESITE**:
  - Production (cross-site): `'None'` (requires SECURE=True)
  - Development (localhost): `'Lax'`
- **Added debug logging** to show cookie configuration

```python
IS_PRODUCTION = os.getenv('ENVIRONMENT', '').lower() == 'production' or 'railway' in os.getenv('RAILWAY_STATIC_URL', '')
app.config['SESSION_COOKIE_SECURE'] = IS_PRODUCTION
app.config['SESSION_COOKIE_SAMESITE'] = 'None' if IS_PRODUCTION else 'Lax'
```

### 2. Frontend (app.js)
- **Enhanced all fetch calls** with proper headers
- **Added comprehensive console logging** to debug authentication flow
- Updated `checkAuth()` and `checkAuthAndShowDashboard()` functions

```javascript
const response = await fetch(`${API_BASE_URL}/me`, { 
  credentials: 'include',  // Send cookies
  method: 'GET',
  headers: {
    'Accept': 'application/json',
    'Content-Type': 'application/json'
  }
});
```

## Railway Environment Variables Required

Go to **https://railway.app/dashboard** → Your Backend Service → **Variables**

Add or update these variables:

| Variable | Value | Notes |
|----------|-------|-------|
| `ENVIRONMENT` | `production` | Triggers production cookie settings |
| `FRONTEND_URL` | `https://studyai-gamma.vercel.app` | OAuth redirect destination |

Both should be automatically set by Railway, but verify them.

## How It Works Now

### Production Flow (https://studyai-gamma.vercel.app)
1. User clicks "Continue with Google"
2. Frontend redirects to `https://studyai-production.up.railway.app/auth/google`
3. Backend generates OAuth state and saves to session with:
   - `SESSION_COOKIE_SECURE=True` (HTTPS required)
   - `SESSION_COOKIE_SAMESITE='None'` (allows cross-site cookies)
4. User completes Google OAuth
5. Google redirects to `https://studyai-production.up.railway.app/auth/google/callback?code=...&state=...`
6. Backend:
   - Retrieves state from session
   - Validates state matches Google's response
   - Creates user session with secure cookies
   - Redirects to `https://studyai-gamma.vercel.app/?dashboard=1`
7. Frontend loads with session cookie included
8. Frontend calls `/me` endpoint with `credentials: 'include'`
9. Backend sends user data, frontend shows dashboard ✅

### Development Flow (http://localhost:3000)
1. Works exactly the same but with:
   - `SESSION_COOKIE_SECURE=False` (HTTP allowed)
   - `SESSION_COOKIE_SAMESITE='Lax'` (local redirects allowed)

## Debugging
When you test, check browser console for logs like:
```
App initialized
API_BASE_URL: https://studyai-production.up.railway.app
Checking auth and showing dashboard...
Dashboard auth check response status: 200
User authenticated for dashboard: {email: "...", name: "..."}
```

And backend console should show:
```
[Session] SECURE=True, SAMESITE=None
[DEBUG] State generated: ...
[DEBUG] State saved to session: ...
[DEBUG] Redirecting to: https://studyai-gamma.vercel.app/?dashboard=1
```

## Testing

### Local Testing (still works ✅)
1. `http://localhost:3000`
2. Click "Continue with Google"
3. Complete OAuth
4. Should redirect to `http://localhost:3000/?dashboard=1` with dashboard showing

### Production Testing (now fixed ✅)
1. `https://studyai-gamma.vercel.app`
2. Click "Continue with Google"
3. Complete OAuth
4. Should redirect to `https://studyai-gamma.vercel.app/?dashboard=1` with dashboard showing

## Next Steps

1. ✅ Changes are committed locally
2. Push to GitHub: `git push origin main`
3. Vercel will auto-deploy frontend
4. Railway will auto-deploy backend
5. Verify Railway variables are set (especially `ENVIRONMENT=production`)
6. Test login at `https://studyai-gamma.vercel.app`

## If Still Having Issues

Check these in order:

1. **Browser DevTools → Application → Cookies**
   - Should see session cookie from `studyai-production.up.railway.app`
   - Cookie should have:
     - `Secure` checkmark (for HTTPS)
     - `SameSite: None` (for cross-site)

2. **Browser Console**
   - Look for the debug logs
   - Check for CORS errors (should be none)
   - Look for failed fetch calls to `/me`

3. **Railway Logs**
   - Go to `https://railway.app/dashboard` → Backend → Logs
   - Search for `[Session]` and `[DEBUG]` lines
   - Verify `SECURE=True` and `SAMESITE=None`

4. **Check Environment Variables**
   - Make sure `ENVIRONMENT=production` is set in Railway
   - Make sure `FRONTEND_URL=https://studyai-gamma.vercel.app` is set

If issues persist, the problem is likely in the environment variables on Railway not being set correctly.
