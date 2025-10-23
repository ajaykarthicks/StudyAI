# 🔴 FIX: "Invalid State" Error on Phone/Production Login

## ⏱️ Takes 5 minutes - Follow these steps EXACTLY

### Step 1: Go to Google Cloud Console (2 min)

1. Open: https://console.cloud.google.com
2. Make sure you're in the right Google Account (the one you created the OAuth app with)
3. At the top, click the **Project selector** (shows project name)
4. Find your StudyAI project and click it
5. Left sidebar → **APIs & Services** → **Credentials**

### Step 2: Edit Your OAuth Client (2 min)

1. Under "OAuth 2.0 Client IDs", find the one that says **Web application**
2. Click on it to edit
3. You'll see a form with various fields

### Step 3: Update Redirect URIs (1 min)

**IMPORTANT: This is the critical step!**

Look for the field: **"Authorized redirect URIs"**

**DELETE any of these if they exist:**
- ❌ `http://localhost:5000/auth/google/callback`
- ❌ `http://127.0.0.1:5000/auth/google/callback`
- ❌ Any URL with `192.168.` or local IP address
- ❌ Any URLs that don't start with `https://`

**KEEP/ADD only this ONE URL:**
```
https://studyai-production.up.railway.app/auth/google/callback
```

### Step 4: Save and Wait (2+ min)

1. Click the **SAVE** button at the bottom
2. You should see a success message
3. **WAIT 5-10 MINUTES** - Google takes time to propagate changes
4. Don't test yet!

### Step 5: Clear Your Browser (1 min)

After waiting 5-10 minutes:

1. Open your browser
2. Press **F12** to open DevTools
3. Click **Application** tab (or **Storage**)
4. On the left, click **Cookies**
5. You should see cookies for `studyai-production.up.railway.app` and `studyai-gamma.vercel.app`
6. **Delete ALL cookies** from both domains
7. Close DevTools (F12 again)
8. **Close your browser completely** and reopen it

### Step 6: Test the App (1 min)

1. Open: **https://studyai-gamma.vercel.app**
2. Click **"Continue with Google"**
3. Select your Gmail account
4. You should see the dashboard ✅

## ✅ If It Works

Congratulations! Your app is now working correctly on production! 🎉

## ❌ If You Still Get "Invalid State"

### Check These:

**Option A: You're on your phone connected to WiFi**
- This won't work unless you register the phone's IP in Google
- For now, test on: https://studyai-gamma.vercel.app from a desktop/laptop
- OR if you need phone support, tell me your local IP and I'll help add it

**Option B: Check Railway Dashboard**
1. Go to: https://railway.app/dashboard
2. Click your **Backend** service
3. Click **Logs** tab
4. When you click login, look for these lines:
   ```
   [DEBUG] /auth/google route called
   [DEBUG] State generated: ...
   ```
   If you DON'T see these, your backend might not have redeployed
   - Wait 5 minutes and try again

**Option C: Hard Refresh Browser**
1. Press: **Ctrl + Shift + R** (Windows) or **Cmd + Shift + R** (Mac)
2. This clears the cache and reloads the page
3. Try login again

**Option D: Use Incognito Mode**
1. Press: **Ctrl + Shift + N** (Windows) or **Cmd + Shift + N** (Mac)
2. Go to: https://studyai-gamma.vercel.app
3. Try login - fresh browser, no old cookies
4. If this works, it means your cookies were corrupted

## 📝 Checklist

- [ ] Went to Google Cloud Console
- [ ] Found my OAuth app
- [ ] Edited the app
- [ ] Deleted all localhost URLs
- [ ] Added ONLY: `https://studyai-production.up.railway.app/auth/google/callback`
- [ ] Clicked SAVE
- [ ] Waited 5-10 minutes
- [ ] Cleared all cookies from browser
- [ ] Closed and reopened browser
- [ ] Tested at https://studyai-gamma.vercel.app
- [ ] ✅ See dashboard after login!

## 🆘 Still Stuck?

If you still see "Invalid state" after following ALL these steps:

1. **Screenshot the Google OAuth redirect URIs** (show what's registered)
2. **Screenshot the Rails logs** when you try to login
3. Send me both screenshots with the error you're seeing

There's likely something simple that got misconfigured, but I can diagnose it from the screenshots.

---

**This should 100% fix your "Invalid state" error!** 🚀
