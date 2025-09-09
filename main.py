from fastapi import FastAPI
from contextlib import asynccontextmanager
from resources import RSS_FEEDS
import feedparser
from summarizer import summarize_articles, get_openai_client
from notifier import notify
from apscheduler.schedulers.background import BackgroundScheduler
import asyncio
import os
from fastapi.responses import HTMLResponse
import re
from urllib.parse import urlparse

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

def diversify_articles(articles: list, max_articles: int = 12) -> list:
    """Select up to max_articles ensuring diversity across sources (round-robin)."""
    by_source = {}
    for a in articles:
        src = a.get("source", "Unknown")
        by_source.setdefault(src, []).append(a)
    selected = []
    # Round-robin pick one from each source until we reach the limit
    while len(selected) < max_articles and any(by_source.values()):
        for src in list(by_source.keys()):
            bucket = by_source.get(src, [])
            if bucket:
                item = bucket.pop(0)
                selected.append({"title": item["title"], "link": item["link"]})
                if len(selected) >= max_articles:
                    break
    return selected

async def select_top_articles_with_ai(articles: list, max_articles: int = 12) -> list:
    """Use AI to select the most interesting and relevant articles"""
    if len(articles) <= max_articles:
        return [{"title": a["title"], "link": a["link"]} for a in articles]
    
    try:
        article_summaries = []
        for i, article in enumerate(articles):
            summary = f"{i+1}. **{article['title']}** (Source: {article['source']})\n"
            if article['summary']:
                summary += f"   Summary: {article['summary'][:200]}...\n"
            article_summaries.append(summary)
        
        articles_text = "\n".join(article_summaries)
        
        prompt = f"""You are a tech news curator. From the following {len(articles)} articles, select the {max_articles} most interesting, important, and diverse articles for a daily tech digest.

Consider these criteria:
- Breaking news and major announcements
- Significant technological developments
- Industry trends and insights  
- Educational content
- Diverse topics (AI/ML, web dev, mobile, security, etc.)
- Avoid duplicate or very similar topics

Articles:
{articles_text}

Respond with ONLY the numbers of the selected articles (e.g., "1,3,7,12,15,18,22,25,28,30,33,36"), separated by commas, in order of importance."""

        client = get_openai_client()
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.3
        )
        
        selected_indices = []
        try:
            raw = response.choices[0].message.content.strip()
            print(f"[AI Selection] Raw indices response: {raw}")
            nums = re.findall(r"\d+", raw)
            selected_indices = []
            seen = set()
            for n in nums:
                i = int(n) - 1
                if 0 <= i < len(articles) and i not in seen:
                    selected_indices.append(i)
                    seen.add(i)
            if not selected_indices:
                raise ValueError("No valid indices parsed")
        except Exception as parse_err:
            print(f"[AI Selection] Parse error: {parse_err}. Falling back to diverse selection of {max_articles}.")
            return diversify_articles(articles, max_articles)
        
        selected_articles = []
        for i in selected_indices[:max_articles]:
            article = articles[i]
            selected_articles.append({
                "title": article["title"],
                "link": article["link"]
            })
        
        return selected_articles
        
    except Exception as e:
        print(f"Error in AI article selection: {e}")
        return diversify_articles(articles, max_articles)

async def fetch_articles():
    articles = []
    for i, url in enumerate(RSS_FEEDS):
        try:
            feed = feedparser.parse(url, request_headers={"User-Agent": "AI-Daily-Digest/1.0"})
            source_name = getattr(feed.feed, 'title', None)
            if not source_name:
                try:
                    source_name = urlparse(url).netloc
                except Exception:
                    source_name = f"Feed {i+1}"
            
            for entry in feed.entries[:20]:
                article = {
                    "title": entry.title,
                    "link": entry.link,
                    "summary": getattr(entry, 'summary', ''),
                    "published": getattr(entry, 'published', ''),
                    "source": source_name
                }
                articles.append(article)
        except Exception as e:
            print(f"Error fetching feed {url}: {e}")
            continue
    
    if articles:
        selected_articles = await select_top_articles_with_ai(articles)
        return selected_articles
    
    return []

async def job():
    articles = await fetch_articles()
    summary = await summarize_articles(articles)
    await notify(summary)

def run_daily_job():
    try:
        asyncio.run(asyncio.wait_for(job(), timeout=30.0))
    except asyncio.TimeoutError:
        print("Job execution timed out after 30 seconds")
    except Exception as e:
        print(f"Error in daily job: {e}")

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
    port = int(os.environ.get("PORT", 8888))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
