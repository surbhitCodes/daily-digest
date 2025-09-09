from fastapi import FastAPI, HTTPException, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import feedparser
from summarizer import summarize_articles
from database_postgres import add_user, get_all_active_users, get_user_feeds, update_last_digest_sent, get_user_by_id, add_user_feed, remove_user_feed, get_all_user_feeds
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
    """Send digests to users whose local time matches their scheduled hour and haven't received today's digest"""
    users = get_all_active_users()
    current_utc = datetime.now(pytz.UTC)
    
    for user in users:
        try:
            user_tz = pytz.timezone(user['timezone'])
            user_time = current_utc.astimezone(user_tz)
            
            # Check if it's the user's scheduled hour and they haven't received today's digest
            if user_time.hour == user['schedule_hour'] and should_send_digest_today(user, user_time):
                print(f"Sending digest to {user['email']} at {user_time.strftime('%Y-%m-%d %H:%M %Z')}")
                await asyncio.wait_for(send_digest_to_user(user), timeout=30.0)
            else:
                # Log why digest wasn't sent for debugging
                if user_time.hour != user['schedule_hour']:
                    print(f"Skipping {user['email']}: current hour {user_time.hour} != scheduled hour {user['schedule_hour']}")
                else:
                    print(f"Skipping {user['email']}: already received today's digest")
                
        except asyncio.TimeoutError:
            print(f"Digest for {user['email']} timed out after 30 seconds")
        except Exception as e:
            print(f"Error processing user {user['email']}: {e}")

def should_send_digest_today(user: dict, user_time: datetime) -> bool:
    """Check if user should receive digest today based on last_digest_sent"""
    if not user.get('last_digest_sent'):
        return True  # Never sent before
    
    try:
        raw = user.get('last_digest_sent')
        # Ensure string type for parsing
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode()
        last_sent = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
        # SQLite CURRENT_TIMESTAMP is naive (no tz); treat it as UTC
        if last_sent.tzinfo is None:
            last_sent = pytz.UTC.localize(last_sent)
        last_sent_user_tz = last_sent.astimezone(user_time.tzinfo)
        
        # Check if last digest was sent on a different date in user's timezone
        return last_sent_user_tz.date() != user_time.date()
    except Exception as e:
        print(f"Error parsing last_digest_sent for {user['email']}: {e}")
        return True  # Send if we can't parse the date

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

@app.get("/trigger")
async def trigger_scheduled_digests():
    """Check and send digests to users whose scheduled time has arrived"""
    try:
        users = get_all_active_users()
        current_utc = datetime.now(pytz.UTC)
        
        print(f"Starting digest check at {current_utc.strftime('%Y-%m-%d %H:%M:%S UTC')} for {len(users)} users")
        
        await hourly_digest_check()
        
        return {
            "message": "Scheduled digest check completed",
            "timestamp": current_utc.isoformat(),
            "users_checked": len(users)
        }
    except Exception as e:
        print(f"Error in trigger_scheduled_digests: {e}")
        return {
            "message": "Digest check failed",
            "error": str(e),
            "timestamp": datetime.now(pytz.UTC).isoformat()
        }

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

@app.get("/debug/database")
async def debug_database():
    """Debug database status"""
    import os
    from database_postgres import get_db_connection
    
    db_url = os.getenv("DATABASE_URL", "users.db")
    is_postgres = db_url.startswith("postgres")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if is_postgres:
            # PostgreSQL queries
            cursor.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            tables = [row[0] for row in cursor.fetchall()]
        else:
            # SQLite queries
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
        
        # Get user count
        user_count = 0
        if 'users' in tables:
            cursor.execute("SELECT COUNT(*) FROM users;")
            user_count = cursor.fetchone()[0]
        
        # Get feed count
        feed_count = 0
        if 'user_feeds' in tables:
            cursor.execute("SELECT COUNT(*) FROM user_feeds;")
            feed_count = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "database_type": "PostgreSQL" if is_postgres else "SQLite",
            "database_url": db_url if not is_postgres else "PostgreSQL (URL hidden)",
            "tables": tables,
            "user_count": user_count,
            "feed_count": feed_count,
            "message": "Database accessible"
        }
        
    except Exception as e:
        return {
            "database_type": "PostgreSQL" if is_postgres else "SQLite",
            "database_url": db_url if not is_postgres else "PostgreSQL (URL hidden)",
            "error": str(e),
            "message": "Database connection error"
        }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8888))
    uvicorn.run("multi_user_main:app", host="0.0.0.0", port=port, reload=False)
