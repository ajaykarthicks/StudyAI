# StudyAI Deployment Guide: Vercel + Railway

## 📋 Overview
- **Frontend**: Vercel (free, fast, global CDN)
- **Backend**: Railway (free tier, $5/month after)
- **Database**: File-based sessions (built-in to Flask)

---

## 🚀 STEP 1: Prepare Your Project

### 1.1 Check Files Created
✅ `.gitignore` - Protects sensitive files
✅ `backend/Procfile` - Tells Railway how to run your app
✅ `backend/runtime.txt` - Specifies Python version
✅ `frontend/vercel.json` - Vercel configuration
✅ `frontend/app.js` - Updated with dynamic API URL

### 1.2 Update requirements.txt with gunicorn
Run this command in your terminal:

```bash
cd backend
pip install gunicorn
pip freeze > requirements.txt
```

This adds gunicorn (production web server) to your dependencies.

---

## 📝 STEP 2: Create GitHub Repository

### 2.1 Sign up on GitHub
1. Go to **github.com**
2. Click "Sign up"
3. Create an account (use a strong password)

### 2.2 Create New Repository
1. After logging in, click the **+** icon (top right)
2. Select **New repository**
3. Name it: `ai-smart-study-hub`
4. Select **Public** (so Vercel/Railway can access it)
5. Click **Create repository**

### 2.3 Initialize Git Locally
Open terminal in your project folder:

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

**Replace YOUR_USERNAME with your actual GitHub username**

### 2.4 Verify on GitHub
- Go to your GitHub repo URL
- You should see all your files there
- Files in `.gitignore` should NOT be visible (that's correct!)

---

## 🚂 STEP 3: Deploy Backend on Railway

### 3.1 Create Railway Account
1. Go to **railway.app**
2. Click **Start Project**
3. Sign up with GitHub (easiest method)
4. Authorize Railway to access your GitHub

### 3.2 Create New Project
1. Click **Create Project**
2. Select **Deploy from GitHub repo**
3. Find your `ai-smart-study-hub` repository
4. Click **Deploy Now**

### 3.3 Configure Railway
Railway should auto-detect it's a Python project. If not:

1. Go to your Railway dashboard
2. Click on your project
3. Go to **Settings**
4. Set **Framework**: Python
5. Set **Python Version**: 3.10

### 3.4 Add Environment Variables
1. In Railway dashboard, go to **Variables**
2. Add these variables (from your `.env` file):

```
FLASK_SECRET_KEY=your_super_secret_key_12345678901234567890
GOOGLE_CLIENT_ID=24191536666-vsf97buq1glirsnb5to10k2hm87ibv63.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=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
GROQ_API_KEY=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
```

⚠️ **IMPORTANT**: Don't commit your `.env` file to GitHub!

### 3.5 Get Your Backend URL
1. In Railway dashboard, click on your project
2. Look for **Deployment** section
3. Copy the domain (e.g., `https://studyai-backend-prod.up.railway.app`)
4. **Save this URL** - you'll need it for Vercel

### 3.6 Fix GOOGLE_REDIRECT_URI
Update your `.env` in Railway:

```
GOOGLE_REDIRECT_URI=https://your-railway-url/auth/google/callback
```

Replace `your-railway-url` with your actual Railway backend URL.

---

## ☁️ STEP 4: Deploy Frontend on Vercel

### 4.1 Create Vercel Account
1. Go to **vercel.com**
2. Click **Sign Up**
3. Choose **Sign Up with GitHub** (easiest)
4. Authorize Vercel to access GitHub

### 4.2 Import Your Project
1. In Vercel dashboard, click **New Project**
2. Click **Import Git Repository**
3. Search for `ai-smart-study-hub`
4. Click **Import**

### 4.3 Configure Deployment
1. **Project Name**: `ai-smart-study-hub-frontend`
2. **Framework Preset**: Other
3. **Root Directory**: `./frontend`
4. Keep other settings default
5. Click **Deploy**

### 4.4 Add Environment Variables (Important!)
1. After deployment, go to **Settings**
2. Click **Environment Variables**
3. Add this variable:

```
Key: NEXT_PUBLIC_API_URL
Value: https://your-railway-url
```

Replace `your-railway-url` with your Railway backend URL from Step 3.5

### 4.5 Redeploy
1. Go back to **Deployments**
2. Click the three dots (...) on latest deployment
3. Select **Redeploy**

This picks up your new environment variable.

### 4.6 Get Your Frontend URL
1. In Vercel dashboard, find your project
2. Copy the domain (e.g., `https://ai-smart-study-hub-frontend.vercel.app`)
3. **Save this URL**

---

## 🔧 STEP 5: Update Google OAuth Settings

### 5.1 Update Redirect URI
Go to **Google Cloud Console**:

1. Visit **console.cloud.google.com**
2. Go to **APIs & Services** → **Credentials**
3. Find your OAuth client ID
4. Click **Edit**
5. Update **Authorized redirect URIs**:
   - Add: `https://your-railway-url/auth/google/callback`
   - Keep: `http://localhost:5000/auth/google/callback` (for local testing)
6. Click **Save**

### 5.2 Update Frontend CORS Origin
Update in `backend/app.py`:

```python
CORS(app, 
     supports_credentials=True, 
     resources={r"*": {
         "origins": [
             "http://localhost:3000",  # Local testing
             "http://127.0.0.1:3000",  # Local testing
             "https://your-vercel-frontend-url",  # Add your Vercel URL
         ],
         "methods": ["GET", "POST", "OPTIONS"],
         "allow_headers": ["Content-Type"]
     }},
     ...
)
```

Then push this to GitHub:

```bash
git add backend/app.py
git commit -m "Update CORS for production deployment"
git push
```

Both Vercel and Railway will auto-redeploy!

---

## ✅ STEP 6: Testing

### 6.1 Test Backend
Open in browser:
```
https://your-railway-url/me
```

You should see: `{"authenticated": false}`

### 6.2 Test Frontend
1. Go to `https://your-vercel-frontend-url`
2. You should see the StudyAI landing page
3. Try clicking "Continue with Google"
4. You should be redirected to Google login
5. After login, you should see the dashboard

### 6.3 Test Upload
1. Upload a PDF file
2. Try using each tool (Chat, Summarize, Quiz, Flashcards)
3. Check that responses come back

---

## 🐛 Troubleshooting

### Issue: "Cannot reach backend" or CORS error
**Solution**: 
- Check `app.js` has correct Railway URL
- Check CORS configuration in `app.py`
- Check Railway environment variables are set
- Check Railway deployment logs

### Issue: "Google login not working"
**Solution**:
- Verify `GOOGLE_REDIRECT_URI` in Railway matches the authorized redirect in Google Cloud
- Check Google OAuth credentials are in Railway env vars
- Test locally first with `localhost:5000`

### Issue: "Session not persisting"
**Solution**:
- Check `FLASK_SECRET_KEY` is set in Railway
- Clear browser cookies and try again
- Check Railway logs for errors

### Check Logs
**Railway logs:**
1. Go to Railway dashboard
2. Click your project
3. Scroll to **Build & Deploy** logs
4. Check **Recent Deploys** for errors

**Vercel logs:**
1. Go to Vercel dashboard
2. Click your project
3. Go to **Deployments**
4. Click latest deployment
5. Check **Build Logs** and **Runtime Logs**

---

## 📱 Local Development (Still Works!)

Your local setup still works:

```bash
# Terminal 1 - Backend
cd backend
python app.py

# Terminal 2 - Frontend
cd frontend
http-server -p 3000 --cors
```

Then open `http://localhost:3000`

---

## 🔒 Security Tips

1. **Never commit `.env`** - it's in `.gitignore`
2. **Use Railway secrets** for sensitive data
3. **Keep API keys private** - don't share URLs with keys
4. **Monitor usage** - check Groq and Google API quotas
5. **Update regularly** - keep dependencies updated

---

## 📊 Project URLs After Deployment

- **Frontend**: `https://your-vercel-domain.vercel.app`
- **Backend API**: `https://your-railway-domain.up.railway.app`
- **GitHub**: `https://github.com/your-username/ai-smart-study-hub`

---

## ⚡ Cost Breakdown

| Service | Free Tier | Cost |
|---------|-----------|------|
| Vercel | ✅ Free | $0/month |
| Railway | ✅ $5 credit/month | $0-5/month |
| Google OAuth | ✅ Free | $0 |
| Groq API | ✅ Free tier available | $0+ |

**Your project is mostly FREE! 🎉**

---

## 🆘 Need Help?

- Railway docs: https://docs.railway.app
- Vercel docs: https://vercel.com/docs
- Google OAuth: https://developers.google.com/identity

Good luck! 🚀
