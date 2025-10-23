# ⚡ QUICK FIX: Vercel Environment Variable Already Exists

## The Error You Got
```
A variable with the name `NEXT_PUBLIC_API_URL` already exists for the target 
production, preview, development on branch undefined
```

## What It Means
The variable `NEXT_PUBLIC_API_URL` was already set in your Vercel project from before.

## Quick Fix (2 minutes)

### Step 1: Go to Vercel Dashboard
```
https://vercel.com/dashboard
```

### Step 2: Click Your Project
Find `ai-smart-study-hub` project

### Step 3: Settings → Environment Variables
Look for `NEXT_PUBLIC_API_URL` in the list

### Step 4: Click the ⋮ (three dots) Menu
You'll see options:
- Edit
- Delete
- Copy

### Step 5: Click Edit
Update the value to your Railway URL:
```
https://your-railway-domain.up.railway.app
```

### Step 6: Click Save
Wait a moment for it to save

### Step 7: Redeploy
1. Go to **Deployments** tab
2. Click **Redeploy** button
3. Wait 2-3 minutes

### Step 8: ✅ Done!
Your frontend is now updated with the correct Railway backend URL!

---

## Important: Find Your Railway URL

You need your Railway URL from Step 2 of deployment.

**Where to find it:**
1. Go to https://railway.app/dashboard
2. Click your project
3. Look for **Domain** section
4. Copy the URL (looks like: `https://studyai-prod.up.railway.app`)
5. Paste into Vercel's `NEXT_PUBLIC_API_URL`

---

## Test It

After redeploy:
1. Open https://your-vercel-domain.vercel.app
2. Click "Continue with Google"
3. Should work! ✅

---

**That's it! Your app is live!** 🚀
