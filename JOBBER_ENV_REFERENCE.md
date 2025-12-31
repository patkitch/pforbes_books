# Jobber Environment Variables Reference

## Complete List of Jobber Variables

Here are ALL the Jobber-related environment variables your application uses:

### ✅ Required for OAuth Flow

1. **JOBBER_CLIENT_ID**
   - Your Jobber App's client ID
   - Value: `7e67e5f1-15c6-43ad-a75f-44ab5e0f29ce`
   - Where to get it: https://developer.getjobber.com/myapps

2. **JOBBER_CLIENT_SECRET**
   - Your Jobber App's client secret
   - Value: `86c6c27da56b610c94b04c9070305b7fe008ce0a46bf94cbfd9d14d351860d4a`
   - Where to get it: https://developer.getjobber.com/myapps

3. **JOBBER_OAUTH_REDIRECT_URI**
   - Where Jobber sends the user after OAuth authorization
   - Local: `http://localhost:8003/jobber/oauth/callback/`
   - Production: `https://pforbes-books-uuad7.ondigitalocean.app/jobber/oauth/callback/`

### ✅ API Configuration

4. **JOBBER_API_URL**
   - Jobber's GraphQL API endpoint
   - Value: `https://api.getjobber.com/api/graphql`
   - Usually doesn't change

5. **JOBBER_API_VERSION**
   - API version to use
   - Value: `2025-04-16`
   - Check Jobber docs for latest version

6. **JOBBER_OAUTH_TOKEN_URL**
   - OAuth token exchange endpoint
   - Value: `https://api.getjobber.com/api/oauth/token`
   - Usually doesn't change

7. **JOBBER_OAUTH_AUTHORIZE_URL**
   - OAuth authorization endpoint
   - Value: `https://api.getjobber.com/api/oauth/authorize`
   - Usually doesn't change

### ⚠️ Optional (Managed by OAuth)

8. **JOBBER_ACCESS_TOKEN**
   - JWT access token for API requests
   - Your current token expires: **December 28, 2025**
   - **Best practice:** Don't set this manually - let the OAuth flow obtain it
   - Stored in database: `JobberToken` model

---

## Environment-Specific Values

### For LOCAL development (.env file):

```bash
JOBBER_CLIENT_ID=7e67e5f1-15c6-43ad-a75f-44ab5e0f29ce
JOBBER_CLIENT_SECRET=86c6c27da56b610c94b04c9070305b7fe008ce0a46bf94cbfd9d14d351860d4a
JOBBER_API_URL=https://api.getjobber.com/api/graphql
JOBBER_API_VERSION=2025-04-16
JOBBER_OAUTH_REDIRECT_URI=http://localhost:8003/jobber/oauth/callback/
JOBBER_OAUTH_TOKEN_URL=https://api.getjobber.com/api/oauth/token
JOBBER_OAUTH_AUTHORIZE_URL=https://api.getjobber.com/api/oauth/authorize
JOBBER_ACCESS_TOKEN=your-token-here
```

### For PRODUCTION (DigitalOcean App Platform):

Set these in: **Settings → pforbes-books-uuad7 → Settings → App-Level Environment Variables**

```
JOBBER_CLIENT_ID = 7e67e5f1-15c6-43ad-a75f-44ab5e0f29ce
JOBBER_CLIENT_SECRET = 86c6c27da56b610c94b04c9070305b7fe008ce0a46bf94cbfd9d14d351860d4a
JOBBER_API_URL = https://api.getjobber.com/api/graphql
JOBBER_API_VERSION = 2025-04-16
JOBBER_OAUTH_REDIRECT_URI = https://pforbes-books-uuad7.ondigitalocean.app/jobber/oauth/callback/
JOBBER_OAUTH_TOKEN_URL = https://api.getjobber.com/api/oauth/token
JOBBER_OAUTH_AUTHORIZE_URL = https://api.getjobber.com/api/oauth/authorize
JOBBER_ACCESS_TOKEN = (optional - will be in database after OAuth)
```

**Note:** In DigitalOcean, enter values WITHOUT quotes (no quotes around the values in the UI)

---

## How the OAuth Flow Works

1. User visits: `/jobber/oauth/start/`
2. App redirects to Jobber's authorization page
3. User authorizes your app
4. Jobber redirects back to: `/jobber/oauth/callback/?code=...`
5. Your app exchanges the code for an access token
6. Token is saved in `JobberToken` database model
7. Future API calls use the token from the database

---

## Token Expiration

Your current access token expires on **December 28, 2025** (tomorrow!).

After expiration:
1. Go to: `http://localhost:8003/jobber/oauth/start/`
2. Authorize the app again
3. Fresh token will be saved to database
4. Token includes a refresh token for automatic renewal

---

## Quick Checklist

### ✅ What you've already done:
- [x] Created Jobber App on developer.getjobber.com
- [x] Got Client ID and Secret
- [x] Set variables in DigitalOcean (from your screenshot)
- [x] Updated settings.py to read from environment

### 📋 What to do next:
- [ ] Replace your local .env file with the corrected one
- [ ] Test OAuth flow locally: `python manage.py runserver`
- [ ] Visit: `http://localhost:8003/jobber/oauth/start/`
- [ ] Verify new token is saved in database
- [ ] Test syncing data from Jobber

---

## Troubleshooting

**Problem:** "Invalid client credentials"
- Check JOBBER_CLIENT_ID and JOBBER_CLIENT_SECRET are correct
- Verify they match what's in https://developer.getjobber.com/myapps

**Problem:** "Redirect URI mismatch"
- Make sure JOBBER_OAUTH_REDIRECT_URI matches exactly what's configured in your Jobber App settings
- Local: `http://localhost:8003/jobber/oauth/callback/`
- Production: `https://pforbes-books-uuad7.ondigitalocean.app/jobber/oauth/callback/`

**Problem:** "Token expired"
- Run the OAuth flow again to get a fresh token
- Check JobberToken model in database for current token
