# Production Redirect Fix - OAuth Callback

## Problem
After logging in with Google OAuth, the backend was redirecting back to `http://localhost:3000` instead of `https://studyai-gamma.vercel.app`.

## Solution
Updated the OAuth callback to:
1. Check the `Origin` header from the request
2. If the request came from localhost → redirect to `http://localhost:3000` (development)
3. If the request came from production → redirect to `https://studyai-gamma.vercel.app` (production)

## What Changed

### backend/app.py
- Updated `/auth/google/callback` route to detect request origin
- Added logic to choose frontend URL based on where request came from

### backend/.env (Local)
- Added `FRONTEND_URL=https://studyai-gamma.vercel.app`

## Railway Configuration Required ⚠️

Go to your Railway project dashboard and add this environment variable:

**Variable Name:** `FRONTEND_URL`
**Variable Value:** `https://studyai-gamma.vercel.app`

### Steps:
1. Go to https://railway.app/dashboard
2. Select your project
3. Click on the backend service (studyai-production or similar)
4. Go to "Variables" tab
5. Click "New Variable"
6. Set Name: `FRONTEND_URL`
7. Set Value: `https://studyai-gamma.vercel.app`
8. Click "Add"
9. Railway will auto-redeploy with the new variable

## How It Works

When you visit the production app at `https://studyai-gamma.vercel.app`:

1. Click "Continue with Google"
2. Backend receives OAuth callback from Google
3. Checks the `Origin` header (will be `https://studyai-gamma.vercel.app`)
4. Since it doesn't contain "localhost", uses the `FRONTEND_URL` environment variable
5. Redirects to `https://studyai-gamma.vercel.app/?dashboard=1`
6. Dashboard loads in production ✅

## Testing Locally

Testing at `http://localhost:3000` still works because:
1. The `Origin` header will be `http://localhost:3000`
2. Backend detects "localhost" in the origin
3. Redirects to `http://localhost:3000/?dashboard=1` (development)
4. Dashboard loads locally ✅

## Next Steps

1. Add `FRONTEND_URL` to Railway environment variables
2. Push code changes to GitHub (will auto-redeploy)
3. Test login at https://studyai-gamma.vercel.app
4. Should now stay in production after login ✅
