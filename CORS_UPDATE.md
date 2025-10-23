# 🔐 CORS UPDATE FOR PRODUCTION - COMPLETE GUIDE

## What Was Done ✅

Your `backend/app.py` has been updated with **smart CORS configuration** that:
- ✅ Always allows localhost (for local development)
- ✅ Automatically detects Vercel URL from environment variables
- ✅ Adds Vercel URL to allowed origins when deployed
- ✅ Logs which origins are allowed (for debugging)

---

## How It Works

### Updated CORS Code

```python
# Build origins list - always include localhost for development
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Add production Vercel URL if available
VERCEL_URL = os.getenv('VERCEL_URL')
if VERCEL_URL and VERCEL_URL not in CORS_ORIGINS:
    CORS_ORIGINS.append(f"https://{VERCEL_URL}")

print(f"[CORS] Allowed origins: {CORS_ORIGINS}")

CORS(app, 
     supports_credentials=True, 
     resources={r"*": {
         "origins": CORS_ORIGINS,
         "methods": ["GET", "POST", "OPTIONS"],
         "allow_headers": ["Content-Type"]
     }},
     expose_headers=["Content-Type"],
     max_age=3600
)
```

### What Each Part Does

| Line | Purpose |
|------|---------|
| `CORS_ORIGINS = [...]` | Start with localhost URLs |
| `VERCEL_URL = os.getenv('VERCEL_URL')` | Get Vercel URL from environment |
| `if VERCEL_URL and...` | If Vercel URL exists, add it to list |
| `print(f"[CORS]...")` | Log which origins are allowed (helpful for debugging) |
| `CORS(app, ..., origins=CORS_ORIGINS)` | Use the dynamic origins list |

---

## How Vercel Provides the URL

When you deploy to Vercel, it **automatically sets** the `VERCEL_URL` environment variable:

**On Vercel Production:**
- Automatically set to your domain
- Example: `studyai.vercel.app`
- Gets added to CORS automatically ✅

**On Railway:**
- You need to **manually add** `VERCEL_URL` environment variable
- Set it to your Vercel frontend URL
- Example: `https://studyai.vercel.app`

---

## Step-by-Step: What to Do Now

### Step 1: Know Your URLs

Write down your URLs (you'll need these):

```
Vercel Frontend URL: https://your-vercel-domain.vercel.app
Railway Backend URL: https://your-railway-domain.up.railway.app
```

### Step 2: Add Environment Variable to Railway

1. Go to Railway Dashboard: https://railway.app/dashboard
2. Click your project
3. Go to **Variables** tab
4. Click **New Variable**
5. Add:
   - **Key:** `VERCEL_URL`
   - **Value:** `your-vercel-domain.vercel.app` (without https://)
   - Example: `studyai.vercel.app`
6. Click **Save**
7. Railway auto-redeploys in 1-2 minutes

### Step 3: Wait for Redeploy

Railway will automatically rebuild with the new environment variable.

When deployment is done, you should see in **Deploy Logs:**
```
[CORS] Allowed origins: ['http://localhost:3000', 'http://127.0.0.1:3000', 'https://your-vercel-domain.vercel.app']
```

---

## Verification: Check It's Working

### Test 1: Check CORS Headers

Open your browser and test:

```javascript
// Open console (F12) on your Vercel frontend
fetch('https://your-railway-url/me', {
  credentials: 'include'
})
.then(r => r.json())
.then(d => console.log(d))
```

Should work without CORS errors ✅

### Test 2: Try Google Login

1. Go to your Vercel frontend: `https://your-vercel-domain.vercel.app`
2. Click "Continue with Google"
3. Should redirect to Google login
4. After login, should redirect back and show dashboard
5. No CORS errors in console ✅

### Test 3: Check Railway Logs

1. Go to Railway Dashboard
2. Click your project
3. Go to **Deploy Logs**
4. Should see:
   ```
   [CORS] Allowed origins: ['http://localhost:3000', 'http://127.0.0.1:3000', 'https://your-vercel-url']
   ```

---

## What Each URL Does

| URL | Purpose | CORS Status |
|-----|---------|------------|
| `http://localhost:3000` | Local development (frontend) | ✅ Always allowed |
| `http://127.0.0.1:3000` | Local development alt | ✅ Always allowed |
| `https://your-vercel-url` | Production frontend | ✅ Added by CORS config |
| `https://your-railway-url` | Production backend | N/A (this is the API server) |

---

## Common Issues & Solutions

### Issue 1: CORS Error on Frontend
```
Access to fetch at 'https://railway-url/api/chat' from origin 'https://vercel-url' 
has been blocked by CORS policy
```

**Solution:**
1. Check Railway's `VERCEL_URL` environment variable is set
2. Verify it matches your actual Vercel URL
3. Check Railway redeploy completed
4. Restart your browser (F5)

### Issue 2: Logs Show Only Localhost Origins
```
[CORS] Allowed origins: ['http://localhost:3000', 'http://127.0.0.1:3000']
```

**Solution:**
1. Go to Railway Dashboard
2. Check **Variables** section
3. Verify `VERCEL_URL` is set and saved
4. Click **Redeploy** on latest deployment
5. Wait 2-3 minutes

### Issue 3: Google Login Fails
```
Error: redirect_uri_mismatch
```

**Solution:**
1. Go to Google Cloud Console
2. Update "Authorized redirect URIs"
3. Add: `https://your-railway-url/auth/google/callback`
4. Save and try again

---

## Complete Deployment Checklist

- [x] ✅ Updated CORS in `backend/app.py`
- [x] ✅ Committed locally
- [ ] Push to GitHub:
  ```bash
  git push origin main
  ```
- [ ] Go to Railway Dashboard
- [ ] Add `VERCEL_URL` environment variable with your Vercel URL
- [ ] Wait for auto-redeploy (2-3 minutes)
- [ ] Check Railway deploy logs for CORS message
- [ ] Test Google login on your Vercel frontend
- [ ] Test PDF upload
- [ ] Test AI tools (Chat, Summarize, Quiz, Flashcards)

---

## Your CORS Configuration is Now

**Smart & Flexible:**
- ✅ Works locally with `localhost:3000`
- ✅ Works in production with Vercel URL
- ✅ Auto-detects from environment variables
- ✅ Logs allowed origins for debugging
- ✅ No hardcoding needed (except environment vars)

---

## 🎯 Next Steps

1. ✅ CORS updated in code (done)
2. 📤 Push to GitHub
3. 🔧 Add `VERCEL_URL` to Railway Variables
4. ⏳ Wait for Railway redeploy
5. ✨ Test your app - should work perfectly!

---

## Environment Variables Summary

### Railway Should Have:
```
FLASK_SECRET_KEY=your_super_secret_key_12345678901234567890
GOOGLE_CLIENT_ID=24191536666-...
GOOGLE_CLIENT_SECRET=GOCSPX-...
GROQ_API_KEY=gsk_...
VERCEL_URL=your-vercel-domain.vercel.app (NEW!)
```

### Vercel Should Have:
```
NEXT_PUBLIC_API_URL=https://your-railway-domain.up.railway.app
```

---

**Your CORS is now production-ready! 🚀**

*Good luck with your deployment!* 💪
