from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def summarize_articles(articles):
    combined_text = "\n\n".join(f"{a['title']} - {a['link']}" for a in articles[:5])
    prompt = f"Summarize the following tech/AI articles in simple terms:\n{combined_text}"
    
    response = client.responses.create(
        model="gpt-4.1",
        input=prompt,
        temperature=0.3
    )
    return response.output[0].content[0].text.strip()

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
