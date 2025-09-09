from fastapi import FastAPI
from contextlib import asynccontextmanager
from resources import RSS_FEEDS
import feedparser
from summarizer import summarize_articles
from notifier import notify
from apscheduler.schedulers.background import BackgroundScheduler
import asyncio
import os
from fastapi.responses import HTMLResponse
from openai import OpenAI

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

async def select_top_articles_with_ai(articles: list, max_articles: int = 12) -> list:
    """Use AI to select the most interesting and relevant articles"""
    if len(articles) <= max_articles:
        return [{"title": a["title"], "link": a["link"]} for a in articles]
    
    try:
        # Prepare article summaries for AI analysis
        article_summaries = []
        for i, article in enumerate(articles):
            summary = f"{i+1}. **{article['title']}** (Source: {article['source']})\n"
            if article['summary']:
                # Truncate summary to avoid token limits
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

        client = OpenAI()
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.3
        )
        
        # Parse the response to get selected article indices
        selected_indices = []
        try:
            indices_str = response.choices[0].message.content.strip()
            selected_indices = [int(x.strip()) - 1 for x in indices_str.split(',')]
            # Validate indices are within range
            selected_indices = [i for i in selected_indices if 0 <= i < len(articles)]
        except:
            # Fallback to first articles if parsing fails
            selected_indices = list(range(min(max_articles, len(articles))))
        
        # Return selected articles
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
        # Fallback to first articles
        return [{"title": a["title"], "link": a["link"]} for a in articles[:max_articles]]

async def fetch_articles():
    articles = []
    for i, url in enumerate(RSS_FEEDS):
        try:
            feed = feedparser.parse(url)
            source_name = f"Feed {i+1}"  # Simple source naming
            
            # Get all recent articles (up to 20 per feed)
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
    
    # Use AI to select the most interesting articles
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
