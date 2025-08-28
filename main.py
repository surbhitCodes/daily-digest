from fastapi import FastAPI
from contextlib import asynccontextmanager
from resources import RSS_FEEDS
import feedparser
from summarizer import summarize_articles
from notifier import notify
from apscheduler.schedulers.background import BackgroundScheduler
import asyncio

scheduler = BackgroundScheduler()

def start_scheduler():
    scheduler.add_job(run_daily_job, "cron", hour=8)
    scheduler.start()

def stop_scheduler():
    scheduler.shutdown()

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()

app = FastAPI(lifespan=lifespan)

def fetch_articles():
    articles = []
    for url in RSS_FEEDS:
        feed = feedparser.parse(url)
        articles.extend(feed.entries[:2])
    return [{"title": e.title, "link": e.link} for e in articles]

async def job():
    articles = fetch_articles()
    summary = await summarize_articles(articles)
    await notify(summary)

def run_daily_job():
    asyncio.run(job())

@app.get("/trigger", response_class=HTMLResponse)
async def trigger_digest():
    await job()
    html_content = """
    <html>
        <head>
            <title>Digest Triggered</title>
            <meta http-equiv="refresh" content="2;url=/" />
        </head>
        <body>
            <p>Digest triggered successfully! Redirecting back to home in 2 seconds...</p>
            <p>Or <a href="/">click here</a> to go back now.</p>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)

@app.get("/")
async def root():
    return {"message": "AI Digest running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8888, reload=True)
