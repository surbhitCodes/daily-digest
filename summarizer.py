from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def summarize_articles(articles):
    combined_text = "\n\n".join(f"{a['title']} - {a['link']}" for a in articles[:5])
    prompt = f"Summarize the following tech/AI articles in simple terms:\n{combined_text}"
    
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    return response.choices[0].message.content.strip()

def format_slack_digest(articles: list[dict]) -> str:
    blocks = ["*📰 AI + Dev Digest:*\n"]
    for i, article in enumerate(articles, 1):
        title = article.get("title", "Untitled")
        link = article.get("link", "#")
        summary = article.get("summary", "No summary provided.")
        blocks.append(
            f"*{i}. <{link}|{title}>*\n"
            f"> {summary.strip()}\n"
        )
    return "\n".join(blocks)
