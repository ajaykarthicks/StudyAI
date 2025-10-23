# 🚀 QUICK DEPLOYMENT CHECKLIST

## Pre-Deployment (Do these FIRST)

- [ ] Created `.gitignore` ✅
- [ ] Added `backend/Procfile` ✅
- [ ] Added `backend/runtime.txt` ✅
- [ ] Updated `backend/requirements.txt` with gunicorn ✅
- [ ] Updated `frontend/app.js` with dynamic API URL ✅
- [ ] Read `DEPLOYMENT_GUIDE.md` completely

## Step 1: GitHub (5 minutes)

- [ ] Create GitHub account: https://github.com
- [ ] Create new repository named `ai-smart-study-hub`
- [ ] Copy these commands and run in your project folder:

```bash
git config --global user.name "Your Name"
git config --global user.email "your@email.com"
git init
git add .
git commit -m "Initial commit: StudyAI project"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/ai-smart-study-hub.git
git push -u origin main
```

## Step 2: Railway Backend (10 minutes)

- [ ] Sign up on Railway: https://railway.app
- [ ] Click "Create Project" → "Deploy from GitHub repo"
- [ ] Select your `ai-smart-study-hub` repository
- [ ] Railway auto-detects Python ✅
- [ ] Go to Variables and add:
  - `FLASK_SECRET_KEY=your_super_secret_key_12345678901234567890`
  - `GOOGLE_CLIENT_ID=24191536666-vsf97buq1glirsnb5to10k2hm87ibv63.apps.googleusercontent.com`
  - `GOOGLE_CLIENT_SECRET=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`
  - `GROQ_API_KEY=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`
- [ ] Get your Railway URL (e.g., `https://studyai-prod.up.railway.app`)
- [ ] **SAVE this URL!**

## Step 3: Vercel Frontend (10 minutes)

- [ ] Sign up on Vercel: https://vercel.com
- [ ] Click "New Project" → "Import Git Repository"
- [ ] Select your `ai-smart-study-hub` repository
- [ ] Set Root Directory: `./frontend`
- [ ] After deployment, go to Settings → Environment Variables
- [ ] Add or Update: `NEXT_PUBLIC_API_URL=https://your-railway-url`
  - (Replace with your Railway URL from Step 2)
  - If variable already exists, click Edit instead of Add
  - See `VERCEL_ENV_FIX.md` if you get env variable error
- [ ] Redeploy to apply env vars
- [ ] Get your Vercel URL (e.g., `https://studyai.vercel.app`)
- [ ] **SAVE this URL!**

## Step 4: Google OAuth Update (5 minutes)

- [ ] Go to Google Cloud Console: https://console.cloud.google.com
- [ ] Edit OAuth client
- [ ] Update "Authorized redirect URIs":
  - Add: `https://your-railway-url/auth/google/callback`
  - (Keep localhost version for local testing)
- [ ] Save

## Step 5: Update CORS in Code

- [ ] Update `backend/app.py` CORS settings:
  - Add your Vercel URL to origins list
- [ ] Commit and push:
  ```bash
  git add backend/app.py
  git commit -m "Update CORS for production"
  git push
  ```
- [ ] Both Railway and Vercel auto-redeploy ✅

## Step 6: Test! (10 minutes)

- [ ] Test backend: `https://your-railway-url/me`
  - Should see: `{"authenticated": false}`
- [ ] Test frontend: `https://your-vercel-url`
  - Should see landing page with "Continue with Google"
- [ ] Try Google login
- [ ] Upload a PDF
- [ ] Test each tool (Chat, Summarize, Quiz, Flashcards)

## URLs You'll Need

Write these down! You'll need them:

```
GitHub Repo: https://github.com/YOUR_USERNAME/ai-smart-study-hub
Railway Backend: https://your-railway-domain.up.railway.app
Vercel Frontend: https://your-vercel-domain.vercel.app
Google Cloud Console: https://console.cloud.google.com
```

## Troubleshooting Quick Fixes

| Problem | Solution |
|---------|----------|
| "Cannot reach backend" | Check Railway URL in `app.js` matches |
| CORS errors | Add Vercel URL to CORS in `app.py` |
| Google login fails | Check redirect URI in Google Cloud |
| Blank page | Check Vercel deployment logs |
| Backend errors | Check Railway build logs |

## Support

- Railway docs: https://docs.railway.app
- Vercel docs: https://vercel.com/docs
- Can't find your URL? Check the dashboard under "Deployments"

---

**That's it! Your project is now live! 🎉**

Local development still works with `http://localhost:3000` and `http://localhost:5000`
