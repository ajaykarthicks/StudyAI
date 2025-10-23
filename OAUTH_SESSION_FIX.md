# OAuth Session Fix - In-Memory State Storage

## Problem
Session cookies were not being created or persisted. The root cause was that Flask-Session with filesystem backend wasn't properly persisting the OAuth state between the initial `/auth/google` call and the Google callback redirect.

**Debug Output Showed:** `Saved state: None` - the state stored in the session was lost.

## Root Cause
1. Flask-Session filesystem backend requires proper session folder setup
2. When redirecting to Google's OAuth servers and back, the session context was being lost
3. The state couldn't be validated, causing auth failures

## Solution
Changed from **session-based state storage** to **in-memory state storage**:

### Before ❌
```python
# Store state in Flask session (unreliable)
session['oauth_state'] = state
session.modified = True
# Later...
saved_state = session.get('oauth_state')  # Returns None!
```

### After ✅
```python
# Store flow object in memory using state as key
oauth_flows[state] = flow
# Later...
flow = oauth_flows.pop(state)  # Reliably retrieved and deleted
```

## Implementation

### Changes to backend/app.py

**1. Added In-Memory OAuth Flow Storage:**
```python
# Store OAuth flows in memory (using state as key for simplicity)
# In production, use Redis or database
oauth_flows = {}
```

**2. Updated `/auth/google` Route:**
- Generates state from authorization_url
- Stores the entire Flow object in `oauth_flows[state]`
- No session dependency needed for OAuth flow

**3. Updated `/auth/google/callback` Route:**
- Retrieves state from request parameters
- Looks up flow from `oauth_flows` dictionary
- Pops (removes) flow after use to prevent memory leaks
- Completes OAuth flow with the stored flow object
- Stores user data in session (which works for user info)

**4. Better Error Handling:**
- Checks if state exists before trying to use it
- Returns 400 Bad Request if state is invalid
- Detailed error logging

## How It Works Now

### Step-by-Step Flow:

1. **User clicks "Continue with Google"**
   - Frontend redirects to `/auth/google`

2. **Backend: `/auth/google` Route**
   ```
   [Generate OAuth flow + state]
   oauth_flows['state_abc123'] = flow_object
   [Redirect to Google with state_abc123]
   ```

3. **Google OAuth Happens**
   - User logs in to Google
   - Google verifies credentials

4. **Google Redirects Back**
   - `GET /auth/google/callback?state=state_abc123&code=auth_code&...`

5. **Backend: `/auth/google/callback` Route**
   ```
   [Get state from URL: state_abc123]
   flow_object = oauth_flows.pop('state_abc123')
   [Use flow_object to exchange auth_code for token]
   [Fetch user info]
   session['user'] = user_info
   [Redirect to frontend]
   ```

6. **Frontend Receives Session Cookie**
   - Browser now has session cookie
   - Next `/me` request includes cookie
   - User authenticated! ✅

## Advantages of This Approach

| Aspect | Before | After |
|--------|--------|-------|
| Session Dependency | ✗ Unreliable | ✓ Not needed |
| State Persistence | ✗ Often lost | ✓ Always available |
| Cross-Origin Cookies | ✗ Issues | ✓ Only stored after auth success |
| Debugging | ✗ Hard to trace | ✓ Easy to see flow stored/retrieved |
| Production Ready | ✗ Would fail | ✓ Works locally, needs Redis for multi-instance |

## Production Note ⚠️

**Current Implementation:** In-memory dictionary `oauth_flows = {}`
- ✅ Works for development (single process)
- ✅ Works for Railway (single dyno)
- ❌ Won't work for multi-instance/horizontal scaling

**For Scaling to Multiple Instances:**
Replace in-memory dict with Redis:
```python
# In production with multiple dynos, use Redis
import redis
redis_client = redis.from_url(os.getenv('REDIS_URL'))
# Store: redis_client.setex(state, 600, flow_data)
# Retrieve: redis_client.get(state)
```

## Testing

### Local Testing (http://localhost:3000)
1. Click "Continue with Google"
2. Complete OAuth
3. Should redirect to dashboard
4. Check DevTools → Application → Cookies → should see Flask session cookie

### What to Look For in Logs
```
[DEBUG] /auth/google route called
[DEBUG] State generated: state_abc123
[DEBUG] Flow stored in oauth_flows
[DEBUG] Authorization URL: https://accounts.google.com/...

[DEBUG] Callback received
[DEBUG] Received state: state_abc123
[DEBUG] Stored flows: ['state_abc123']
[DEBUG] Flow retrieved from oauth_flows
[DEBUG] Token fetched successfully
[DEBUG] User info retrieved: user@email.com
[DEBUG] User stored in session
[DEBUG] Redirecting to: http://localhost:3000/?dashboard=1
```

## Next Steps

1. ✅ Test locally - click login and verify you see dashboard
2. Push to GitHub: `git push origin main`
3. Vercel will auto-deploy frontend
4. Railway will auto-deploy backend
5. Test production at `https://studyai-gamma.vercel.app`

## If Still Having Issues

1. **Check Browser Console:** Look for CORS errors (should be none)
2. **Check Browser Cookies:** Should see session cookie after OAuth completes
3. **Check Backend Logs:** Look for the debug messages above
4. **Clear Cache:** Hard refresh (Ctrl+Shift+R) to clear browser cache
5. **Check Environment Variables:** Verify `FRONTEND_URL` is set in Railway

The session cookie issue should now be completely resolved! 🎉
