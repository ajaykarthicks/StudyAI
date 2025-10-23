# ⚡ CORS UPDATE - QUICK START

## ✅ Already Done

Your `backend/app.py` CORS has been updated to:
- ✅ Always allow localhost (development)
- ✅ Auto-detect Vercel URL from environment variable
- ✅ Add Vercel to allowed origins automatically
- ✅ Log which origins are allowed

---

## 🚀 What to Do Now (3 Steps)

### Step 1: Push to GitHub
```bash
git push origin main
```

### Step 2: Add Environment Variable to Railway

1. Go to: https://railway.app/dashboard
2. Click your project
3. Go to **Variables** tab
4. Click **New Variable**
5. Add:
   - **Key:** `VERCEL_URL`
   - **Value:** `your-vercel-domain.vercel.app`
   - **Example:** `studyai.vercel.app`
6. Click **Save**
7. Railway auto-redeploys automatically

### Step 3: Wait & Test

1. Wait 2-3 minutes for Railway to redeploy
2. Test your frontend: `https://your-vercel-domain.vercel.app`
3. Try Google login
4. Should work! ✅

---

## 🔍 How to Verify

Check Railway logs should show:
```
[CORS] Allowed origins: ['http://localhost:3000', 'http://127.0.0.1:3000', 'https://your-vercel-domain.vercel.app']
```

---

## 📋 Environment Variable You Need to Add

| Service | Key | Value |
|---------|-----|-------|
| Railway | `VERCEL_URL` | `your-vercel-domain.vercel.app` |

---

**That's it! Your CORS is production-ready!** 🚀

See `CORS_UPDATE.md` for complete details and troubleshooting.
