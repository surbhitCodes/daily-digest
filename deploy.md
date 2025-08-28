# Deployment Guide for Daily Digest

## Railway Deployment (Recommended - Free Tier)

### Step 1: Prepare Your Repository
1. Ensure all files are committed to Git
2. Push to GitHub/GitLab if not already done

### Step 2: Deploy to Railway
1. Go to [Railway.app](https://railway.app)
2. Sign up/login with GitHub
3. Click "New Project" → "Deploy from GitHub repo"
4. Select your `daily-digest` repository
5. Railway will automatically detect it's a Python app

### Step 3: Set Environment Variables
In Railway dashboard, go to Variables tab and add:
```
OPENAI_API_KEY=your_openai_api_key
SLACK_WEBHOOK_URL=your_slack_webhook_url
EMAIL_FROM=your_email@gmail.com
EMAIL_TO=recipient@example.com
```

### Step 4: Set Up Cron Job (Scheduled Trigger)
Railway doesn't have built-in cron, so we'll use an external service:

**Option A: GitHub Actions (Free)**
1. Create `.github/workflows/trigger.yml` in your repo
2. Use the workflow to call your `/trigger` endpoint daily

**Option B: Cron-job.org (Free)**
1. Go to [cron-job.org](https://cron-job.org)
2. Create account and add job to call: `https://your-app.railway.app/trigger`
3. Set schedule: Daily at 8:00 AM

### Step 5: Test Deployment
- Your app will be available at: `https://your-app-name.railway.app`
- Test manual trigger: `https://your-app-name.railway.app/trigger`

## Alternative: Render.com Deployment

### Step 1: Deploy to Render
1. Go to [Render.com](https://render.com)
2. Connect GitHub and select repository
3. Choose "Web Service"
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

### Step 2: Add Environment Variables
Same as Railway - add your API keys in Render dashboard

### Step 3: Set Up Cron Job
Use same external cron services as mentioned above.

## Getting Your API Keys

### OpenAI API Key
1. Go to [OpenAI Platform](https://platform.openai.com)
2. Create account → API Keys → Create new key
3. Copy the key (starts with `sk-`)

### Slack Webhook URL
1. Go to [Slack API](https://api.slack.com/apps)
2. Create new app → Incoming Webhooks
3. Activate webhooks → Add to workspace
4. Copy webhook URL

## Testing Locally Before Deploy
```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables in .env file
cp .env.example .env
# Edit .env with your actual values

# Run locally
python main.py
```

Visit `http://localhost:8888` to test locally.
