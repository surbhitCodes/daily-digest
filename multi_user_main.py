from fastapi import FastAPI, HTTPException, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import feedparser
from summarizer import summarize_articles
from database import add_user, get_all_active_users, get_user_feeds, update_last_digest_sent, get_user_by_id, add_user_feed, remove_user_feed, get_all_user_feeds
from notifier import send_simple_email
from apscheduler.schedulers.background import BackgroundScheduler
import asyncio
import os
import aiohttp
from datetime import datetime
import pytz

scheduler = BackgroundScheduler()
templates = Jinja2Templates(directory="templates")

def start_scheduler():
    # Run digest job every hour and check which users need their digest
    if not scheduler.running:
        scheduler.add_job(run_hourly_digest_check, "cron", minute=0)
        scheduler.start()

def stop_scheduler():
    scheduler.shutdown()

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()

app = FastAPI(lifespan=lifespan, title="AI Daily Digest - Multi-User")

async def fetch_articles_for_user(user_id: str):
    """Fetch articles from user's configured RSS feeds"""
    feeds = get_user_feeds(user_id)
    if not feeds:
        # Fallback to default feeds if user has none
        feeds = [
            {"url": "https://www.langchain.dev/rss.xml", "name": "LangChain Blog"},
            {"url": "https://openai.com/blog/rss.xml", "name": "OpenAI Blog"},
            {"url": "https://pythonweekly.com/rss", "name": "Python Weekly"},
            {"url": "https://huggingface.co/blog/feed.xml", "name": "Hugging Face Blog"},
            {"url": "https://techcrunch.com/feed/", "name": "TechCrunch"},
            {"url": "https://feeds.arstechnica.com/arstechnica/index", "name": "Ars Technica"}
        ]
    
    articles = []
    for feed in feeds:
        try:
            feed_url = feed['url'] if isinstance(feed, dict) else feed
            parsed_feed = feedparser.parse(feed_url)
            articles.extend(parsed_feed.entries[:3])  # Get 3 articles per feed
        except Exception as e:
            print(f"Error fetching feed {feed_url}: {e}")
            continue
    
    return [{"title": e.title, "link": e.link} for e in articles[:12]]  # Max 12 articles

async def send_digest_to_user(user: dict):
    """Send digest to a specific user"""
    try:
        articles = await fetch_articles_for_user(user['id'])
        if not articles:
            return
        
        summary = await summarize_articles(articles)
        
        # Send to user's Slack webhook with proper formatting
        slack_message = f"🤖 *Daily AI/Tech Digest for {user['email']}*\n\n{summary}"
        
        async with aiohttp.ClientSession() as session:
            await session.post(user['slack_webhook_url'], json={
                "text": slack_message,
                "unfurl_links": True,
                "unfurl_media": True
            })
        
        # Also send email notification
        try:
            await send_simple_email(summary, user['email'])
        except Exception as e:
            print(f"Email notification failed for {user['email']}: {e}")
        
        update_last_digest_sent(user['id'])
        print(f"Digest sent to {user['email']}")
        
    except Exception as e:
        print(f"Error sending digest to {user['email']}: {e}")

def run_hourly_digest_check():
    """Check which users need their digest sent based on their timezone and schedule"""
    asyncio.run(hourly_digest_check())

async def hourly_digest_check():
    """Send digests to users whose local time matches their scheduled hour"""
    users = get_all_active_users()
    current_utc = datetime.now(pytz.UTC)
    
    for user in users:
        try:
            # Convert current UTC time to user's timezone
            user_tz = pytz.timezone(user['timezone'])
            user_time = current_utc.astimezone(user_tz)
            
            # Check if it's the user's scheduled hour
            if user_time.hour == user['schedule_hour']:
                await send_digest_to_user(user)
                
        except Exception as e:
            print(f"Error processing user {user['email']}: {e}")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "contact_email": os.getenv("CONTACT_EMAIL", "get.tech.updated@gmail.com")
    })

@app.get("/health")
async def health_check():
    """Health check endpoint for Railway"""
    return {"status": "healthy", "message": "AI Daily Digest is running"}

@app.post("/register")
async def register_user(
    email: str = Form(...),
    slack_webhook_url: str = Form(...),
    timezone: str = Form(default="UTC"),
    schedule_hour: int = Form(default=8)
):
    """Register a new user"""
    try:
        # Validate Slack webhook URL
        if not slack_webhook_url.startswith("https://hooks.slack.com/"):
            raise HTTPException(400, "Invalid Slack webhook URL")
        
        # Validate schedule hour
        if not 0 <= schedule_hour <= 23:
            raise HTTPException(400, "Schedule hour must be between 0-23")
        
        user_id = add_user(email, slack_webhook_url, timezone, schedule_hour)
        return RedirectResponse(url=f"/success?user_id={user_id}", status_code=303)
        
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Registration failed: {str(e)}")

@app.get("/success", response_class=HTMLResponse)
async def success(request: Request, user_id: str):
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    
    return templates.TemplateResponse("success.html", {
        "request": request, 
        "user": user,
        "trigger_url": f"{request.base_url}trigger/{user_id}",
        "contact_email": os.getenv("CONTACT_EMAIL", "get.tech.updated@gmail.com")
    })

@app.get("/trigger/{user_id}")
async def trigger_user_digest(user_id: str):
    """Manually trigger digest for a specific user"""
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    
    await send_digest_to_user(user)
    return {"message": f"Digest sent to {user['email']}"}

@app.get("/manage/{user_id}", response_class=HTMLResponse)
async def manage_feeds(request: Request, user_id: str):
    """Manage RSS feeds for a user"""
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    
    feeds = get_all_user_feeds(user_id)
    return templates.TemplateResponse("manage.html", {
        "request": request,
        "user": user,
        "feeds": feeds,
        "contact_email": os.getenv("CONTACT_EMAIL", "get.tech.updated@gmail.com")
    })

@app.post("/manage/{user_id}/add-feed")
async def add_feed(user_id: str, feed_url: str = Form(...), feed_name: str = Form(...)):
    """Add a new RSS feed for a user"""
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    
    if not feed_url.startswith(('http://', 'https://')):
        raise HTTPException(400, "Invalid feed URL")
    
    success = add_user_feed(user_id, feed_url, feed_name)
    if not success:
        raise HTTPException(400, "Feed already exists")
    
    return RedirectResponse(url=f"/manage/{user_id}", status_code=303)

@app.post("/manage/{user_id}/remove-feed/{feed_id}")
async def remove_feed(user_id: str, feed_id: int):
    """Remove an RSS feed for a user"""
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    
    success = remove_user_feed(user_id, feed_id)
    if not success:
        raise HTTPException(404, "Feed not found")
    
    return RedirectResponse(url=f"/manage/{user_id}", status_code=303)

@app.get("/stats")
async def get_stats():
    """Get platform statistics"""
    users = get_all_active_users()
    return {
        "total_active_users": len(users),
        "message": "AI Daily Digest - Multi-User Platform"
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8888))
    uvicorn.run("multi_user_main:app", host="0.0.0.0", port=port, reload=False)
